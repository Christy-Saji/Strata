"""Ingestion pipeline CLI entrypoint.

Usage:
    python -m strata.ingest.run_ingestion

Workflow:
1. Ensure DB migrations are applied.
2. For each seed entity: upsert into entities, fetch company facts,
   parse the fixed concept set, generate embeddings, insert into
   facts_sediment.
3. Print a summary at the end.
4. Safe to re-run — checks for existing rows before inserting.
"""

from __future__ import annotations

import json
import sys
import time

from strata.config import get_settings
from strata.db.connection import get_connection
from strata.db.migrate import run_migrations
from strata.embeddings.local_embedder import embed_batch
from strata.ingest.edgar_client import get_company_facts, get_submissions
from strata.ingest.parse_xbrl import parse_company_facts
from strata.ingest.detect_restatements import (
    get_restatement_accessions,
    is_restatement_form,
)
from strata.ingest.seed_entities import SEED_ENTITIES


def _upsert_entity(
    conn, cik: str, name: str, ticker: str | None
) -> str:
    """Upsert an entity and return its UUID.

    Uses ON CONFLICT to handle re-runs gracefully.
    """
    row = conn.execute(
        """
        INSERT INTO entities (cik, name, ticker)
        VALUES (%s, %s, %s)
        ON CONFLICT (cik)
        DO UPDATE SET name = EXCLUDED.name, ticker = EXCLUDED.ticker
        RETURNING id
        """,
        (cik, name, ticker),
    ).fetchone()
    return str(row[0])


def _fact_exists(
    conn, entity_id: str, fact_key: str, filed_at: str, source_url: str
) -> bool:
    """Check if this exact fact already exists in sediment.

    Deduplication key: entity_id + fact_key + filed_at + source_url.
    """
    row = conn.execute(
        """
        SELECT 1 FROM facts_sediment
        WHERE entity_id = %s
          AND fact_key = %s
          AND filed_at = %s
          AND source_url = %s
        LIMIT 1
        """,
        (entity_id, fact_key, filed_at, source_url),
    ).fetchone()
    return row is not None


def _insert_facts(
    conn,
    entity_id: str,
    facts: list[dict],
    restatement_accessions: set[str],
) -> tuple[int, int]:
    """Insert parsed facts into facts_sediment with embeddings.

    Returns (inserted_count, restatement_count).
    """
    if not facts:
        return 0, 0

    # Filter out duplicates before doing expensive embedding work
    new_facts = []
    for fact in facts:
        if not _fact_exists(
            conn, entity_id, fact["fact_key"], fact["filed_at"], fact["source_url"]
        ):
            new_facts.append(fact)

    if not new_facts:
        return 0, 0

    # Generate embeddings in batch for efficiency
    texts = [f["fact_text"] for f in new_facts]
    embeddings = embed_batch(texts)

    inserted = 0
    restatement_count = 0

    for fact, embedding in zip(new_facts, embeddings):
        # Check restatement signal: from form type or from known
        # restatement accessions
        is_restatement = (
            fact["is_restatement_signal"]
            or is_restatement_form(fact["source_type"])
        )

        conn.execute(
            """
            INSERT INTO facts_sediment (
                entity_id, fact_key, fact_value, fact_text, embedding,
                source_type, source_url, filed_at,
                is_restatement_signal, confidence
            ) VALUES (
                %s, %s, %s::jsonb, %s, %s::vector,
                %s, %s, %s,
                %s, %s
            )
            """,
            (
                entity_id,
                fact["fact_key"],
                fact["fact_value"],
                fact["fact_text"],
                str(embedding),
                fact["source_type"],
                fact["source_url"],
                fact["filed_at"],
                is_restatement,
                fact["confidence"],
            ),
        )
        inserted += 1
        if is_restatement:
            restatement_count += 1

    return inserted, restatement_count


def run_ingestion() -> None:
    """Run the full ingestion pipeline for all seed entities."""
    # Step 1: ensure migrations are applied
    print("=" * 60)
    print("Strata Ingestion Pipeline")
    print("=" * 60)
    print("\n[1/3] Ensuring database migrations are applied...")
    run_migrations()

    settings = get_settings()

    # Step 2: process each seed entity
    print(f"\n[2/3] Processing {len(SEED_ENTITIES)} seed entities...")
    total_entities = 0
    total_facts = 0
    total_restatements = 0
    skipped_entities: list[str] = []

    with get_connection(autocommit=True) as conn:
        for i, (cik, name, ticker) in enumerate(SEED_ENTITIES, 1):
            print(f"\n--- [{i}/{len(SEED_ENTITIES)}] {name} (CIK {cik}) ---")

            # Upsert entity
            entity_id = _upsert_entity(conn, cik, name, ticker)
            print(f"  Entity ID: {entity_id}")

            # Fetch company facts from EDGAR
            try:
                print("  Fetching company facts from EDGAR...")
                company_facts = get_company_facts(cik)
            except Exception as exc:
                print(f"  ⚠ Could not fetch company facts: {exc}")
                skipped_entities.append(f"{name} (facts: {exc})")
                continue

            # Parse XBRL facts
            facts = parse_company_facts(company_facts, name)
            print(f"  Parsed {len(facts)} fact(s) from XBRL data")

            if not facts:
                print("  ⚠ No relevant XBRL facts found, skipping")
                skipped_entities.append(f"{name} (no XBRL facts)")
                total_entities += 1
                continue

            # Fetch submissions for restatement detection
            restatement_accessions: set[str] = set()
            try:
                print("  Fetching submissions for restatement detection...")
                submissions = get_submissions(cik)
                restatement_accessions = get_restatement_accessions(submissions)
                if restatement_accessions:
                    print(
                        f"  Found {len(restatement_accessions)} "
                        f"restatement-related filing(s)"
                    )
            except Exception as exc:
                print(f"  ⚠ Could not fetch submissions: {exc}")

            # Insert facts with embeddings
            print("  Generating embeddings and inserting facts...")
            inserted, restatement_count = _insert_facts(
                conn, entity_id, facts, restatement_accessions
            )

            total_entities += 1
            total_facts += inserted
            total_restatements += restatement_count

            print(
                f"  ✓ Inserted {inserted} new fact(s) "
                f"({restatement_count} restatement signal(s))"
            )

    # Step 3: summary
    print("\n" + "=" * 60)
    print("Ingestion Summary")
    print("=" * 60)
    print(f"  Entities processed:     {total_entities}/{len(SEED_ENTITIES)}")
    print(f"  Facts inserted:         {total_facts}")
    print(f"  Restatement signals:    {total_restatements}")

    if skipped_entities:
        print(f"\n  Skipped/partial entities ({len(skipped_entities)}):")
        for s in skipped_entities:
            print(f"    - {s}")

    print("\nDone.")


if __name__ == "__main__":
    try:
        run_ingestion()
    except KeyboardInterrupt:
        print("\nIngestion interrupted by user.")
        sys.exit(1)
    except SystemExit:
        raise
    except Exception as exc:
        print(f"\nIngestion failed: {exc}", file=sys.stderr)
        sys.exit(1)
