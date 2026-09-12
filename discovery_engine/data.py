"""Load the canonical OpenEndo data layer (read-only).

Source is either raw.githubusercontent.com (default) or a local checkout of
wckdboy/openendo. The engine NEVER writes to the data repo.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from .config import FETCH_TIMEOUT_SEC, RAW_BASE, USER_AGENT

JSON_FILES = {
    "targets": "docs/data/targets.json",
    "repurposing": "docs/data/repurposing_candidates.json",
    "trials": "docs/data/trials_global_recruiting.json",
    "trials_dk": "docs/data/trials_denmark.json",
    "pubmed_recent": "docs/data/pubmed_recent.json",
}

# Kept for callers that still iterate the original map. LATEST is a pointer,
# not JSON — load it via _load_latest_evidence, never as a dataset blob.
DATA_FILES = {
    **JSON_FILES,
    "evidence_weekly": "docs/research/evidence/weekly/LATEST",
}

EVIDENCE_WEEKLY_DIR = "docs/research/evidence/weekly"
EVIDENCE_LATEST = f"{EVIDENCE_WEEKLY_DIR}/LATEST"

ABSTRACT_CHAR_CAP = 1500  # keep prompt sizes sane


class CorpusLoadError(Exception):
    """A single dataset failed to load. Other datasets may still be usable."""


@dataclass
class Corpus:
    """Everything the engine reasons over, with identifier whitelists."""

    targets: dict = field(default_factory=dict)
    repurposing: dict = field(default_factory=dict)
    trials: dict = field(default_factory=dict)
    trials_dk: dict = field(default_factory=dict)
    pubmed_recent: dict = field(default_factory=dict)
    evidence_weekly: dict = field(default_factory=dict)
    allowed_ids: dict = field(default_factory=dict)  # kind -> set of ids
    warnings: list[str] = field(default_factory=list)

    def identifier_whitelist(self) -> str:
        """Render the whitelist as prompt text: only these IDs may be cited."""
        out = []
        for kind in ("pmid", "nct", "chembl"):
            ids = sorted(self.allowed_ids.get(kind, ()))
            if ids:
                out.append(f"{kind}: {', '.join(ids[:400])}")
        return "\n".join(out)

    def warn(self, message: str) -> None:
        self.warnings.append(message)


def _fetch_bytes(url: str, timeout: float = FETCH_TIMEOUT_SEC) -> bytes:
    """GET url with a hard timeout and a clear error on failure."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except TimeoutError as exc:
        raise CorpusLoadError(f"timeout after {timeout}s fetching {url}") from exc
    except urllib.error.HTTPError as exc:
        raise CorpusLoadError(f"HTTP {exc.code} fetching {url}") from exc
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, TimeoutError) or "timed out" in str(reason).lower():
            raise CorpusLoadError(f"timeout after {timeout}s fetching {url}") from exc
        raise CorpusLoadError(f"failed to fetch {url}: {reason}") from exc


def _parse_json_object(raw: bytes | str, *, label: str) -> dict:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CorpusLoadError(f"{label}: invalid JSON ({exc.msg})") from exc
    if not isinstance(data, dict):
        raise CorpusLoadError(f"{label}: expected a JSON object, got {type(data).__name__}")
    return data


def _read_json_url(url: str, timeout: float = FETCH_TIMEOUT_SEC) -> dict:
    return _parse_json_object(_fetch_bytes(url, timeout=timeout), label=url)


def _parse_latest_pointer(text: str) -> str:
    """LATEST must be a single filename, not a path."""
    stripped = text.strip()
    if not stripped:
        raise CorpusLoadError("evidence_weekly: LATEST pointer is empty")
    fname = stripped.splitlines()[0].strip()
    if not fname:
        raise CorpusLoadError("evidence_weekly: LATEST pointer is empty")
    if fname in {".", ".."} or "/" in fname or "\\" in fname:
        raise CorpusLoadError(
            f"evidence_weekly: LATEST pointer is not a plain filename: {fname!r}"
        )
    return fname


