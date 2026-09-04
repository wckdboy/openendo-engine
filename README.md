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

## Quick start

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # fill in keys
python -m discovery_engine run
```

Output: `output/<date>/findings.json` + `output/<date>/report.md`

### Configuration (.env)

| Var | Meaning |
|---|---|
| `LANGSMITH_API_KEY` | LangSmith API key (tracing) |
| `LANGSMITH_ENDPOINT` | e.g. `https://eu.api.smith.langchain.com` (EU) |
| `LANGSMITH_PROJECT` | tracing project, default `openendo-discovery-engine` |
| `OPENAI_BASE_URL` | any OpenAI-compatible `/v1` endpoint |
| `OPENAI_API_KEY` | key for that endpoint |
| `DISCOVERY_MODEL` | model name, default `deepseek/deepseek-v4-flash-0731` |
| `OPENENDO_SOURCE` | `raw` (default) or `local` |
| `OPENENDO_PATH` | local wckdboy/openendo checkout when source=`local` |

## Findings schema

```json
{
  "id": "OE-2026-09-04-0001",
  "category": "research_gap | conflict | repurposing_lead | hypothesis",
  "claim": "plain-language claim",
  "classification": "documented-evidence | likely-association | untested-hypothesis",
  "confidence": "high | medium | low",
  "sources": [{"type": "pmid | nct | chembl | url", "id": "...", "url": "..."}],
  "rationale": "why the engine says this",
  "caveats": "limitations / what would change the picture"
}
```

Source-traceability is enforced: the model may only cite identifiers that
actually exist in the loaded data, and the engine drops (and reports) any
finding whose sources fail that whitelist check. Exception per mission law:
`untested-hypothesis` claims may legitimately carry no source yet (no
citable evidence exists — that is precisely why they are hypotheses), so
they are accepted with an empty `sources` list.

## Development

```bash
python -m discovery_engine run --source local --path ../openendo   # local data
python -m pytest                                                   # tests
```
