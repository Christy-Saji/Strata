# Strata — Self-Curating Financial Memory for AI Agents

> **This document is the persistent source of truth for the Strata project.**
> It is read by every coding agent (Claude Code, Codex, Antigravity, or any
> other tool) at the start of every session, in every phase, regardless of
> which chat thread it lives in. If something in this document conflicts
> with an instruction given inside a chat, **this document wins unless the
> human operator explicitly says otherwise in writing inside a phase
> prompt.** Keep this file updated as decisions are made — it is not a
> historical record, it is the live spec.

---

## 1. One-liner

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

---

## 2. The problem, precisely

Long-running or multi-agent systems accumulate memory the way a river
accumulates sediment — indiscriminately. Three specific failure modes,
none of which a plain vector database can solve on its own:

1. **Contradiction blindness.** A fact learned on day 1 ("Company X
   reported $50M net income for Q3") and a fact learned on day 40
   ("Company X actually reported a $12M net loss for Q3, per restated
   filing") sit in the vector index as two equally-retrievable neighbors.
   Nothing tells the agent which one is current. Cosine similarity has no
   concept of "supersedes."
2. **Concurrent write corruption.** Two agent processes (or two runs of
   the same agent) write facts about the same entity at roughly the same
   time. A plain vector store has no transactional isolation — this is
   effectively last-write-wins with no guarantee about *which* write wins,
   and no audit trail of the collision. Under real concurrency this
   silently corrupts the memory.
3. **No decay.** Nothing in a standard RAG pipeline distinguishes a fact
   that's been independently reconfirmed ten times from a fact that was
   asserted once by a low-confidence source and never touched again. Both
   retrieve with equal weight forever.

Strata's thesis: **the database itself has to do work here, not just
store vectors.** Serializable ACID transactions are the mechanism that
makes contradiction *resolution* (not just contradiction *detection*)
safe under concurrency. That is the specific reason CockroachDB is the
right tool, not an arbitrary hackathon-sponsor choice.

---

## 3. System architecture

```
                        ┌─────────────────────────────┐
                        │   SEC EDGAR (data source)    │
                        │  XBRL Frames API + Full-Text │
                        │  Search + Filing Index        │
                        └──────────────┬───────────────┘
                                       │  fetch / parse
                                       ▼
                        ┌─────────────────────────────┐
                        │      Ingestion Pipeline       │
                        │  (Python, src/strata/ingest)  │
                        │  - parses XBRL facts           │
                        │  - detects restatement events   │
                        │  - generates local embeddings   │
                        │    (sentence-transformers)      │
                        └──────────────┬───────────────┘
                                       │  INSERT (append-only)
                                       ▼
        ┌───────────────────────────────────────────────────────┐
        │                    CockroachDB Cloud                     │
        │  ┌───────────────┐        ┌───────────────────────┐     │
        │  │ facts_sediment │        │   facts_curated        │     │
        │  │ (immutable log)│──────▶ │ (current-truth view,    │    │
        │  │  + VECTOR col  │  curator│  one row per entity/fact│    │
        │  │                │  writes │  slot, ACID-updated)    │    │
        │  └───────────────┘        └───────────────────────┘     │
        │  ┌───────────────┐        ┌───────────────────────┐     │
        │  │contradictions_ │        │    curator_runs         │    │
        │  │     log        │        │  (audit of every pass)  │    │
        │  └───────────────┘        └───────────────────────┘     │
        └───────────────────────────────┬─────────────────────────┘
                                        │ read/introspect (MCP,
                                        │ read-only) + read/write
                                        │ (driver, transactional)
                                        ▼
                        ┌─────────────────────────────┐
                        │       Curator Agent           │
                        │  (src/strata/curator)          │
                        │  - vector search for candidate  │
                        │    contradictions                │
                        │  - Groq LLM adjudication call     │
                        │  - resolves inside a serializable │
                        │    transaction                     │
                        │  - promotion/demotion scoring       │
                        └──────────────┬───────────────┘
                                       │ demoted facts
                                       ▼
                        ┌─────────────────────────────┐
                        │   AWS S3 (cold archive)       │
                        │   triggered via AWS Lambda      │
                        └─────────────────────────────┘
```

Two agents exist in this system, and they must not be conflated:

- **The Ingestion Agent** — dumb and fast. Its only job is to get facts
  from SEC EDGAR into `facts_sediment` correctly, with embeddings. It does
  not adjudicate truth.
- **The Curator Agent** — the actual point of the project. Periodically
  (Lambda-triggered) walks recent sediment, finds candidate contradictions
  via vector similarity, asks Groq to adjudicate, and writes the
  resolution into `facts_curated` inside a transaction. It also scores
  facts for promotion/demotion and archives cold facts to S3.

---

## 4. Data model

All DDL lives in `docs/prompts/` as it's introduced phase by phase, and
the live schema lives in `src/strata/db/migrations/`. This section is the
conceptual model — treat the migration files as the executable truth.

### `entities`
One row per real-world thing facts are about (a company, identified by
CIK — SEC's Central Index Key). Keeps `facts_sediment` normalized instead
of repeating company names as strings.

| column | type | notes |
|---|---|---|
| `id` | UUID PK | |
| `cik` | TEXT UNIQUE | SEC Central Index Key, zero-padded to 10 digits |
| `name` | TEXT | company name at time of last seen filing |
| `ticker` | TEXT | nullable, not all entities have one |
| `created_at` | TIMESTAMPTZ | |

### `facts_sediment` (append-only, never UPDATE or DELETE)
Every fact any ingestion or agent run ever produced. This is the diary.

| column | type | notes |
|---|---|---|
| `id` | UUID PK | |
| `entity_id` | UUID FK → entities | |
| `fact_key` | TEXT | normalized dimension, e.g. `net_income_q3_2025` |
| `fact_value` | JSONB | value + unit + currency, flexible on purpose |
| `fact_text` | TEXT | human-readable sentence form, embedded for search |
| `embedding` | VECTOR(384) | from sentence-transformers `all-MiniLM-L6-v2` |
| `source_type` | TEXT | `10-K` \| `10-K/A` \| `10-Q` \| `10-Q/A` \| `8-K-4.02` \| `xbrl-frame` |
| `source_url` | TEXT | link to the actual EDGAR filing |
| `filed_at` | TIMESTAMPTZ | SEC filing date (not ingestion date) |
| `ingested_at` | TIMESTAMPTZ | DEFAULT now() |
| `is_restatement_signal` | BOOLEAN | true for `10-K/A`, `10-Q/A`, and Item 4.02 `8-K`s |
| `confidence` | FLOAT | 0–1, set at ingestion, adjusted by curator over time |

Indexes: vector index on `embedding`, btree on `(entity_id, fact_key,
filed_at)`.

### `facts_curated` (the "what do we currently believe" table)
One row per `(entity_id, fact_key)`. This is what a downstream agent
actually queries when it wants an answer, not `facts_sediment`.

| column | type | notes |
|---|---|---|
| `entity_id` | UUID FK | |
| `fact_key` | TEXT | |
| `current_value` | JSONB | |
| `current_sediment_id` | UUID FK → facts_sediment | which sediment row won |
| `status` | TEXT | `active` \| `contested` \| `deprecated` |
| `trust_score` | FLOAT | promotion/demotion score, see §7 |
| `last_curated_at` | TIMESTAMPTZ | |
| PRIMARY KEY | `(entity_id, fact_key)` | |

### `contradictions_log`
Every time the Curator finds two sediment rows that disagree, whether or
not it could resolve them.

| column | type | notes |
|---|---|---|
| `id` | UUID PK | |
| `entity_id` | UUID FK | |
| `fact_key` | TEXT | |
| `sediment_id_a` | UUID FK | |
| `sediment_id_b` | UUID FK | |
| `resolution` | TEXT | `a_wins` \| `b_wins` \| `both_valid_different_context` \| `unresolved` |
| `adjudication_reasoning` | TEXT | raw Groq output, kept for audit |
| `detected_at` | TIMESTAMPTZ | |

### `curator_runs`
Audit log of every Curator pass, used for the MCP self-introspection step
and for the demo dashboard.

| column | type | notes |
|---|---|---|
| `id` | UUID PK | |
| `started_at` / `finished_at` | TIMESTAMPTZ | |
| `sediment_rows_scanned` | INT | |
| `contradictions_found` | INT | |
| `contradictions_resolved` | INT | |
| `facts_promoted` | INT | |
| `facts_demoted` | INT | |
| `facts_archived_to_s3` | INT | |

---

## 5. Dataset: SEC EDGAR

**Why this dataset and not a synthetic one:** restatements are real,
timestamped, public, well-documented contradiction events. Nobody has to
invent fake disagreeing facts — companies genuinely filed one number,
then later filed a legally binding correction. That gives Strata real
ground truth to evaluate against instead of self-graded synthetic noise.

### Endpoints (all free, no API key required)

- **XBRL Company Facts API** — structured, machine-readable financial
  facts per company:
  `https://data.sec.gov/api/xbrl/companyfacts/CIK{10-digit-cik}.json`
  Returns every standardized XBRL concept (e.g. `NetIncomeLoss`,
  `Revenues`) the company has ever reported, tagged by fiscal period and
  filing. This is the primary source of `facts_sediment` rows.

- **XBRL Frames API** — one concept across *all* companies for one period,
  useful for bulk ingestion across many entities at once:
  `https://data.sec.gov/api/xbrl/frames/us-gaap/NetIncomeLoss/USD/CY2024Q3I.json`

- **EDGAR Full-Text Search API** — used to find restatement-signaling
  filings directly:
  `https://efts.sec.gov/LATEST/search-index?q=%22restatement%22&forms=8-K&dateRange=custom`
  Specifically filter for **Item 4.02** 8-Ks — these are filings a company
  is legally required to submit when it concludes previously issued
  financials **should no longer be relied upon**. This is the single
  cleanest, most explicit "this fact is now false" signal available in
  any public dataset. It is effectively pre-labeled contradiction ground
  truth.

- **Filing index / submissions API** — per-company list of all filings
  with type and date, used to pair an original `10-K`/`10-Q` with its
  later `10-K/A`/`10-Q/A` amendment:
  `https://data.sec.gov/submissions/CIK{10-digit-cik}.json`

### Required HTTP header

SEC requires a descriptive `User-Agent` header on every request
identifying the requester (name + contact email), or requests will be
rate-limited or blocked. This must be set in ingestion config — see
`.env.example` in the Phase 1 prompt.

### Seed entity list for the demo (deliberately chosen for restatement history)

Pick ~15–20 companies with a documented restatement in their filing
history so the demo has real contradiction density instead of hoping one
turns up. Do not hardcode this list into ingestion logic — keep it in
`src/strata/ingest/seed_entities.py` as data, so it's easy to swap.
Finding candidates: search EDGAR full-text search for `8-K` filings with
Item 4.02 in the last 3–5 years, take the CIKs.

---

## 6. Curator algorithm (conceptual — implemented in Phase 2+)

1. **Candidate generation.** For each new/unprocessed row in
   `facts_sediment`, run a vector similarity search against existing
   `facts_sediment` rows for the same `entity_id` (and optionally same
   `fact_key`) to find semantic neighbors — candidates for either
   duplication or contradiction.
2. **Adjudication.** For each candidate pair, call Groq with both fact
   texts, their sources, and filing dates, and ask it to classify the
   relationship: `duplicate` / `contradiction` / `unrelated` /
   `legitimate_update` (e.g. Q1 and Q2 numbers are both true, they're just
   different periods — not every difference is a contradiction).
3. **Resolution under transaction.** If `contradiction` or
   `legitimate_update`, open a CockroachDB transaction that:
   - inserts a row into `contradictions_log`,
   - updates (or inserts) the corresponding row in `facts_curated`
     favoring the later-filed / higher-authority source (an amendment
     always outranks an original filing; an Item 4.02 8-K always wins
     over the filing it targets),
   - commits atomically, so a concurrent Curator run (or concurrent
     ingestion write) can't interleave and produce an inconsistent state.
     This is the concrete, demoable reason the project needs
     serializable transactions and not just "a database."
4. **Promotion/demotion scoring.** `trust_score` starts at the
   ingestion-time `confidence` value and is adjusted each Curator pass:
   - `+0.1` (capped at 1.0) if a fact is retrieved and *not* contradicted
     within the lookback window,
   - `-0.3` if a fact loses an adjudication,
   - facts with `trust_score < 0.2` get `status = 'deprecated'` and are
     eligible for cold-archival to S3 (row stays in `facts_sediment`
     forever — only its "current truth" standing changes).
5. **Cold archival.** A scheduled Lambda periodically selects deprecated
   facts older than a retention window, writes them as JSON to S3, and
   marks them `archived = true` in Postgres metadata (the row itself is
   never deleted from `facts_sediment` — S3 is a copy for cheap cold
   storage / demo narrative, not the only copy).

---

## 7. Tech stack

| Layer | Choice | Reasoning |
|---|---|---|
| Language | Python 3.11+ | fastest path for vibe-coding, best library support for both data science and API glue |
| Env management | `venv` + `pip` + `requirements.txt` | no extra tooling to learn, explicit, portable |
| DB driver | `psycopg` (v3, binary) | CockroachDB is PostgreSQL wire-compatible |
| Migrations | plain numbered `.sql` files + a tiny runner script | avoids ORM overhead for a project this size; keeps schema changes reviewable |
| Embeddings | `sentence-transformers` (`all-MiniLM-L6-v2`, 384-dim) run **locally** | zero API cost, no rate limit, deterministic, matches the project's zero-marginal-cost posture |
| LLM inference | Groq API (`llama-3.3-70b-versatile` primary, `openai/gpt-oss-120b` fallback) | free tier, OpenAI-compatible SDK, fast enough for the Curator's adjudication loop |
| Vector store | CockroachDB `VECTOR` column + vector index | satisfies hackathon requirement, avoids running a second database |
| Structured DB queries for the agent | CockroachDB Cloud Managed MCP Server | satisfies hackathon requirement — the Curator agent uses this for read-only self-introspection (e.g. "how many unresolved contradictions exist right now") as part of its own reasoning loop, not just for humans/IDEs |
| Compute for Curator runs | AWS Lambda | event/schedule-triggered, always-free tier (1M req/month) |
| Cold storage | AWS S3 | always-free tier (5GB) |
| Config/secrets | `.env` (never committed) via `python-dotenv` | |

---

## 8. External services — accounts and free-tier constraints

| Service | Free tier | Constraint to respect |
|---|---|---|
| CockroachDB Cloud (Basic/Serverless) | $15/mo credit ≈ 50M Request Units + 10GiB storage, per org | Don't run unbounded backfills; batch ingestion |
| Groq API | No card required; ~30 RPM / ~1,000 requests/day per model (varies by model — check current headers, this changes) | Curator adjudication calls should be batched/rate-aware, not fired per-row unthrottled |
| AWS Lambda | 1M requests + 400,000 GB-seconds/month, permanent | fine for this project's volume |
| AWS S3 | 5GB storage, permanent free tier | cold archive only, not primary storage |
| sentence-transformers | Fully local, no external cost | first run downloads the model (~90MB), cache it |

**Always re-check current limits before relying on exact numbers above —
these programs change. This document should be updated if a limit
changes materially.**

---

## 9. Hackathon requirement mapping (do not lose sight of this)

- **CockroachDB tools used (≥2 required):**
  1. **Distributed Vector Indexing** — semantic contradiction/duplicate
     candidate search over `facts_sediment.embedding`.
  2. **Cloud Managed MCP Server** — the Curator agent queries live
     database state (e.g. counts of unresolved contradictions, sediment
     growth rate) as a tool call within its own reasoning loop, and it's
     also used during development via Claude Code / Codex / Antigravity
     for schema introspection.
- **AWS service used (≥1 required):** AWS Lambda (Curator run
  orchestration) + AWS S3 (cold archive) — both permanently free-tier.
- **The actual judged claim:** memory correctness under concurrent
  writers is only possible because CockroachDB gives serializable ACID
  transactions — a plain vector store cannot make this guarantee. The
  demo must make this concrete (see §10), not just asserted in the
  README.

---

## 10. The demo (design target, not a Phase 1 concern — noted here so
early architecture doesn't accidentally make it impossible)

Two things, side by side:

1. **Correctness-over-time chart.** Ingest a stream of facts with real
   restatement events mixed in (in filing-date order, replayed at demo
   speed). Query `facts_curated` at each point in simulated time on a
   "naive" path (last-write-wins, no curator) vs. the Strata path
   (curator-managed). Plot retrieval accuracy against the actual
   ground-truth restated values over time for both. The naive line should
   visibly degrade; the Strata line should hold.
2. **Concurrency fault-injection.** Fire multiple concurrent ingestion +
   curator processes writing conflicting facts about the same entity at
   the same time, live. Show `contradictions_log` and `facts_curated`
   ending in a consistent state with no lost/corrupted rows, and
   optionally show what happens on a naive (non-transactional) code path
   for contrast.

---

## 11. Repository structure (industrial standard layout)

```
strata/
├── CLAUDE.md
├── AGENTS.md
├── README.md
├── .env.example
├── .gitignore
├── requirements.txt
├── docs/
│   ├── context.md                 ← this file
│   └── prompts/
│       ├── phase-1-foundation.md
│       ├── phase-2-curator.md     ← added when Phase 1 is done
│       ├── phase-3-concurrency-and-aws.md
│       └── phase-4-demo.md
├── src/
│   └── strata/
│       ├── __init__.py
│       ├── config.py               # env/config loading, single source
│       ├── db/
│       │   ├── connection.py
│       │   ├── migrations/
│       │   │   ├── 0001_init.sql
│       │   │   └── ...
│       │   └── migrate.py          # tiny migration runner
│       ├── ingest/
│       │   ├── edgar_client.py     # SEC EDGAR HTTP wrapper
│       │   ├── seed_entities.py
│       │   ├── parse_xbrl.py
│       │   ├── detect_restatements.py
│       │   └── run_ingestion.py    # CLI entrypoint
│       ├── embeddings/
│       │   └── local_embedder.py   # sentence-transformers wrapper
│       ├── curator/
│       │   ├── candidate_search.py
│       │   ├── adjudicate.py       # Groq calls
│       │   ├── resolve.py          # transactional writes
│       │   ├── scoring.py
│       │   └── run_curator.py      # CLI / Lambda entrypoint
│       ├── mcp/
│       │   └── client.py           # CockroachDB MCP server client
│       └── aws/
│           ├── lambda_handler.py
│           └── s3_archive.py
├── infra/
│   └── lambda/                     # deployment packaging, added in Phase 3
├── scripts/
│   └── check_env.py                # sanity-check .env + DB connectivity
├── tests/
│   ├── test_schema.py
│   ├── test_ingestion.py
│   └── test_curator.py
└── data/
    ├── raw/                        # gitignored, SEC responses cache
    └── processed/                  # gitignored
```

---

## 12. Environment variables (documented here, defined in `.env.example` in Phase 1)

| Variable | Purpose |
|---|---|
| `COCKROACHDB_URL` | full connection string from CockroachDB Cloud console |
| `GROQ_API_KEY` | from console.groq.com |
| `SEC_EDGAR_USER_AGENT` | required by SEC, format: `"Your Name your.email@example.com"` |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | for boto3 (Lambda/S3), only needed once Phase 3 starts |
| `AWS_REGION` | e.g. `ap-south-1` |
| `S3_ARCHIVE_BUCKET` | cold archive bucket name |
| `COCKROACHDB_MCP_ENDPOINT` | `https://cockroachlabs.cloud/mcp` |
| `EMBEDDING_MODEL_NAME` | default `all-MiniLM-L6-v2`, overridable |

---

## 13. Glossary

- **Sediment** — a raw, immutable fact as originally learned, never
  modified after insert.
- **Curated fact** — the system's current best belief for a given
  `(entity, fact_key)`, derived from sediment by the Curator.
- **Restatement** — a company's formal correction of previously filed
  financials; the real-world contradiction signal this project is built
  around.
- **Item 4.02 8-K** — an SEC filing type required when a company
  concludes past financials should no longer be relied upon; the
  cleanest available "this was wrong" ground-truth label.
- **Trust score** — a float per curated fact, increased by
  reconfirmation, decreased by lost adjudications, driving
  promotion/demotion.
- **CIK** — SEC's Central Index Key, the stable per-company identifier
  used across all EDGAR APIs.

---

## 14. Non-goals (explicit, to prevent scope creep while vibe-coding)

- This is **not** a general-purpose fraud/trading system. No trade
  execution, no price prediction.
- This is **not** trying to cover every XBRL concept — pick a small,
  fixed set of fact keys (`net_income`, `revenue`, `total_assets` to
  start) and expand only if time allows.
- The Curator does not need to be right 100% of the time — the project's
  claim is that it's **auditable and improvable**, not infallible. Every
  adjudication is logged with reasoning; that's the point.
- No custom frontend framework needed for the first three phases — a
  CLI + a couple of `matplotlib`/`plotly` charts is enough until the demo
  phase.

---

## 15. Status log

Keep this section updated at the end of each phase — one or two lines,
appended, never rewritten. This is how a fresh chat session (with no
memory of previous ones) knows where the project actually stands.

- `[unstarted]` — Phase 0: context and planning complete (this document).
  No code written yet.
- `[2026-08-18]` — Phase 1 (foundation): All code scaffolded and written.
  Repository structure matches spec. 15 seed entities with verified
  Item 4.02 8-K restatement history sourced from real EDGAR data.
  `pyproject.toml` added for src-layout package discovery (not in original
  spec but required for imports to work). `pytest -q` passes: 15 passed,
  4 skipped (schema tests skip without COCKROACHDB_URL). Vector index
  syntax confirmed as `CREATE VECTOR INDEX ... ON table (col)` per
  CockroachDB v25.2+ docs; feature flag
  `feature.vector_index.enabled = true` set in migrate.py.
  **Pending**: live DB migration + EDGAR ingestion run (requires real
  `.env` credentials).