def _load_latest_evidence(
    source: str,
    local: Path | None,
    timeout: float = FETCH_TIMEOUT_SEC,
) -> tuple[dict, list[str]]:
    """Resolve evidence_weekly/LATEST to the newest digest.

    Failures return ({}, warnings) so the rest of the corpus stays loaded.
    """
    if source == "raw":
        pointer_url = f"{RAW_BASE}/{EVIDENCE_LATEST}"
        try:
            fname = _parse_latest_pointer(_fetch_bytes(pointer_url, timeout=timeout).decode())
        except CorpusLoadError as exc:
            return {}, [
                f"evidence_weekly: LATEST pointer failed ({exc}); "
                "weekly evidence omitted, other datasets unchanged"
            ]
        except Exception as exc:
            return {}, [
                f"evidence_weekly: LATEST pointer failed ({exc}); "
                "weekly evidence omitted, other datasets unchanged"
            ]
        digest_url = f"{RAW_BASE}/{EVIDENCE_WEEKLY_DIR}/{fname}"
        try:
            return _read_json_url(digest_url, timeout=timeout), []
        except CorpusLoadError as exc:
            return {}, [
                f"evidence_weekly: LATEST points to {fname!r} but the digest failed "
                f"({exc}); weekly evidence omitted, other datasets unchanged"
            ]

    assert local is not None
    pointer = local / EVIDENCE_LATEST
    if not pointer.exists():
        return {}, [
            f"evidence_weekly: LATEST pointer missing at {pointer}; "
            "weekly evidence omitted, other datasets unchanged"
        ]
    try:
        fname = _parse_latest_pointer(pointer.read_text())
    except CorpusLoadError as exc:
        return {}, [
            f"evidence_weekly: LATEST pointer unreadable ({exc}); "
            "weekly evidence omitted, other datasets unchanged"
        ]
    path = local / EVIDENCE_WEEKLY_DIR / fname
    if not path.exists():
        return {}, [
            f"evidence_weekly: LATEST points to missing file {fname!r}; "
            "weekly evidence omitted, other datasets unchanged"
        ]
    try:
        return _parse_json_object(path.read_text(), label=str(path)), []
    except CorpusLoadError as exc:
        return {}, [
            f"evidence_weekly: digest {fname!r} failed ({exc}); "
            "weekly evidence omitted, other datasets unchanged"
        ]


def collect_whitelist(corpus: Corpus) -> None:
    """Build the identifier whitelist from loaded data."""
    allowed = {"pmid": set(), "nct": set(), "chembl": set()}

    for t in corpus.targets.get("targets", []):
        if t.get("chembl_id"):
            allowed["chembl"].add(t["chembl_id"])
    for key, entries in corpus.repurposing.get("per_target", {}).items():
        if key.startswith("CHEMBL"):
            allowed["chembl"].add(key)
        for c in entries.get("candidates", []):
            if c.get("molecule"):
                allowed["chembl"].add(c["molecule"])
    for trial_list in (corpus.trials.get("trials", []), corpus.trials_dk.get("trials", [])):
        for t in trial_list:
            if t.get("nct_id"):
                allowed["nct"].add(t["nct_id"])
    for paper_list in (corpus.pubmed_recent.get("papers", []), corpus.evidence_weekly.get("papers", [])):
        for p in paper_list:
            if p.get("pmid"):
                allowed["pmid"].add(str(p["pmid"]))
    corpus.allowed_ids = allowed


