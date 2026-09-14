"""Discovery Engine core — one Stage-4 LLM call, four finding categories.

The live path packs shared corpus context once (targets, named M3 shortlist,
trials, title-only weekly evidence) and asks the model for all four categories
in a single JSON object. Dry-run still skips the LLM.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone

from langsmith import traceable

from . import data as d
from .config import CATEGORIES, ENGINE_VERSION, FINDINGS_SCHEMA, Settings
from .tracing import traced_client
from .validation import validate_finding

SYSTEM_PROMPT = """You are the OpenEndo Discovery Engine, a research-support AI for endometriosis.

Mission law — every output MUST obey all three:
1. Classify every claim exactly as one of:
   - documented-evidence   (directly supported by the cited sources)
   - likely-association    (strongly implied by available evidence)
   - untested-hypothesis   (plausible but unverified)
2. Trace every claim to its original sources. Cite ONLY identifiers from the
   provided WHITELIST — never invent a PMID/NCT/CHEMBL. If a claim has no
   citable source from the whitelist, mark it untested-hypothesis with no
   source or a "url" source you can verify.
3. This is research support, never individual medical advice. No dosing,
   no patient-facing recommendations.

Corpus caveats (do not overclaim):
- Weekly evidence rows are titles only unless an abstract is present. Do not
  invent mechanism, direction of effect, or study results from a title.
- ChEMBL max_phase is the highest phase for ANY indication, not
  endometriosis-specific. Do not treat it as endometriosis approval/trial status.
- When a repurposing candidate has an M3 status in context (top-tier,
  watchlist, validated-axis, wrong-direction), use that status. Do not relabel
  a named shortlist compound as wrong-direction when its provided status is
  top-tier or watchlist. wrong-direction and validated-axis are
  target-validating evidence, not repurposing leads.

Return STRICT JSON: one object with keys research_gap, conflict,
repurposing_lead, hypothesis. Each value is a list of finding objects:
{"claim": "...", "classification": "...", "confidence": "high|medium|low",
 "sources": [{"type": "pmid|nct|chembl|url", "id": "...", "url": "..."}],
 "rationale": "...", "caveats": "..."}
