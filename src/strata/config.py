"""Strata configuration — single source of truth for all settings.

This is the ONLY module in the codebase that reads os.environ directly.
Every other module imports settings from here.
"""

from __future__ import annotations

import os
from pathlib import Path
from functools import lru_cache

from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError

# Load .env from the repo root (two levels up from src/strata/)
_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(_ENV_PATH)


class Settings(BaseModel):
    """Validated application settings loaded from environment variables."""

    # Required for Phase 1
    cockroachdb_url: str = Field(
        ...,
        description="CockroachDB Cloud connection string",
    )
    sec_edgar_user_agent: str = Field(
        ...,
        description='SEC EDGAR User-Agent header, format: "Name email@example.com"',
    )
    embedding_model_name: str = Field(
        default="all-MiniLM-L6-v2",
        description="sentence-transformers model name for local embeddings",
    )

    # Optional — not required until later phases
    groq_api_key: str = Field(
        default="",
        description="Groq API key from console.groq.com",
    )
    aws_access_key_id: str = Field(default="", description="AWS access key")
    aws_secret_access_key: str = Field(default="", description="AWS secret key")
    aws_region: str = Field(default="", description="AWS region")
    s3_archive_bucket: str = Field(default="", description="S3 archive bucket name")
    cockroachdb_mcp_endpoint: str = Field(
        default="https://cockroachlabs.cloud/mcp",
        description="CockroachDB Cloud MCP server endpoint",
    )


def _read_env(name: str, default: str | None = None) -> str:
    """Read a single env var, returning default if not set."""
    val = os.environ.get(name, default)
    if val is None:
        return ""
    return val


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load, validate, and cache settings from environment variables.

    Raises a clear error naming the missing variable if a required one
    is absent.
    """
    raw = {
        "cockroachdb_url": _read_env("COCKROACHDB_URL"),
        "sec_edgar_user_agent": _read_env("SEC_EDGAR_USER_AGENT"),
        "embedding_model_name": _read_env("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2"),
        "groq_api_key": _read_env("GROQ_API_KEY", ""),
        "aws_access_key_id": _read_env("AWS_ACCESS_KEY_ID", ""),
        "aws_secret_access_key": _read_env("AWS_SECRET_ACCESS_KEY", ""),
        "aws_region": _read_env("AWS_REGION", ""),
        "s3_archive_bucket": _read_env("S3_ARCHIVE_BUCKET", ""),
        "cockroachdb_mcp_endpoint": _read_env(
            "COCKROACHDB_MCP_ENDPOINT", "https://cockroachlabs.cloud/mcp"
        ),
    }

    # Filter out empty strings for required fields so pydantic raises
    # a clear validation error naming them
    for required_key in ("cockroachdb_url", "sec_edgar_user_agent"):
        if not raw[required_key]:
            raw.pop(required_key)

    try:
        return Settings(**raw)
    except ValidationError as exc:
        missing = [
            err["loc"][0]
            for err in exc.errors()
            if err["type"] == "missing"
        ]
        if missing:
            names = ", ".join(str(m).upper() for m in missing)
            raise SystemExit(
                f"Missing required environment variable(s): {names}\n"
                f"Copy .env.example to .env and fill in real values."
            ) from exc
        raise SystemExit(f"Configuration error:\n{exc}") from exc
