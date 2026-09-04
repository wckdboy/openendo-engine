"""Load the canonical OpenEndo data layer (read-only).

Source is either raw.githubusercontent.com (default) or a local checkout of
wckdboy/openendo. The engine NEVER writes to the data repo.
"""
from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from .config import RAW_BASE

DATA_FILES = {
    "targets": "docs/data/targets.json",
    "repurposing": "docs/data/repurposing_candidates.json",
    "trials": "docs/data/trials_global_recruiting.json",
    "trials_dk": "docs/data/trials_denmark.json",
    "pubmed_recent": "docs/data/pubmed_recent.json",
    "evidence_weekly": "docs/research/evidence/weekly/LATEST",  # pointer, then real file
}

ABSTRACT_CHAR_CAP = 1500  # keep prompt sizes sane


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

    def identifier_whitelist(self) -> str:
        """Render the whitelist as prompt text: only these IDs may be cited."""
        out = []
        for kind in ("pmid", "nct", "chembl"):
            ids = sorted(self.allowed_ids.get(kind, ()))
            if ids:
                out.append(f"{kind}: {', '.join(ids[:400])}")
        return "\n".join(out)


def _read_json(path: str) -> dict:
    with urllib.request.urlopen(path, timeout=45) as r:
        return json.load(r)


def _load_latest_evidence(source: str, local: Path | None) -> dict:
    """evidence_weekly/LATEST contains the filename of the newest digest."""
    if source == "raw":
        try:
            with urllib.request.urlopen(f"{RAW_BASE}/{DATA_FILES['evidence_weekly']}", timeout=45) as r:
                fname = r.read().decode().strip().splitlines()[0].strip()
        except Exception:
            return {}
        try:
            return _read_json(f"{RAW_BASE}/docs/research/evidence/weekly/{fname}")
        except Exception:
            return {}
    base = local / "docs/research/evidence/weekly"
    if not (base / "LATEST").exists():
        return {}
    fname = (base / "LATEST").read_text().strip().splitlines()[0].strip()
    path = base / fname
    return json.loads(path.read_text()) if path.exists() else {}


def _collect(corpus: Corpus) -> None:
    """Build the identifier whitelist from loaded data."""
    allowed = {"pmid": set(), "nct": set(), "chembl": set()}

    for t in corpus.targets.get("targets", []):
        if t.get("chembl_id"):
            allowed["chembl"].add(t["chembl_id"])
    for key, entries in corpus.repurposing.get("per_target", {}).items():
        allowed["chembl"].add(key) if key.startswith("CHEMBL") else None
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


def load_corpus(source: str = "raw", local_path: str = "") -> Corpus:
    local = Path(local_path).resolve() if local_path else None
    corpus = Corpus()

    if source == "raw":
        for key, rel in DATA_FILES.items():
            try:
                corpus.__dict__[key] = _read_json(f"{RAW_BASE}/{rel}")
            except Exception:
                corpus.__dict__[key] = {}
        # evidence LATEST pointer handled separately (points to a dated file)
        corpus.evidence_weekly = _load_latest_evidence("raw", None)
    else:
        if local is None or not local.exists():
            raise FileNotFoundError(f"local openendo path not found: {local}")
        for key, rel in DATA_FILES.items():
            p = local / rel
            if p.exists():
                corpus.__dict__[key] = json.loads(p.read_text())
            else:
                corpus.__dict__[key] = {}
        corpus.evidence_weekly = _load_latest_evidence("local", local)

    _collect(corpus)
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
        if nct in seen:
            continue
        seen.add(nct)
        lines.append(f"- {nct} [{t.get('phase')}] {t.get('title')} — {t.get('sponsor')} — {', '.join(t.get('countries') or [])[:120]}")
        if len(lines) >= limit:
            break
    return "\n".join(lines) or "(no recruiting trial data)"


def compact_papers(corpus: Corpus, key: str = "evidence_weekly", limit: int = 12) -> str:
    papers = corpus.__dict__.get(key, {}).get("papers", [])
    out = []
    for p in papers[:limit]:
        title = p.get("title", "")
        abstract = (p.get("abstract") or "")[:ABSTRACT_CHAR_CAP]
        out.append(f"- PMID {p.get('pmid')} | {title} | {p.get('journal')} {p.get('pubdate')}\n  {abstract}")
    return "\n\n".join(out) or f"(no {key} papers)"
