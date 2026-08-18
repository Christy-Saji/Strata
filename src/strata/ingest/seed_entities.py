"""Seed entity list for the Strata demo.

Companies deliberately chosen for documented restatement history
(Item 4.02 8-K filings, 10-K/A, or 10-Q/A).  All CIKs verified against
real EDGAR filings.  This list is data, not logic — easy to swap or
extend without touching ingestion code.

Each tuple: (cik_10_digit, company_name, ticker_or_None)
"""

from __future__ import annotations

SEED_ENTITIES: list[tuple[str, str, str | None]] = [
    # Companies with Item 4.02 8-K filings (verified via EDGAR search)
    ("0001702744", "Simply Good Foods Co", "SMPL"),
    ("0001739566", "Utz Brands Inc", "UTZ"),
    ("0001449792", "Pioneer Power Solutions Inc", "PPSI"),
    ("0000771999", "DSS Inc", "DSS"),
    ("0001141197", "PEDEVCO Corp", "PED"),
    ("0001467761", "Minim Inc", "MINM"),
    ("0001770236", "Moving iMAGE Technologies Inc", "MITQ"),
    ("0001703073", "VIVIC Corp", "VIVC"),
    ("0001635077", "Aclarion Inc", "ACON"),
    ("0001131903", "Spectral Capital Corp", "FCCN"),
    ("0001510518", "Genufood Energy Enzymes Corp", "GFOO"),
    ("0001119897", "PCT Ltd", "PCTL"),
    ("0001852707", "Better For You Wellness Inc", "BFYW"),
    ("0000895665", "Clearday Inc", "CLRD"),
    ("0001688126", "Crypto Co", "CRCW"),
]
