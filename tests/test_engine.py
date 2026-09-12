"""Finding IDs, result assembly, dry-run skeleton — no network, no LLM."""
from __future__ import annotations

from datetime import date

from discovery_engine.config import CATEGORIES, ENGINE_VERSION, FINDINGS_SCHEMA, Settings
from discovery_engine.engine import (
    assemble_result,
    empty_stage_reports,
    gen_finding_id,
    run_discovery,
)
from tests.helpers import write_mini_openendo

RESULT_KEYS = {
    "schema",
    "run_date",
    "generated_at",
    "engine_version",
    "model",
    "langsmith_project",
    "source",
    "dry_run",
    "counts",
    "dropped",
    "warnings",
    "findings",
}


def test_gen_finding_id_format():
    assert gen_finding_id(date(2026, 9, 12), "research_gap", 1) == "OE-2026-09-12-RESE-0001"
    assert gen_finding_id(date(2026, 9, 12), "conflict", 2) == "OE-2026-09-12-CONF-0002"
    assert gen_finding_id(date(2026, 9, 12), "repurposing_lead", 3) == "OE-2026-09-12-REPU-0003"
    assert gen_finding_id(date(2026, 9, 12), "hypothesis", 12) == "OE-2026-09-12-HYPO-0012"


def test_assemble_result_assigns_ids_and_warnings():
    stages = [
        {
            "category": "research_gap",
            "findings": [
                {
                    "claim": "Fixture claim: NCT000001 appears in the fixture trial list",
                    "classification": "documented-evidence",
                    "confidence": "high",
                    "sources": [{"type": "nct", "id": "NCT000001", "url": "https://clinicaltrials.gov/study/NCT000001"}],
                    "category": "research_gap",
                }
            ],
            "dropped": [],
        },
        {"category": "conflict", "findings": [], "dropped": [{"finding": {"claim": "x"}, "problems": ["missing"]}]},
        {"category": "repurposing_lead", "findings": [], "dropped": []},
        {"category": "hypothesis", "findings": [], "dropped": []},
    ]
    result = assemble_result(
        Settings(openai_api_key="", langsmith_api_key=""),
        stages,
        warnings=["evidence_weekly: LATEST pointer missing"],
        run_date=date(2026, 9, 12),
    )
    assert result["schema"] == FINDINGS_SCHEMA
    assert result["engine_version"] == ENGINE_VERSION
    assert set(result) >= RESULT_KEYS
    assert result["findings"][0]["id"] == "OE-2026-09-12-RESE-0001"
    assert result["counts"] == {
        "research_gap": 1,
        "conflict": 0,
        "repurposing_lead": 0,
        "hypothesis": 0,
    }
    assert len(result["dropped"]) == 1
    assert result["warnings"] == ["evidence_weekly: LATEST pointer missing"]
    assert result["dry_run"] is False


def test_empty_stage_reports_cover_all_categories():
    reports = empty_stage_reports()
    assert [r["category"] for r in reports] == list(CATEGORIES)
    assert all(r["findings"] == [] and r["dropped"] == [] for r in reports)


def test_dry_run_emits_schema_valid_skeleton():
    result = run_discovery(Settings(openai_api_key="", langsmith_api_key=""), dry_run=True)
    assert set(result) >= RESULT_KEYS
    assert result["schema"] == FINDINGS_SCHEMA
    assert result["engine_version"] == ENGINE_VERSION
    assert result["dry_run"] is True
    assert result["model"] == "dry-run"
    assert result["source"] == "dry-run"
    assert result["findings"] == []
    assert result["dropped"] == []
    assert result["counts"] == {category: 0 for category in CATEGORIES}
    assert any("LLM stages skipped" in w for w in result["warnings"])
    assert any("skipped remote corpus fetch" in w for w in result["warnings"])


def test_dry_run_local_surfaces_latest_warning(tmp_path):
    root = write_mini_openendo(tmp_path / "openendo", latest=None)
    settings = Settings(
        source="local",
        local_path=str(root),
        openai_api_key="",
        langsmith_api_key="",
    )
    result = run_discovery(settings, dry_run=True)
    assert result["schema"] == FINDINGS_SCHEMA
    assert result["findings"] == []
    assert result["source"] == "local"
    assert any("LATEST pointer missing" in w for w in result["warnings"])
    assert any("LLM stages skipped" in w for w in result["warnings"])
