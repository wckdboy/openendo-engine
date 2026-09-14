"""Finding IDs, result assembly, dry-run skeleton — no network, no LLM."""
from __future__ import annotations

from datetime import date

from discovery_engine.config import CATEGORIES, ENGINE_VERSION, FINDINGS_SCHEMA, Settings
from discovery_engine.engine import (
    STAGE_TASKS,
    SYSTEM_PROMPT,
    _extract_json_value,
    assemble_result,
    build_discovery_prompt,
    empty_stage_reports,
    gen_finding_id,
    group_stage_payload,
    run_discovery,
)
from tests.helpers import mini_corpus, write_mini_openendo

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


def test_stage_tasks_cover_all_categories():
    assert set(STAGE_TASKS) == set(CATEGORIES)


def test_system_prompt_includes_corpus_caveats():
    assert "titles only" in SYSTEM_PROMPT
    assert "ANY indication" in SYSTEM_PROMPT
    assert "M3 status" in SYSTEM_PROMPT
    assert "one object with keys research_gap, conflict," in SYSTEM_PROMPT


def test_build_discovery_prompt_packs_context_once():
    corpus = mini_corpus()
    prompt = build_discovery_prompt(corpus)
    assert prompt.count("CONTEXT DATA (shared; sent once)") == 1
    assert prompt.count("IDENTIFIER WHITELIST") == 1
    for category in CATEGORIES:
        assert f"- {category}:" in prompt
    assert "Sirolimus (rapamycin)" in prompt
    assert "status=top-tier" in prompt
    assert "title-only" in prompt.lower()
    assert "ChEMBL any-indication" in prompt
    # Shared pack, not four copies of targets/repurposing.
    assert prompt.count("== TARGETS ==") == 1
    assert prompt.count("== REPURPOSING CANDIDATES ==") == 1


def test_group_stage_payload_object_and_list():
    payload = {
        "research_gap": [{"claim": "gap"}],
        "conflict": [],
        "repurposing_lead": [{"claim": "lead"}],
        "hypothesis": [{"claim": "hyp"}],
    }
    grouped = group_stage_payload(payload)
    assert [f["claim"] for f in grouped["research_gap"]] == ["gap"]
    assert grouped["conflict"] == []
    assert grouped["repurposing_lead"][0]["claim"] == "lead"

    as_list = [
        {"category": "conflict", "claim": "c1"},
        {"category": "hypothesis", "claim": "h1"},
        {"category": "unknown", "claim": "drop-me"},
    ]
    grouped_list = group_stage_payload(as_list)
    assert grouped_list["conflict"][0]["claim"] == "c1"
    assert grouped_list["hypothesis"][0]["claim"] == "h1"
    assert grouped_list["research_gap"] == []


def test_extract_json_value_object_and_fence():
    obj = _extract_json_value('```json\n{"research_gap": [], "conflict": []}\n```')
    assert obj == {"research_gap": [], "conflict": []}
    arr = _extract_json_value('prefix [{"claim": "x"}] suffix')
    assert arr == [{"claim": "x"}]
