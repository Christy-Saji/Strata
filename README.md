# Strata — Self-Curating Financial Memory for AI Agents

Strata is a memory layer for AI agents that treats **remembering** and
**being right** as two different problems. Instead of a flat vector store
that silently accumulates stale, duplicate, and contradictory facts,
Strata append-only-logs every fact an agent learns, then runs a background
**Curator agent** that finds contradictions, resolves them under real
database transactions, and demotes what turns out to be wrong — without
ever deleting the paper trail.

The proving ground is **financial facts from SEC filings**, because
finance is one of the few domains where "this fact was true, then it was
formally and traceably un-true" happens constantly, on the record, with
timestamps: **restatements**.

For full architecture, schema, dataset details, and design rationale, see
[docs/context.md](docs/context.md).

## Setup

```bash
# from repo root
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env               # then fill in real values, never commit .env
python scripts/check_env.py        # verifies env vars + DB connectivity
```

Run tests:

```bash
source .venv/bin/activate
pytest -q
```

Run the ingestion CLI (once Phase 1 is complete):

```bash
python -m strata.ingest.run_ingestion
```

Run the curator CLI (once Phase 2 is complete):

```bash
python -m strata.curator.run_curator
```
