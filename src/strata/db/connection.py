"""CockroachDB connection management via psycopg (v3)."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

import psycopg

from strata.config import get_settings


@contextmanager
def get_connection(
    autocommit: bool = True,
) -> Generator[psycopg.Connection, None, None]:
    """Yield a psycopg connection to CockroachDB.

    Args:
        autocommit: If True (default), each statement auto-commits.
                    Set to False for explicit transaction control.
    """
    settings = get_settings()
    conn = psycopg.connect(settings.cockroachdb_url, autocommit=autocommit)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def get_transaction() -> Generator[psycopg.Connection, None, None]:
    """Yield a connection inside a serializable transaction.

    The caller should NOT call conn.commit() — commit happens
    automatically when the context manager exits without error.
    On exception the transaction is rolled back.
    """
    settings = get_settings()
    conn = psycopg.connect(settings.cockroachdb_url, autocommit=False)
    try:
        conn.execute(
            "SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"
        )
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
