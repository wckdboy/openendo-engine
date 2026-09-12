"""Discovery Engine core — the four Stage-4 passes.

Each pass is a @traceable function so the whole run shows up as a trace tree
(root run -> stage runs -> per-call LLM runs) in LangSmith.
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

Return STRICT JSON: a list of finding objects, each:
{"claim": "...", "classification": "...", "confidence": "high|medium|low",
 "sources": [{"type": "pmid|nct|chembl|url", "id": "...", "url": "..."}],
 "rationale": "...", "caveats": "..."}
"""


def _extract_json(text: str) -> list:
    """Tolerant JSON extraction (fenced or bare list)."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end <= start:
        raise ValueError(f"no JSON array in model output: {text[:200]}")
    return json.loads(text[start : end + 1])


@traceable(name="discovery_stage_call", run_type="chain")
def _stage_call(client, model: str, temperature: float, category: str, user_prompt: str) -> list:
    """One LLM stage call. Auto-traced by the wrapped client."""
    resp = client.chat.completions.create(
        model=model,
        temperature=temperature,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )
    content = resp.choices[0].message.content or ""
    return _extract_json(content)


def _run_stage(s, client, category: str, task: str, context: str, corpus: d.Corpus) -> dict:
    """Validate + tag one stage's findings. Returns stage report."""
    whitelist = corpus.identifier_whitelist()
    prompt = (
        f"TASK ({category}): {task}\n\n"
        f"CONTEXT DATA:\n{context}\n\n"
        f"IDENTIFIER WHITELIST (only these may be cited):\n{whitelist}\n\n"
        "Return findings as a JSON array. Each finding must have a 'claim' that "
        f"is a single {category.replace('_', ' ')}."
    )
    raw = _stage_call(client, s.model, s.temperature, category, prompt)

    valid, dropped = [], []
    for i, f in enumerate(raw):
        f = dict(f)
        f["category"] = category
        problems = validate_finding(f, category, corpus.allowed_ids, i)
        if problems:
            dropped.append({"finding": f, "problems": problems})
            continue
        f["sources"] = [
            {
                "type": src.get("type"),
                "id": str(src.get("id", "")),
                "url": src.get("url") or _default_url(src.get("type"), src.get("id")),
            }
            for src in f.get("sources") or []
        ]
        valid.append(f)
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


@traceable(name="discovery_research_gaps", run_type="chain")
def stage_research_gaps(s, client, corpus: d.Corpus) -> dict:
    ctx = "\n\n".join([
        "== TARGETS (58 drug targets; 35 novel) ==",
        d.compact_targets(corpus),
        "== REPURPOSING CANDIDATES ==",
        d.compact_repurposing(corpus),
        "== RECRUITING TRIALS WORLDWIDE ==",
        d.compact_trials(corpus),
    ])
    return _run_stage(
        s, client, "research_gap",
        "Identify concrete research gaps: novel targets with no approved drug, "
        "no recruiting trial, or contradictory/absent expression evidence. "
        "Name the gap, why it matters, and what evidence would close it.",
        ctx, corpus,
    )


@traceable(name="discovery_conflicts", run_type="chain")
def stage_conflicts(s, client, corpus: d.Corpus) -> dict:
    ctx = d.compact_papers(corpus, "evidence_weekly", limit=12)
    return _run_stage(
        s, client, "conflict",
        "Find conflicting or contradictory results across the recent evidence "
        "(e.g. direction-of-effect disagreements, mechanism disputes, results "
        "that challenge a repurposing candidate's rationale). For each, state "
        "the two sides with their sources and what would resolve the conflict.",
        ctx, corpus,
    )


@traceable(name="discovery_repurposing_leads", run_type="chain")
def stage_repurposing_leads(s, client, corpus: d.Corpus) -> dict:
    ctx = "\n\n".join([
        "== REPURPOSING CANDIDATES ==",
        d.compact_repurposing(corpus),
        "== TARGETS ==",
        d.compact_targets(corpus),
        "== RECENT EVIDENCE ==",
        d.compact_papers(corpus, "evidence_weekly", limit=8),
    ])
    return _run_stage(
        s, client, "repurposing_lead",
        "Evaluate drug-repurposing leads: rank candidate drug->target pairs by "
        "mechanistic plausibility, evidence strength and direction of effect. "
        "Flag wrong-direction candidates. Suggest overlooked approved-drug "
        "opportunities ONLY if supported by whitelisted targets/evidence.",
        ctx, corpus,
    )


@traceable(name="discovery_hypotheses", run_type="chain")
def stage_hypotheses(s, client, corpus: d.Corpus) -> dict:
    ctx = "\n\n".join([
        "== TARGETS ==",
        d.compact_targets(corpus),
        "== RECENT EVIDENCE ==",
        d.compact_papers(corpus, "evidence_weekly", limit=8),
    ])
    return _run_stage(
        s, client, "hypothesis",
        "Generate testable, falsifiable research hypotheses linking targets, "
        "mechanisms and disease biology. Each must name the proposed experiment "
        "or analysis that would test it. Classification should almost always be "
        "untested-hypothesis unless the cited sources directly support the claim.",
        ctx, corpus,
    )


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
    """Full engine run: four traced stages -> tagged findings report.

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
    stage_reports = [
        stage_research_gaps(s, client, corpus),
        stage_conflicts(s, client, corpus),
        stage_repurposing_leads(s, client, corpus),
        stage_hypotheses(s, client, corpus),
    ]
    return assemble_result(s, stage_reports, warnings=warnings, dry_run=False)
