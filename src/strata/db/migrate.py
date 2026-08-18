"""Tiny migration runner for forward-only numbered SQL files.

Tracks applied migrations in a `schema_migrations` table.
Idempotent — safe to run repeatedly.

Usage:
    python -m strata.db.migrate
"""

from __future__ import annotations

import sys
from pathlib import Path

from strata.db.connection import get_connection

_MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def _ensure_schema_migrations_table(conn) -> None:
    """Create the tracking table if it doesn't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            filename    TEXT PRIMARY KEY,
            applied_at  TIMESTAMPTZ DEFAULT now()
        )
    """)


def _get_applied(conn) -> set[str]:
    """Return the set of already-applied migration filenames."""
    cur = conn.execute("SELECT filename FROM schema_migrations")
    return {row[0] for row in cur.fetchall()}


def _get_pending(applied: set[str]) -> list[Path]:
    """Return migration files not yet applied, sorted by name."""
    all_files = sorted(_MIGRATIONS_DIR.glob("*.sql"))
    return [f for f in all_files if f.name not in applied]


def _enable_vector_index(conn) -> None:
    """Enable the vector index feature flag if not already enabled.

    This is a cluster setting and only needs to be done once, but is
    safe to re-run.
    """
    try:
        conn.execute(
            "SET CLUSTER SETTING feature.vector_index.enabled = true"
        )
        print("  ✓ Vector index feature flag enabled")
    except Exception as exc:
        # On CockroachDB Cloud Basic, cluster settings may not be
        # directly settable by the user — the feature may already be
        # enabled by default. Log and continue.
        print(f"  ⚠ Could not set vector index feature flag: {exc}")
        print("    (This may already be enabled on CockroachDB Cloud)")


def run_migrations() -> None:
    """Apply all pending migrations in filename order."""
    with get_connection(autocommit=True) as conn:
        _ensure_schema_migrations_table(conn)
        _enable_vector_index(conn)

        applied = _get_applied(conn)
        pending = _get_pending(applied)

        if not pending:
            print("All migrations already applied.")
            return

        for migration_file in pending:
            print(f"Applying {migration_file.name}...")
            sql = migration_file.read_text(encoding="utf-8")
            conn.execute(sql)
            conn.execute(
                "INSERT INTO schema_migrations (filename) VALUES (%s)",
                (migration_file.name,),
            )
            print(f"  ✓ {migration_file.name} applied")

        print(f"Done — {len(pending)} migration(s) applied.")


if __name__ == "__main__":
    try:
        run_migrations()
    except Exception as exc:
        print(f"Migration failed: {exc}", file=sys.stderr)
        sys.exit(1)
