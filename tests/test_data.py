"""Data compact helpers, whitelist collection, and loader hardening — no network."""
from __future__ import annotations

import json

import pytest

from discovery_engine.data import (
    ABSTRACT_CHAR_CAP,
    Corpus,
    CorpusLoadError,
    collect_whitelist,
    compact_papers,
    compact_repurposing,
    compact_targets,
    compact_trials,
    load_corpus,
)
from tests.helpers import FIXTURE_PAPER, write_mini_openendo


def test_compact_targets_empty():
    assert compact_targets(Corpus()) == "(no target data)"


def test_compact_targets_fixture(fixture_corpus):
    text = compact_targets(fixture_corpus)
    assert "FKBP4" in text
    assert "CHEMBL4050" in text
    assert "novel=True" in text


def test_compact_targets_respects_limit(fixture_corpus):
    fixture_corpus.targets["targets"] = fixture_corpus.targets["targets"] * 5
    lines = [line for line in compact_targets(fixture_corpus, limit=2).splitlines() if line]
    assert len(lines) == 2


def test_compact_repurposing_empty():
    assert compact_repurposing(Corpus()) == "(no repurposing data)"


def test_compact_repurposing_fixture(fixture_corpus):
    text = compact_repurposing(fixture_corpus)
    assert "pipeline: fixture" in text
    assert "fixture-molecule" in text
    assert "pChEMBL 8.1" in text
    assert "CHEMBL4050" in text


def test_compact_trials_empty():
    assert compact_trials(Corpus()) == "(no recruiting trial data)"


def test_compact_trials_fixture(fixture_corpus):
    text = compact_trials(fixture_corpus)
    assert text.startswith("- NCT000001 [Phase 3] Fixture trial title")
    assert "Fixture Sponsor" in text
    assert "Denmark" in text


def test_compact_trials_skips_missing_nct_and_dedupes():
    corpus = Corpus(
        trials={
            "trials": [
                {"nct_id": None, "title": "no id"},
                {"nct_id": "NCT000001", "phase": "1", "title": "first", "sponsor": "A", "countries": []},
                {"nct_id": "NCT000001", "phase": "2", "title": "dup", "sponsor": "B", "countries": []},
            ]
        }
    )
    text = compact_trials(corpus)
    assert text.count("NCT000001") == 1
    assert "first" in text
    assert "dup" not in text


def test_compact_papers_empty():
    assert compact_papers(Corpus(), "evidence_weekly") == "(no evidence_weekly papers)"


def test_compact_papers_fixture_and_truncation(fixture_corpus):
    long_abstract = "x" * (ABSTRACT_CHAR_CAP + 50)
    fixture_corpus.evidence_weekly["papers"][0]["abstract"] = long_abstract
    text = compact_papers(fixture_corpus, "evidence_weekly")
    assert "PMID 87654321" in text
    assert "Weekly fixture paper" in text
    assert long_abstract not in text
    assert ("x" * ABSTRACT_CHAR_CAP) in text


def test_collect_whitelist_from_fixture(fixture_corpus):
    assert fixture_corpus.allowed_ids["chembl"] == {"CHEMBL4050", "CHEMBL413"}
    assert fixture_corpus.allowed_ids["nct"] == {"NCT000001"}
    assert fixture_corpus.allowed_ids["pmid"] == {"12345678", "87654321"}
    rendered = fixture_corpus.identifier_whitelist()
    assert "pmid:" in rendered
    assert "nct: NCT000001" in rendered
    assert "CHEMBL4050" in rendered


def test_collect_whitelist_gene_key_is_not_treated_as_chembl():
    corpus = Corpus(
        repurposing={
            "per_target": {
                "FKBP4": {"chembl": "CHEMBL4050", "candidates": [{"molecule": "CHEMBL413"}]}
            }
        }
    )
    collect_whitelist(corpus)
    assert corpus.allowed_ids["chembl"] == {"CHEMBL413"}


