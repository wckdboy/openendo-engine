"""Unit tests — no network, no LLM. Run: python -m pytest"""
from discovery_engine.config import CLASSIFICATIONS, CATEGORIES
from discovery_engine.validation import validate_finding


def test_validate_finding_ok():
    f = {
        "claim": "sirolimus has no registered endometriosis trial",
        "classification": "documented-evidence",
        "confidence": "high",
        "sources": [{"type": "nct", "id": "NCT000001", "url": "https://clinicaltrials.gov/study/NCT000001"}],
    }
    allowed = {"pmid": set(), "nct": {"NCT000001"}, "chembl": set()}
    assert validate_finding(f, "research_gap", allowed, 0) == []


def test_validate_finding_bad_classification():
    f = {"claim": "x", "classification": "proven", "sources": []}
    allowed = {"pmid": set(), "nct": set(), "chembl": set()}
    problems = validate_finding(f, "conflict", allowed, 0)
    assert any("classification" in p for p in problems)


def test_validate_finding_invented_source():
    f = {
        "claim": "x",
        "classification": "likely-association",
        "sources": [{"type": "pmid", "id": "99999999"}],
    }
    allowed = {"pmid": {"123"}, "nct": set(), "chembl": set()}
    problems = validate_finding(f, "hypothesis", allowed, 0)
    assert any("whitelist" in p for p in problems)


def test_validate_finding_bad_source_type():
    f = {"claim": "x", "classification": "untested-hypothesis", "sources": [{"type": "doi", "id": "10.1/x"}]}
    allowed = {"pmid": set(), "nct": set(), "chembl": set()}
    problems = validate_finding(f, "hypothesis", allowed, 0)
    assert any("source type" in p for p in problems)


def test_untested_hypothesis_may_have_no_sources():
    f = {
        "claim": "ADORA2B antagonism reduces lesion angiogenesis",
        "classification": "untested-hypothesis",
        "confidence": "medium",
        "sources": [],
        "rationale": "mechanistic plausibility only",
    }
    allowed = {"pmid": set(), "nct": set(), "chembl": set()}
    assert validate_finding(f, "hypothesis", allowed, 0) == []


def test_documented_claim_requires_sources():
    f = {
        "claim": "x is proven",
        "classification": "documented-evidence",
        "confidence": "high",
        "sources": [],
    }
    allowed = {"pmid": set(), "nct": set(), "chembl": set()}
    problems = validate_finding(f, "research_gap", allowed, 0)
    assert any("sources" in p for p in problems)


def test_enums_are_what_the_mission_law_says():
    assert CLASSIFICATIONS == ("documented-evidence", "likely-association", "untested-hypothesis")
    assert set(CATEGORIES) == {"research_gap", "conflict", "repurposing_lead", "hypothesis"}
