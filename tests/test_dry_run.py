"""CLI dry-run exercises pipeline wiring offline."""
from __future__ import annotations

import json
from pathlib import Path

from discovery_engine.cli import main
from discovery_engine.config import ENGINE_VERSION, FINDINGS_SCHEMA


def test_cli_dry_run_writes_skeleton(tmp_path: Path, capsys):
    main(["run", "--dry-run", "--outdir", str(tmp_path), "--no-tracing"])
    days = [p for p in tmp_path.iterdir() if p.is_dir()]
    assert len(days) == 1
    findings_path = days[0] / "findings.json"
    report_path = days[0] / "report.md"
    payload = json.loads(findings_path.read_text())
    assert payload["schema"] == FINDINGS_SCHEMA
    assert payload["engine_version"] == ENGINE_VERSION
    assert payload["dry_run"] is True
    assert payload["findings"] == []
    assert payload["counts"] == {
        "research_gap": 0,
        "conflict": 0,
        "repurposing_lead": 0,
        "hypothesis": 0,
    }
    assert isinstance(payload["warnings"], list) and payload["warnings"]
    md = report_path.read_text()
    assert "dry-run" in md
    captured = capsys.readouterr().out
    assert "Dry-run" in captured
    assert str(findings_path) in captured
