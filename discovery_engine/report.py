"""Report writing: JSON + human-readable markdown."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from .config import Settings
from .engine import run_discovery
from .tracing import apply_tracing_env

CONF_ORDER = {"documented-evidence": 0, "likely-association": 1, "untested-hypothesis": 2}


def write_reports(result: dict, outdir: Path) -> dict:
    """Write findings.json + report.md under outdir/<run_date>/. Returns paths."""
    day = result["run_date"]
    target = outdir / day
    target.mkdir(parents=True, exist_ok=True)
    json_path = target / "findings.json"
    md_path = target / "report.md"
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    md_path.write_text(render_markdown(result))
    return {"json": json_path, "md": md_path}


def render_markdown(result: dict) -> str:
    counts = Counter(f["category"] for f in result["findings"])
    lines = [
        f"# OpenEndo Discovery Engine — {result['run_date']}",
        "",
        f"_Model: {result['model']} · Project: {result['langsmith_project']} · "
        f"Source: {result['source']} · Generated: {result['generated_at']}_",
        "",
        "> Research support only — never individual medical advice. Every claim is",
        "> classified documented-evidence | likely-association | untested-hypothesis",
        "> and traced to its sources.",
        "",
        "## Summary",
        "",
    ]
    for cat in ("research_gap", "conflict", "repurposing_lead", "hypothesis"):
        lines.append(f"- {cat}: {counts.get(cat, 0)} findings")
    if result.get("dropped"):
        lines.append(f"- dropped (failed validation): {len(result['dropped'])}")
    if result.get("dry_run"):
        lines.append("- mode: dry-run (LLM skipped; skeleton findings)")
    if result.get("warnings"):
        lines.append(f"- warnings: {len(result['warnings'])}")
    lines.append("")

    if result.get("warnings"):
        lines += ["## Warnings", ""]
        for warning in result["warnings"]:
            lines.append(f"- {warning}")
        lines.append("")

    findings = sorted(result["findings"], key=lambda f: (CONF_ORDER.get(f["classification"], 9), f["id"]))
    for f in findings:
        lines += [
            f"## {f['id']} — {f['category'].replace('_', ' ')}",
            "",
            f"**Claim:** {f['claim']}",
            "",
            f"**Classification:** {f['classification']} · **Confidence:** {f.get('confidence', '-')}",
            "",
            f"**Rationale:** {f.get('rationale', '-')}",
            "",
        ]
        if f.get("caveats"):
            lines += [f"**Caveats:** {f['caveats']}", ""]
        srcs = " · ".join(
            f"[{s.get('type')}:{s.get('id')}]({s.get('url')})" for s in (f.get("sources") or [])
        )
        if srcs:
            lines += [f"**Sources:** {srcs}", ""]
        lines.append("---")
        lines.append("")
    return "\n".join(lines)


def run(s: Settings, outdir: Path, *, dry_run: bool = False) -> dict:
    if dry_run:
        print("Dry-run: skipping LLM and remote fetch.")
    elif not s.tracing_enabled():
        print("WARN: LANGSMITH_API_KEY not set — running WITHOUT tracing.")
    apply_tracing_env(s)
    result = run_discovery(s, dry_run=dry_run)
    paths = write_reports(result, outdir)
    warnings = result.get("warnings") or []
    print(f"Findings: {result['counts']} — dropped: {len(result.get('dropped', []))} — warnings: {len(warnings)}")
    for warning in warnings:
        print(f"WARN: {warning}")
    print(f"JSON: {paths['json']}")
    print(f"Markdown: {paths['md']}")
    return result