def load_corpus(
    source: str = "raw",
    local_path: str = "",
    *,
    timeout: float = FETCH_TIMEOUT_SEC,
) -> Corpus:
    """Load datasets independently so one failure cannot silently empty the rest."""
    local = Path(local_path).resolve() if local_path else None
    corpus = Corpus()

    if source == "raw":
        for key, rel in JSON_FILES.items():
            url = f"{RAW_BASE}/{rel}"
            try:
                setattr(corpus, key, _read_json_url(url, timeout=timeout))
            except CorpusLoadError as exc:
                setattr(corpus, key, {})
                corpus.warn(f"{key}: {exc}")
        evidence, ev_warnings = _load_latest_evidence("raw", None, timeout=timeout)
        corpus.evidence_weekly = evidence
        for w in ev_warnings:
            corpus.warn(w)
    else:
        if local is None or not local.exists():
            raise FileNotFoundError(f"local openendo path not found: {local}")
        for key, rel in JSON_FILES.items():
            path = local / rel
            if not path.exists():
                setattr(corpus, key, {})
                corpus.warn(f"{key}: missing local file {path}")
                continue
            try:
                setattr(corpus, key, _parse_json_object(path.read_text(), label=str(path)))
            except CorpusLoadError as exc:
                setattr(corpus, key, {})
                corpus.warn(f"{key}: {exc}")
        evidence, ev_warnings = _load_latest_evidence("local", local, timeout=timeout)
        corpus.evidence_weekly = evidence
        for w in ev_warnings:
            corpus.warn(w)

    if all(
        not getattr(corpus, key)
        for key in (*JSON_FILES, "evidence_weekly")
    ):
        corpus.warn("corpus: every dataset failed or was empty — findings will have no whitelist")

    collect_whitelist(corpus)
    return corpus


def compact_targets(corpus: Corpus, limit: int = 60) -> str:
    """One line per target: gene, CHEMBL, name, mechanisms, max_phase, novel."""
    rows = []
    for t in corpus.targets.get("targets", [])[:limit]:
        rows.append(
            f"- {t.get('gene')} ({t.get('chembl_id')}) {t.get('name')} — "
            f"mechanisms={t.get('mechanisms')}, max_phase={t.get('max_phase')}, novel={t.get('novel')}"
        )
    return "\n".join(rows) or "(no target data)"


def compact_repurposing(corpus: Corpus) -> str:
    d = corpus.repurposing
    if not d:
        return "(no repurposing data)"
    out = [f"pipeline: {d.get('pipeline')} · pchembl cutoff {d.get('pchembl_cutoff')}",
           f"note: {d.get('note')}"]
    for gene, entry in sorted(d.get("per_target", {}).items()):
        cands = entry.get("candidates", [])
        if cands:
            names = ", ".join(f"{c.get('name') or c.get('molecule')} (pChEMBL {c.get('pchembl')}, phase {c.get('phase')})" for c in cands)
            out.append(f"- {gene} ({entry.get('chembl')}): {names}")
    return "\n".join(out) or "(no candidates)"


def compact_trials(corpus: Corpus, limit: int = 40) -> str:
    lines = []
    seen = set()
    for t in corpus.trials.get("trials", []):
        nct = t.get("nct_id")
        if not nct or nct in seen:
            continue
        seen.add(nct)
        lines.append(f"- {nct} [{t.get('phase')}] {t.get('title')} — {t.get('sponsor')} — {', '.join(t.get('countries') or [])[:120]}")
        if len(lines) >= limit:
            break
    return "\n".join(lines) or "(no recruiting trial data)"


def compact_papers(corpus: Corpus, key: str = "evidence_weekly", limit: int = 12) -> str:
    dataset = getattr(corpus, key, {}) if hasattr(corpus, key) else {}
    papers = dataset.get("papers", []) if isinstance(dataset, dict) else []
    if not isinstance(papers, list):
        papers = []
    out = []
    for p in papers[:limit]:
        title = p.get("title", "")
        abstract = (p.get("abstract") or "")[:ABSTRACT_CHAR_CAP]
        out.append(f"- PMID {p.get('pmid')} | {title} | {p.get('journal')} {p.get('pubdate')}\n  {abstract}")
    return "\n\n".join(out) or f"(no {key} papers)"
