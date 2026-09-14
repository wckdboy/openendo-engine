"""Synthetic OpenEndo-shaped fixtures. Not medical claims; not live data."""
from __future__ import annotations

import json
from pathlib import Path

from discovery_engine.data import Corpus, collect_whitelist

FIXTURE_TARGET = {
    "gene": "FKBP4",
    "chembl_id": "CHEMBL4050",
    "name": "Peptidyl-prolyl cis-trans isomerase FKBP4",
    "mechanisms": 0,
    "max_phase": 0.0,
    "novel": True,
}

# Mirrors live openendo JSON: per_target often stores name==molecule (anonymous
# ChEMBL id), while the top-level candidates list has the human name + M3 status.
FIXTURE_PER_TARGET_CANDIDATE = {
    "name": "CHEMBL413",
    "molecule": "CHEMBL413",
    "pchembl": 8.1,
    "phase": 4,
}

FIXTURE_NAMED_CANDIDATE = {
    "target": "FKBP4",
    "target_chembl": "CHEMBL4050",
    "molecule": "CHEMBL413",
    "name": "Sirolimus (rapamycin)",
    "pchembl": 8.1,
    "phase": 4,
    "status": "top-tier",
    "status_detail": "Fixture M3 status — not a medical claim",
    "validation_ref": "https://example.test/m3",
}

FIXTURE_VALIDATION = {
    "status_vocabulary": ["top-tier", "watchlist", "validated-axis", "wrong-direction"],
    "note": "synthetic fixture — status is not a medical claim",
}

# Back-compat alias used by per_target-only tests.
FIXTURE_CANDIDATE = FIXTURE_PER_TARGET_CANDIDATE

FIXTURE_TRIAL = {
    "nct_id": "NCT000001",
    "phase": "Phase 3",
    "title": "Fixture trial title",
    "sponsor": "Fixture Sponsor",
    "countries": ["Denmark"],
}

FIXTURE_PAPER = {
    "pmid": "12345678",
    "title": "Fixture paper title",
    "journal": "Fixture Journal",
    "pubdate": "2026",
    "abstract": "Synthetic abstract used only as a loader/compact fixture.",
}


def mini_corpus() -> Corpus:
    corpus = Corpus(
        targets={"targets": [FIXTURE_TARGET]},
        repurposing={
            "pipeline": "fixture",
            "pchembl_cutoff": 6.0,
            "note": "synthetic fixture — not a medical claim",
            "validation": dict(FIXTURE_VALIDATION),
            "candidates": [dict(FIXTURE_NAMED_CANDIDATE)],
            "per_target": {
                "CHEMBL4050": {
                    "chembl": "CHEMBL4050",
                    "candidates": [dict(FIXTURE_PER_TARGET_CANDIDATE)],
                }
            },
        },
        trials={"trials": [FIXTURE_TRIAL]},
        trials_dk={"trials": []},
        pubmed_recent={"papers": [FIXTURE_PAPER]},
        evidence_weekly={"papers": [dict(FIXTURE_PAPER, pmid="87654321", title="Weekly fixture paper")]},
    )
    collect_whitelist(corpus)
    return corpus


def write_mini_openendo(
    root: Path,
    *,
    latest: str | None = "2026-09-11.json",
    latest_body: str | None = None,
    write_digest: bool = True,
    omit: set[str] | None = None,
) -> Path:
    """Write a tiny wckdboy/openendo-shaped tree under root."""
    omit = omit or set()
    data = root / "docs" / "data"
    weekly = root / "docs" / "research" / "evidence" / "weekly"
    data.mkdir(parents=True)
    weekly.mkdir(parents=True)

    files = {
        "targets": (data / "targets.json", {"targets": [FIXTURE_TARGET]}),
        "repurposing": (
            data / "repurposing_candidates.json",
            {
                "pipeline": "fixture",
                "pchembl_cutoff": 6.0,
                "note": "synthetic fixture",
                "validation": dict(FIXTURE_VALIDATION),
                "candidates": [dict(FIXTURE_NAMED_CANDIDATE)],
                "per_target": {
                    "CHEMBL4050": {
                        "chembl": "CHEMBL4050",
                        "candidates": [dict(FIXTURE_PER_TARGET_CANDIDATE)],
                    }
                },
            },
        ),
        "trials": (data / "trials_global_recruiting.json", {"trials": [FIXTURE_TRIAL]}),
        "trials_dk": (data / "trials_denmark.json", {"trials": []}),
        "pubmed_recent": (data / "pubmed_recent.json", {"papers": [FIXTURE_PAPER]}),
    }
    for key, (path, payload) in files.items():
        if key in omit:
            continue
        path.write_text(json.dumps(payload) + "\n")

    if latest is not None:
        (weekly / "LATEST").write_text(latest_body if latest_body is not None else f"{latest}\n")
        if write_digest:
            (weekly / latest).write_text(
                json.dumps({"papers": [dict(FIXTURE_PAPER, pmid="87654321")]}) + "\n"
            )
    return root
