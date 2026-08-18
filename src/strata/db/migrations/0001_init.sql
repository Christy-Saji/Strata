-- 0001_init.sql — Phase 1 foundation tables
-- Creates entities and facts_sediment per docs/context.md §4.
-- facts_curated, contradictions_log, curator_runs are Phase 2.

CREATE TABLE IF NOT EXISTS entities (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cik         TEXT UNIQUE NOT NULL,
    name        TEXT NOT NULL,
    ticker      TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS facts_sediment (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id             UUID NOT NULL REFERENCES entities(id),
    fact_key              TEXT NOT NULL,
    fact_value            JSONB NOT NULL,
    fact_text             TEXT NOT NULL,
    embedding             VECTOR(384),
    source_type           TEXT NOT NULL,
    source_url            TEXT NOT NULL,
    filed_at              TIMESTAMPTZ NOT NULL,
    ingested_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_restatement_signal BOOLEAN NOT NULL DEFAULT false,
    confidence            FLOAT NOT NULL DEFAULT 0.8
);

CREATE INDEX IF NOT EXISTS idx_sediment_entity_key_filed
    ON facts_sediment (entity_id, fact_key, filed_at);

-- Note: CockroachDB v25.2+ requires the feature flag
-- feature.vector_index.enabled = true (set by migrate.py before
-- running this file). The USING HNSW clause is optional; omitting
-- it lets CockroachDB choose its default (C-SPANN).
CREATE VECTOR INDEX IF NOT EXISTS idx_sediment_embedding
    ON facts_sediment (embedding);
