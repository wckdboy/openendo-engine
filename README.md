# OpenEndo Discovery Engine

AI research-support engine for the [OpenEndo](https://openendo.org) mission —
Stage 4 (Discovery Engine): surface **research gaps, conflicting results,
repurposing leads and testable hypotheses** from the canonical openendo data
layer.

**Every claim is classified** `documented-evidence | likely-association |
untested-hypothesis` and **traced to original sources** (PMID / NCT / ChEMBL /
URL). Research support only — never individual medical advice.

LangSmith-traced from day one: every LLM stage is visible as a trace with
inputs, outputs, latency and cost.

## Mission alignment

- Stage 1 Information → `docs/knowledge` in [wckdboy/openendo](https://github.com/wckdboy/openendo)
- Stage 2 Clinical Trials → `docs/data/trials_*.json` in wckdboy/openendo
- Stage 3 Research Graph → `docs/research` in wckdboy/openendo
- **Stage 4 Discovery Engine → this repo**

The engine reads the canonical data layer (raw.githubusercontent URLs by
default, or a local checkout) and writes machine-readable findings — it never
mutates the data repo.

### Pairing with openendo CHECKPOINT Stage 4

[`CHECKPOINT.md`](https://github.com/wckdboy/openendo/blob/main/CHECKPOINT.md)
in wckdboy/openendo is the living ops log for the **data/research repo**:
weekly data refresh (trials, PubMed) and the M2 evidence digest that updates
`docs/research/evidence/weekly/LATEST`.

This engine is Stage 4 of that same pipeline: it **consumes** those refreshed
artifacts (targets, repurposing candidates, trials, pubmed_recent, weekly
LATEST) and writes findings here. It does not claim CHECKPOINT tasks or write
into wckdboy/openendo. After a data-cadence update, re-run the engine to
re-derive findings from the new LATEST pointer. A failed LATEST fetch omits
weekly evidence only and records a `warnings` entry — it must not silently
empty the rest of the corpus.

## Quick start

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # fill in keys for a live run
python -m discovery_engine run
```

Output: `output/<date>/findings.json` + `output/<date>/report.md`

### Dry-run (no LLM, no network)

Use this to exercise CLI → corpus-skip → report wiring, including in CI:

```bash
python -m discovery_engine run --dry-run
# or: python -m discovery_engine --dry-run
```

Writes a schema-valid skeleton (`findings: []`, `dry_run: true`) under
`output/<date>/`. No `OPENAI_API_KEY` / `LANGSMITH_API_KEY` required.

To exercise the **local loader** without calling the model (still no invented
claims):

```bash
python -m discovery_engine run --dry-run --source local --path ../openendo
```

### Configuration (.env)

Required for a **live** run only. Dry-run needs none of these.

| Var | Required for live run | Meaning |
|---|---|---|
| `OPENAI_API_KEY` | yes | key for the OpenAI-compatible endpoint |
| `OPENAI_BASE_URL` | no (default OrcaRouter) | any OpenAI-compatible `/v1` endpoint |
| `DISCOVERY_MODEL` | no | model name, default `deepseek/deepseek-v4-flash-0731` |
| `LANGSMITH_API_KEY` | recommended | LangSmith API key (tracing; run continues without it) |
| `LANGSMITH_ENDPOINT` | no | e.g. `https://eu.api.smith.langchain.com` (EU) |
| `LANGSMITH_PROJECT` | no | tracing project, default `openendo-discovery-engine` |
| `OPENENDO_SOURCE` | no | `raw` (default) or `local` |
| `OPENENDO_PATH` | if source=`local` | local wckdboy/openendo checkout |

## Findings schema

```json
{
  "id": "OE-2026-09-12-RESE-0001",
  "category": "research_gap | conflict | repurposing_lead | hypothesis",
  "claim": "plain-language claim",
  "classification": "documented-evidence | likely-association | untested-hypothesis",
  "confidence": "high | medium | low",
  "sources": [{"type": "pmid | nct | chembl | url", "id": "...", "url": "..."}],
  "rationale": "why the engine says this",
  "caveats": "limitations / what would change the picture"
}
```

The run document (`findings.json`) also carries `engine_version`, `warnings`
(loader / dry-run notes; empty when healthy), and `dry_run`.

Source-traceability is enforced: the model may only cite identifiers that
actually exist in the loaded data, and the engine drops (and reports) any
finding whose sources fail that whitelist check. Exception per mission law:
`untested-hypothesis` claims may legitimately carry no source yet (no
citable evidence exists — that is precisely why they are hypotheses), so
they are accepted with an empty `sources` list.

## Development

```bash
python -m discovery_engine run --source local --path ../openendo   # local data
python -m discovery_engine run --dry-run                          # offline skeleton
python -m pytest                                                   # tests (no network, no LLM)
```
