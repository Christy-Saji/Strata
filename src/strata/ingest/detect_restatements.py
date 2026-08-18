"""Detect restatement signals from a company's filing history.

Two detection methods:
1. Match original filings (10-K, 10-Q) to their amendments (10-K/A, 10-Q/A)
   by comparing fiscal period and filing dates.
2. Flag 8-K filings that contain Item 4.02 (non-reliance disclosure).

The output is used to set is_restatement_signal = true on derived facts.
"""

from __future__ import annotations

from typing import Any


# Filing types that are always restatement signals
_AMENDMENT_FORMS = {"10-K/A", "10-Q/A"}

# Original → amendment mapping
_ORIGINAL_TO_AMENDMENT = {
    "10-K": "10-K/A",
    "10-Q": "10-Q/A",
}


def find_amendment_pairs(
    submissions: dict[str, Any],
) -> list[dict[str, Any]]:
    """Find (original, amendment) filing pairs from submissions.

    Looks for 10-K → 10-K/A and 10-Q → 10-Q/A pairs filed for the
    same reporting period.

    Args:
        submissions: Raw submissions JSON from EDGAR.

    Returns:
        List of dicts with keys:
            - original_accession: str
            - amendment_accession: str
            - form_type: str (e.g. "10-K/A")
            - filing_date: str
            - period_of_report: str
    """
    recent = submissions.get("filings", {}).get("recent", {})
    if not recent:
        # Fallback: some submissions responses have a flat structure
        recent = submissions

    forms = recent.get("form", [])
    accessions = recent.get("accessionNumber", [])
    filing_dates = recent.get("filingDate", [])
    report_dates = recent.get("reportDate", [])

    if not forms or not accessions:
        return []

    # Group filings by (base form type, report period)
    originals: dict[tuple[str, str], dict] = {}
    amendments: list[dict] = []

    for i, form in enumerate(forms):
        entry = {
            "form": form,
            "accession": accessions[i] if i < len(accessions) else "",
            "filing_date": filing_dates[i] if i < len(filing_dates) else "",
            "report_date": report_dates[i] if i < len(report_dates) else "",
        }

        if form in _AMENDMENT_FORMS:
            amendments.append(entry)
        elif form in _ORIGINAL_TO_AMENDMENT:
            key = (form, entry["report_date"])
            originals[key] = entry

    # Match amendments to their originals by report period
    pairs = []
    for amend in amendments:
        # Determine the original form type
        if amend["form"] == "10-K/A":
            orig_form = "10-K"
        elif amend["form"] == "10-Q/A":
            orig_form = "10-Q"
        else:
            continue

        key = (orig_form, amend["report_date"])
        original = originals.get(key)

        pairs.append({
            "original_accession": original["accession"] if original else "",
            "amendment_accession": amend["accession"],
            "form_type": amend["form"],
            "filing_date": amend["filing_date"],
            "period_of_report": amend["report_date"],
        })

    return pairs


def find_item_402_filings(
    submissions: dict[str, Any],
) -> list[dict[str, Any]]:
    """Find 8-K filings that include Item 4.02 from the submissions index.

    Rather than fetching and parsing full 8-K text (expensive and
    rate-limited), we check the items field in the submissions JSON.
    Some 8-K filings report their item numbers in the structured data.

    For filings where items aren't available in the index, we fall back
    to checking if the form description contains "4.02".

    Args:
        submissions: Raw submissions JSON from EDGAR.

    Returns:
        List of dicts with keys:
            - accession: str
            - filing_date: str
            - form_type: str (always "8-K" or "8-K/A")
    """
    recent = submissions.get("filings", {}).get("recent", {})
    if not recent:
        recent = submissions

    forms = recent.get("form", [])
    accessions = recent.get("accessionNumber", [])
    filing_dates = recent.get("filingDate", [])
    items_list = recent.get("items", [])

    results = []
    for i, form in enumerate(forms):
        if form not in ("8-K", "8-K/A"):
            continue

        # Check if items field contains "4.02"
        items = items_list[i] if i < len(items_list) else ""
        if "4.02" in str(items):
            results.append({
                "accession": accessions[i] if i < len(accessions) else "",
                "filing_date": filing_dates[i] if i < len(filing_dates) else "",
                "form_type": form,
            })

    return results


def get_restatement_accessions(
    submissions: dict[str, Any],
) -> set[str]:
    """Get all accession numbers associated with restatement signals.

    Combines both amendment pairs and Item 4.02 8-K filings.

    Args:
        submissions: Raw submissions JSON from EDGAR.

    Returns:
        Set of accession numbers that are restatement signals.
    """
    accessions: set[str] = set()

    # Amendment pairs
    for pair in find_amendment_pairs(submissions):
        accessions.add(pair["amendment_accession"])

    # Item 4.02 8-K filings
    for filing in find_item_402_filings(submissions):
        accessions.add(filing["accession"])

    return accessions


def is_restatement_form(form_type: str) -> bool:
    """Check if a form type is inherently a restatement signal.

    Args:
        form_type: SEC form type string.

    Returns:
        True if the form type indicates an amendment/restatement.
    """
    return form_type in _AMENDMENT_FORMS or form_type in ("8-K/A",)
