"""Markdown rendering from a fake result dict — no network, no LLM."""
from __future__ import annotations

from discovery_engine.config import ENGINE_VERSION, FINDINGS_SCHEMA
from discovery_engine.report import render_markdown, write_reports


def fake_result() -> dict:
    return {
        "schema": FINDINGS_SCHEMA,
        "run_date": "2026-09-12",
        "generated_at": "2026-09-12T00:00:00+00:00",
        "engine_version": ENGINE_VERSION,
        "model": "fixture-model",
        "langsmith_project": "openendo-discovery-engine",
        "source": "local",
        "dry_run": False,
        "counts": {
            "research_gap": 1,
            "conflict": 0,
            "repurposing_lead": 0,
            "hypothesis": 1,
        },
        "dropped": [{"finding": {"claim": "dropped fixture"}, "problems": ["source pmid:999 not in loaded data whitelist"]}],
        "warnings": ["evidence_weekly: LATEST pointer missing at /fixture/LATEST"],
        "findings": [
            {
                "id": "OE-2026-09-12-RESE-0001",
                "category": "research_gap",
                "claim": "Fixture claim: NCT000001 is listed in the fixture trial file",
                "classification": "documented-evidence",
                "confidence": "high",
                "rationale": "Present in the fixture corpus whitelist.",
                "caveats": "Fixture only — not a clinical conclusion.",
                "sources": [
                    {
                        "type": "nct",
                        "id": "NCT000001",
                        "url": "https://clinicaltrials.gov/study/NCT000001",
                    }
                ],
            },
            {
                "id": "OE-2026-09-12-HYPO-0001",
                "category": "hypothesis",
                "claim": "Fixture hypothesis: a follow-up measurement would be needed",
                "classification": "untested-hypothesis",
                "confidence": "low",
                "rationale": "No whitelist source is attached, by design.",
                "sources": [],
            },
        ],
    }


def test_render_markdown_includes_summary_findings_and_warnings():
    md = render_markdown(fake_result())
    assert md.startswith("# OpenEndo Discovery Engine — 2026-09-12")
    assert "fixture-model" in md
    assert "- research_gap: 1 findings" in md
    assert "- hypothesis: 1 findings" in md
    assert "- dropped (failed validation): 1" in md
    assert "- warnings: 1" in md
    assert "## Warnings" in md
    assert "LATEST pointer missing" in md
    assert "## OE-2026-09-12-RESE-0001 — research gap" in md
    assert "**Claim:** Fixture claim: NCT000001 is listed in the fixture trial file" in md
    assert "[nct:NCT000001](https://clinicaltrials.gov/study/NCT000001)" in md
    assert "**Caveats:** Fixture only — not a clinical conclusion." in md
    assert "## OE-2026-09-12-HYPO-0001 — hypothesis" in md
    assert "untested-hypothesis" in md
    assert "Research support only" in md


def test_documented_finding_sorts_before_untested():
    md = render_markdown(fake_result())
    assert md.index("OE-2026-09-12-RESE-0001") < md.index("OE-2026-09-12-HYPO-0001")


def test_write_reports_uses_run_date_directory(tmp_path):
    paths = write_reports(fake_result(), tmp_path)
    assert paths["json"] == tmp_path / "2026-09-12" / "findings.json"
    assert paths["md"] == tmp_path / "2026-09-12" / "report.md"
    assert paths["json"].is_file()
    assert paths["md"].is_file()
    assert "OE-2026-09-12-RESE-0001" in paths["md"].read_text()