def test_load_corpus_local_fixture(local_openendo):
    corpus = load_corpus("local", str(local_openendo))
    assert corpus.warnings == []
    assert corpus.targets["targets"][0]["gene"] == "FKBP4"
    assert corpus.evidence_weekly["papers"][0]["pmid"] == "87654321"
    assert "CHEMBL4050" in corpus.allowed_ids["chembl"]
    assert "87654321" in corpus.allowed_ids["pmid"]


def test_latest_missing_does_not_zero_other_datasets(tmp_path):
    root = write_mini_openendo(tmp_path / "openendo", latest=None)
    corpus = load_corpus("local", str(root))
    assert corpus.targets["targets"][0]["chembl_id"] == "CHEMBL4050"
    assert corpus.trials["trials"][0]["nct_id"] == "NCT000001"
    assert corpus.evidence_weekly == {}
    assert any("LATEST pointer missing" in w for w in corpus.warnings)
    assert "CHEMBL4050" in corpus.allowed_ids["chembl"]
    assert "87654321" not in corpus.allowed_ids["pmid"]


def test_latest_points_at_missing_digest(tmp_path):
    root = write_mini_openendo(tmp_path / "openendo", latest="missing.json", write_digest=False)
    corpus = load_corpus("local", str(root))
    assert corpus.pubmed_recent["papers"][0]["pmid"] == FIXTURE_PAPER["pmid"]
    assert corpus.evidence_weekly == {}
    assert any("missing file 'missing.json'" in w for w in corpus.warnings)


def test_latest_path_traversal_is_rejected(tmp_path):
    root = write_mini_openendo(tmp_path / "openendo", latest_body="../outside.json\n", write_digest=False)
    corpus = load_corpus("local", str(root))
    assert corpus.evidence_weekly == {}
    assert any("not a plain filename" in w for w in corpus.warnings)
    assert corpus.targets  # other datasets intact


def test_missing_local_json_warns_per_dataset(tmp_path):
    root = write_mini_openendo(tmp_path / "openendo", omit={"targets"})
    corpus = load_corpus("local", str(root))
    assert corpus.targets == {}
    assert corpus.repurposing["pipeline"] == "fixture"
    assert any(w.startswith("targets: missing local file") for w in corpus.warnings)


def test_local_path_missing_is_fatal(tmp_path):
    with pytest.raises(FileNotFoundError, match="local openendo path not found"):
        load_corpus("local", str(tmp_path / "does-not-exist"))


def test_raw_latest_timeout_does_not_zero_targets(monkeypatch):
    def fake_fetch(url: str, timeout: float = 45) -> bytes:
        if "LATEST" in url or "/evidence/weekly/" in url:
            raise CorpusLoadError(f"timeout after {timeout}s fetching {url}")
        if url.endswith("targets.json"):
            return json.dumps({"targets": [{"gene": "FKBP4", "chembl_id": "CHEMBL4050"}]}).encode()
        return b"{}"

    monkeypatch.setattr("discovery_engine.data._fetch_bytes", fake_fetch)
    corpus = load_corpus("raw")
    assert corpus.targets["targets"][0]["gene"] == "FKBP4"
    assert corpus.evidence_weekly == {}
    assert any("LATEST pointer failed" in w and "other datasets unchanged" in w for w in corpus.warnings)
    assert "CHEMBL4050" in corpus.allowed_ids["chembl"]


def test_raw_all_failures_record_corpus_warning(monkeypatch):
    def fake_fetch(url: str, timeout: float = 45) -> bytes:
        raise CorpusLoadError(f"timeout after {timeout}s fetching {url}")

    monkeypatch.setattr("discovery_engine.data._fetch_bytes", fake_fetch)
    corpus = load_corpus("raw")
    assert corpus.targets == {}
    assert any(w.startswith("targets:") for w in corpus.warnings)
    assert any("LATEST pointer failed" in w for w in corpus.warnings)
    assert any(w.startswith("corpus: every dataset failed") for w in corpus.warnings)
