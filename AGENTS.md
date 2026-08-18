# AGENTS.md

This file follows the open `AGENTS.md` convention and is read by Codex,
Antigravity, Cursor, and other AGENTS.md-compatible coding agents
operating in this repository. If you are Claude Code specifically, also
read `CLAUDE.md`.

## Read this first, every session, in this order

1. `docs/context.md` — the project spec: architecture, schema, dataset,
   scope. Source of truth for *what* this project is.
2. `docs/context.md` §15 — status log, what's actually been built so far.
3. `docs/prompts/master.md` — the global operating rules (scope
   discipline, memory/status-log discipline, environment, database
   rules, code style, testing, definition-of-done discipline). These
   apply in full to everything below and are **not** repeated here.
4. `docs/prompts/phase-N-*.md` — the specific task for this session.

## Setup commands

This is the canonical copy — `README.md` should just link here, not
maintain a second version.

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

## Notes specific to this file

- `master.md` is where the actual behavioral rules live (scope
  discipline, database rules, code style, etc.) — this file exists for
  setup commands and tool-agnostic pointers, not to restate them.
- If a rule needs to change, change it in `master.md` once. Don't patch
  it here or in `CLAUDE.md` individually — that's exactly the drift this
  split is meant to avoid.
