"""Tests for database schema — verifies migrations apply cleanly.

These tests require a live CockroachDB connection. They are skipped
automatically if COCKROACHDB_URL is not set.
"""

from __future__ import annotations

import os
import pytest

# Skip the entire module if no DB credentials are available
pytestmark = pytest.mark.skipif(
    not os.environ.get("COCKROACHDB_URL"),
    reason="COCKROACHDB_URL not set — skipping live DB tests",
)


@pytest.fixture(scope="module")
def db_conn():
    """Provide a live DB connection for the test module."""
    from strata.db.connection import get_connection
    from strata.db.migrate import run_migrations

    # Ensure migrations are applied
    run_migrations()

    with get_connection() as conn:
        yield conn


def test_entities_table_exists(db_conn):
    """Verify the entities table exists with expected columns."""
    rows = db_conn.execute(
        """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'entities'
        ORDER BY ordinal_position
        """
    ).fetchall()

    columns = {row[0]: row[1] for row in rows}
    assert "id" in columns, "entities table missing 'id' column"
    assert "cik" in columns, "entities table missing 'cik' column"
    assert "name" in columns, "entities table missing 'name' column"
    assert "ticker" in columns, "entities table missing 'ticker' column"
    assert "created_at" in columns, "entities table missing 'created_at' column"


def test_facts_sediment_table_exists(db_conn):
    """Verify facts_sediment table exists with expected columns."""
    rows = db_conn.execute(
        """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'facts_sediment'
        ORDER BY ordinal_position
        """
    ).fetchall()

    columns = {row[0]: row[1] for row in rows}

    expected = [
        "id", "entity_id", "fact_key", "fact_value", "fact_text",
        "embedding", "source_type", "source_url", "filed_at",
        "ingested_at", "is_restatement_signal", "confidence",
    ]
    for col in expected:
        assert col in columns, f"facts_sediment table missing '{col}' column"


def test_schema_migrations_table_exists(db_conn):
    """Verify the schema_migrations tracking table exists."""
    rows = db_conn.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'schema_migrations'
        """
    ).fetchall()

    columns = {row[0] for row in rows}
    assert "filename" in columns
    assert "applied_at" in columns


def test_entities_cik_unique_constraint(db_conn):
    """Verify the UNIQUE constraint on entities.cik."""
    rows = db_conn.execute(
        """
        SELECT constraint_name, constraint_type
        FROM information_schema.table_constraints
        WHERE table_name = 'entities'
          AND constraint_type = 'UNIQUE'
        """
    ).fetchall()

    assert len(rows) > 0, "entities table missing UNIQUE constraint on cik"
