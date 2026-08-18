"""Parse XBRL company-facts JSON into facts_sediment rows.

Extracts a fixed set of concepts (per docs/context.md §14 — start small,
expand only if time allows):

  XBRL concept            → fact_key
  ─────────────────────────────────────
  NetIncomeLoss            → net_income
  Revenues (+ RevenueFromContractWithCustomerExcludingAssessedTax)
                           → revenue
  Assets                   → total_assets
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

# Map XBRL concept names to our normalized fact_key.
# Some companies report revenue under different XBRL tags — we handle
# the most common variants.
CONCEPT_MAP: dict[str, str] = {
    "NetIncomeLoss": "net_income",
    "Revenues": "revenue",
    "RevenueFromContractWithCustomerExcludingAssessedTax": "revenue",
    "Assets": "total_assets",
}


def _format_value(val: int | float) -> str:
    """Format a numeric value with commas and $ sign for readability."""
    if abs(val) >= 1_000_000:
        return f"${val:,.0f}"
    return f"${val:,.2f}"


def _parse_period(unit_entry: dict[str, Any]) -> tuple[str, str]:
    """Extract fiscal period and year from a unit entry.

    Returns (fiscal_period, fiscal_year) like ("Q3", "2024") or
    ("FY", "2024"). Falls back to raw date strings if the standard
    fields aren't present.
    """
    fp = unit_entry.get("fp", "")
    fy = str(unit_entry.get("fy", ""))

    if not fp:
        # Try to infer from the date range
        end = unit_entry.get("end", "")
        if end:
            fp = "FY"  # default assumption for point-in-time values
            fy = end[:4]

    return fp, fy


def _build_filed_at(unit_entry: dict[str, Any]) -> str | None:
    """Extract the filing date from a unit entry.

    Returns ISO date string or None if not available.
    """
    filed = unit_entry.get("filed")
    if filed:
        return filed
    return None


def parse_company_facts(
    company_facts_json: dict[str, Any],
    company_name: str,
) -> list[dict[str, Any]]:
    """Parse XBRL company facts JSON into a list of fact dicts.

    Each returned dict has keys matching facts_sediment columns:
        - fact_key: str
        - fact_value: dict (will be stored as JSONB)
        - fact_text: str (human-readable, for embedding)
        - source_type: str (e.g. "10-K", "10-Q")
        - source_url: str
        - filed_at: str (ISO date)
        - is_restatement_signal: bool
        - confidence: float

    Args:
        company_facts_json: Raw JSON from the XBRL Company Facts API.
        company_name: Human-readable company name for fact_text.

    Returns:
        List of parsed fact dicts ready for insertion.
    """
    results: list[dict[str, Any]] = []

    facts_data = company_facts_json.get("facts", {})

    # Check both us-gaap and dei taxonomies
    for taxonomy in ("us-gaap", "dei"):
        taxonomy_facts = facts_data.get(taxonomy, {})

        for xbrl_concept, fact_key in CONCEPT_MAP.items():
            concept_data = taxonomy_facts.get(xbrl_concept)
            if concept_data is None:
                continue

            units = concept_data.get("units", {})

            for unit_label, entries in units.items():
                for entry in entries:
                    val = entry.get("val")
                    if val is None:
                        continue

                    form = entry.get("form", "")
                    filed_at = _build_filed_at(entry)
                    if not filed_at:
                        continue

                    fp, fy = _parse_period(entry)
                    accn = entry.get("accn", "")

                    # Build the EDGAR filing URL from accession number
                    accn_nodash = accn.replace("-", "")
                    source_url = (
                        f"https://www.sec.gov/Archives/edgar/data/"
                        f"{company_facts_json.get('cik', '')}/{accn_nodash}/"
                        f"{accn}-index.htm"
                    ) if accn else ""

                    # Determine source_type and restatement signal
                    source_type = form if form else "xbrl-frame"
                    is_restatement = source_type in ("10-K/A", "10-Q/A")

                    # Build fact_value JSONB
                    fact_value = {
                        "value": val,
                        "unit": unit_label,
                        "fiscal_period": fp,
                        "fiscal_year": fy,
                        "form": form,
                    }

                    # Build human-readable fact_text for embedding
                    period_str = f"{fp} {fy}" if fp and fy else fy or "unknown period"
                    fact_text = (
                        f"{company_name} reported {fact_key.replace('_', ' ')} of "
                        f"{_format_value(val)} ({unit_label}) for fiscal "
                        f"{period_str}, per {source_type} filed {filed_at}."
                    )

                    # Amended filings get slightly lower initial
                    # confidence (they'll be re-evaluated by the
                    # Curator).  Original filings start at 0.8.
                    confidence = 0.7 if is_restatement else 0.8

                    results.append({
                        "fact_key": fact_key,
                        "fact_value": json.dumps(fact_value),
                        "fact_text": fact_text,
                        "source_type": source_type,
                        "source_url": source_url,
                        "filed_at": filed_at,
                        "is_restatement_signal": is_restatement,
                        "confidence": confidence,
                    })

    return results
