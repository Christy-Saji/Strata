"""Environment sanity checker.

Usage:
    python scripts/check_env.py

Verifies:
1. All required env vars are present (without printing values).
2. CockroachDB connectivity (SELECT 1).
3. Embedding model loads and can embed a test string.

Does NOT call Groq or SEC EDGAR — those are exercised by the actual
pipeline.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure the project root is on sys.path so we can import strata
_project_root = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(_project_root))


def check_settings() -> bool:
    """Verify that required settings load successfully."""
    print("[1/3] Checking environment configuration...")
    try:
        from strata.config import get_settings
        settings = get_settings()
        print("  ✓ COCKROACHDB_URL is set")
        print("  ✓ SEC_EDGAR_USER_AGENT is set")
        print(f"  ✓ EMBEDDING_MODEL_NAME = {settings.embedding_model_name}")
        if settings.groq_api_key:
            print("  ✓ GROQ_API_KEY is set")
        else:
            print("  ⚠ GROQ_API_KEY is not set (not needed until Phase 2)")
        return True
    except SystemExit as exc:
        print(f"  ✗ {exc}")
        return False


def check_database() -> bool:
    """Verify CockroachDB connectivity with SELECT 1."""
    print("\n[2/3] Checking CockroachDB connectivity...")
    try:
        from strata.db.connection import get_connection
        with get_connection() as conn:
            result = conn.execute("SELECT 1").fetchone()
            if result and result[0] == 1:
                print("  ✓ CockroachDB connection successful (SELECT 1 = 1)")
                return True
            else:
                print("  ✗ Unexpected result from SELECT 1")
                return False
    except Exception as exc:
        print(f"  ✗ CockroachDB connection failed: {exc}")
        return False


def check_embeddings() -> bool:
    """Verify the embedding model loads and produces correct output."""
    print("\n[3/3] Checking embedding model...")
    try:
        from strata.embeddings.local_embedder import embed
        test_text = "Acme Corp reported net income of $50,000,000 for fiscal Q3 2025."
        vector = embed(test_text)
        dim = len(vector)
        print(f"  ✓ Model loaded successfully")
        print(f"  ✓ Test embedding dimension: {dim}")
        if dim != 384:
            print(f"  ⚠ Expected 384 dimensions, got {dim}")
            return False
        print(f"  ✓ Embedding values look valid (first 3: {vector[:3]})")
        return True
    except Exception as exc:
        print(f"  ✗ Embedding model check failed: {exc}")
        return False


def main() -> None:
    """Run all sanity checks."""
    print("=" * 50)
    print("Strata Environment Check")
    print("=" * 50)

    results = {
        "Settings": check_settings(),
        "Database": check_database(),
        "Embeddings": check_embeddings(),
    }

    print("\n" + "=" * 50)
    print("Results")
    print("=" * 50)

    all_passed = True
    for name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}: {name}")
        if not passed:
            all_passed = False

    if all_passed:
        print("\nAll checks passed! ✓")
    else:
        print("\nSome checks failed. Fix the issues above and re-run.")
        sys.exit(1)


if __name__ == "__main__":
    main()
