"""Validation helpers for engine findings."""
from __future__ import annotations

from .config import CATEGORIES, CLASSIFICATIONS, CONFIDENCES

REQUIRED_FIELDS = ("claim", "classification", "sources")


def validate_finding(f: dict, category: str, allowed: dict, index: int) -> list[str]:
    """Return a list of problems. Empty = finding is valid."""
    problems = []
    for field in REQUIRED_FIELDS:
        if field not in f or f[field] in (None, "", []):
            # sources may legitimately be empty for untested-hypothesis claims
            # (mission law: an untested claim has no citable evidence yet)
            if field == "sources" and f.get("classification") == "untested-hypothesis":
                continue
            problems.append(f"missing '{field}'")
    if f.get("classification") not in CLASSIFICATIONS:
        problems.append(f"classification must be one of {CLASSIFICATIONS}")
    if f.get("confidence") and f["confidence"] not in CONFIDENCES:
        problems.append(f"confidence must be one of {CONFIDENCES}")
    if category not in CATEGORIES:
        problems.append(f"category '{category}' not in {CATEGORIES}")

    sources = f.get("sources") or []
    for src in sources:
        kind = src.get("type")
        sid = str(src.get("id", "")).strip()
        if kind not in ("pmid", "nct", "chembl", "url"):
            problems.append(f"source type '{kind}' not allowed (pmid|nct|chembl|url)")
            continue
        if kind != "url" and sid:
            whitelist = allowed.get(kind, set())
            if sid not in whitelist:
                problems.append(f"source {kind}:{sid} not in loaded data whitelist")
    return problems
