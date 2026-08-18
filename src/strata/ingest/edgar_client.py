"""Thin HTTP wrapper for SEC EDGAR APIs.

Three endpoints per docs/context.md §5:
1. Company Facts (XBRL)
2. Full-Text Search
3. Submissions index

Respects SEC rate-limit guidance (~10 req/s max — we stay well under
with a 0.15s sleep between calls).
"""

from __future__ import annotations

import time
from typing import Any

import requests

from strata.config import get_settings

# Conservative inter-request delay (seconds).
_REQUEST_DELAY = 0.15

# Module-level timestamp of last request for rate-limiting.
_last_request_time: float = 0.0


def _rate_limit() -> None:
    """Sleep if necessary to stay under SEC rate limits."""
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < _REQUEST_DELAY:
        time.sleep(_REQUEST_DELAY - elapsed)
    _last_request_time = time.time()


def _headers() -> dict[str, str]:
    """Return headers with the required User-Agent."""
    settings = get_settings()
    return {
        "User-Agent": settings.sec_edgar_user_agent,
        "Accept": "application/json",
    }


def _get(url: str) -> Any:
    """Make a GET request with rate-limiting and error handling.

    Returns the parsed JSON response.
    Raises requests.HTTPError on non-200 responses.
    """
    _rate_limit()
    resp = requests.get(url, headers=_headers(), timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_company_facts(cik: str) -> dict:
    """Fetch structured XBRL facts for a company.

    Args:
        cik: 10-digit zero-padded CIK string.

    Returns:
        Full company facts JSON dict.
    """
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    return _get(url)


def get_submissions(cik: str) -> dict:
    """Fetch the filing submissions index for a company.

    Args:
        cik: 10-digit zero-padded CIK string.

    Returns:
        Submissions JSON dict including recent filings.
    """
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    return _get(url)


def search_filings(
    query: str,
    forms: str = "8-K",
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    """Search EDGAR full-text search for filings matching a query.

    Args:
        query: Search term (e.g. '"Item 4.02"').
        forms: Comma-separated form types to filter.
        start_date: Optional start date (YYYY-MM-DD).
        end_date: Optional end date (YYYY-MM-DD).

    Returns:
        Search results JSON dict.
    """
    params = f'q={query}&forms={forms}'
    if start_date and end_date:
        params += f"&dateRange=custom&startdt={start_date}&enddt={end_date}"
    url = f"https://efts.sec.gov/LATEST/search-index?{params}"
    return _get(url)