Empty lists are allowed. Do not invent medical claims beyond the context.
"""

STAGE_TASKS = {
    "research_gap": (
        "Identify concrete research gaps: novel targets with no approved drug, "
        "no recruiting trial, or contradictory/absent expression evidence. "
        "Name the gap, why it matters, and what evidence would close it. "
        "Do not treat ChEMBL max_phase as endometriosis-specific."
    ),
    "conflict": (
        "Find conflicting or contradictory results across the recent evidence "
        "(e.g. direction-of-effect disagreements, mechanism disputes, results "
        "that challenge a repurposing candidate's rationale). For each, state "
        "the two sides with their sources and what would resolve the conflict. "
        "If the evidence is title-only, do not invent the two sides from titles; "
        "prefer an empty list over fabricated conflicts."
    ),
    "repurposing_lead": (
        "Evaluate drug-repurposing leads using the named M3 shortlist. Rank "
        "candidate drug->target pairs by the provided status, mechanistic "
        "notes, and evidence already in context. Use provided drug names — "
        "never discuss a shortlist compound as an anonymous ChEMBL id. Do not "
        "flag wrong-direction unless the provided "
        "status is wrong-direction. Suggest overlooked approved-drug "
        "opportunities ONLY if supported by whitelisted targets/evidence."
    ),
    "hypothesis": (
        "Generate testable, falsifiable research hypotheses linking targets, "
        "mechanisms and disease biology. Each must name the proposed experiment "
        "or analysis that would test it. Classification should almost always be "
        "untested-hypothesis unless the cited sources directly support the claim. "
        "Do not invent a mechanism from a paper title alone."
    ),
}


def _extract_json_value(text: str):
    """Tolerant JSON extraction (fenced or bare object/list)."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    decoder = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch not in "[{":
            continue
        try:
            value, _ = decoder.raw_decode(text[i:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, (dict, list)):
            return value
    raise ValueError(f"no JSON object/array in model output: {text[:200]}")


def group_stage_payload(payload) -> dict[str, list]:
    """Split a combined model payload into the four finding categories."""
    grouped = {category: [] for category in CATEGORIES}
    if isinstance(payload, dict):
        nested = payload.get("findings")
        if isinstance(nested, list) and not any(
            isinstance(payload.get(category), list) for category in CATEGORIES
        ):
            payload = nested
        else:
            for category in CATEGORIES:
                items = payload.get(category)
                if isinstance(items, list):
                    grouped[category] = [item for item in items if isinstance(item, dict)]
            return grouped
    if isinstance(payload, list):
        for item in payload:
            if not isinstance(item, dict):
                continue
            category = item.get("category")
            if category in grouped:
                grouped[category].append(item)
        return grouped
    raise ValueError(f"unexpected model payload type: {type(payload).__name__}")


def _never_category(category: str) -> None:
    """Exhaustiveness helper if CATEGORIES gains a member that STAGE_TASKS missed."""
    raise ValueError(f"unhandled discovery category: {category}")


def build_discovery_prompt(corpus: d.Corpus) -> str:
    """Shared context + four category tasks in one user prompt."""
    context = d.pack_shared_context(corpus)
    whitelist = d.scoped_identifier_whitelist(corpus, context) or corpus.identifier_whitelist()
    task_lines = []
    for category in CATEGORIES:
        task = STAGE_TASKS.get(category)
        if task is None:
            _never_category(category)
        task_lines.append(f"- {category}: {task}")
    return (
        "Produce findings for ALL FOUR categories below from the same context. "
        "Return a JSON object with those four keys (each a list of findings).\n\n"
        + "\n".join(task_lines)
        + "\n\nCONTEXT DATA (shared; sent once):\n"
        + context
        + "\n\nIDENTIFIER WHITELIST (only these may be cited; scoped to IDs in context):\n"
        + (whitelist or "(none — do not cite pmid/nct/chembl identifiers)")
        + "\n"
    )


@traceable(name="discovery_stage_call", run_type="chain")
def _stage_call(client, model: str, temperature: float, user_prompt: str):
    """One LLM call for all four categories. Auto-traced by the wrapped client."""
    resp = client.chat.completions.create(
        model=model,
        temperature=temperature,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )
    content = resp.choices[0].message.content or ""
    return _extract_json_value(content)


def _validate_findings(raw: list, category: str, corpus: d.Corpus) -> dict:
    """Validate + tag one category's findings. Returns stage report."""
    valid, dropped = [], []
    for i, finding in enumerate(raw):
        finding = dict(finding)
        finding["category"] = category
        problems = validate_finding(finding, category, corpus.allowed_ids, i)
        if problems:
            dropped.append({"finding": finding, "problems": problems})
            continue
        finding["sources"] = [
            {
                "type": src.get("type"),
                "id": str(src.get("id", "")),
                "url": src.get("url") or _default_url(src.get("type"), src.get("id")),
            }
            for src in finding.get("sources") or []
        ]
        valid.append(finding)
    return {"category": category, "findings": valid, "dropped": dropped}


def _default_url(kind: str, sid: str) -> str:
    if kind == "pmid":
        return f"https://pubmed.ncbi.nlm.nih.gov/{sid}/"
    if kind == "nct":
        return f"https://clinicaltrials.gov/study/{sid}"
    if kind == "chembl":
        return f"https://www.ebi.ac.uk/chembl/target_report_card/{sid}/"
    return sid or ""


def gen_finding_id(run_date: date, category: str, i: int) -> str:
    """Stable finding id: OE-YYYY-MM-DD-CATE-0001."""
    return f"OE-{run_date.isoformat()}-{category[:4].upper()}-{i:04d}"


def empty_stage_reports() -> list[dict]:
    """Schema-valid empty stages for dry-run / fixture mode."""
    return [{"category": category, "findings": [], "dropped": []} for category in CATEGORIES]


def assemble_result(
    s: Settings,
    stage_reports: list[dict],
    *,
    warnings: list[str] | None = None,
    dry_run: bool = False,
    run_date: date | None = None,
) -> dict:
    """Build the findings document. Always includes a warnings list."""
    run_date = run_date or date.today()
    now = datetime.now(timezone.utc).isoformat()
    all_findings = []
    for report in stage_reports:
        for i, finding in enumerate(report["findings"]):
            tagged = dict(finding)
            tagged["id"] = gen_finding_id(run_date, report["category"], i + 1)
            all_findings.append(tagged)
    result = {
        "schema": FINDINGS_SCHEMA,
        "run_date": run_date.isoformat(),
        "generated_at": now,
        "engine_version": ENGINE_VERSION,
        "model": "dry-run" if dry_run else s.model,
        "langsmith_project": s.langsmith_project,
        "source": "dry-run" if dry_run and s.source == "raw" else s.source,
        "dry_run": dry_run,
        "counts": {report["category"]: len(report["findings"]) for report in stage_reports},
        "dropped": [item for report in stage_reports for item in report["dropped"]],
        "warnings": list(warnings or []),
        "findings": all_findings,
    }
    return result


@traceable(name="discovery_all_stages", run_type="chain")
def run_all_stages(s, client, corpus: d.Corpus) -> list[dict]:
    """One LLM call → four category reports (same schema as the old four stages)."""
    prompt = build_discovery_prompt(corpus)
    payload = _stage_call(client, s.model, s.temperature, prompt)
    grouped = group_stage_payload(payload)
    return [_validate_findings(grouped[category], category, corpus) for category in CATEGORIES]


def _load_run_corpus(s: Settings, *, dry_run: bool) -> d.Corpus:
    """Load the data layer. Dry-run never touches the network."""
    if dry_run and s.source == "raw":
        corpus = d.Corpus()
        corpus.warn("dry-run: skipped remote corpus fetch (no network)")
        d.collect_whitelist(corpus)
        return corpus
    return d.load_corpus(s.source, s.local_path)


@traceable(name="discovery_run", run_type="chain")
def run_discovery(s: Settings, *, dry_run: bool = False) -> dict:
    """Full engine run: one traced LLM call -> four tagged finding categories.

    dry_run skips the LLM and (for source=raw) remote fetches, then writes a
    schema-valid skeleton with empty findings. Local --source still loads
    fixtures so CI can exercise the loader without inventing claims.
    """
    corpus = _load_run_corpus(s, dry_run=dry_run)
    warnings = list(corpus.warnings)
    if dry_run:
        warnings.append("dry-run: LLM stages skipped; skeleton findings only")
        return assemble_result(s, empty_stage_reports(), warnings=warnings, dry_run=True)

    client = traced_client(s)
    stage_reports = run_all_stages(s, client, corpus)
    return assemble_result(s, stage_reports, warnings=warnings, dry_run=False)
