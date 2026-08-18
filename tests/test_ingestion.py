"""Unit tests for the XBRL parser.

Uses hand-written fixture JSON — no network calls. Verifies the fixed
concept set (NetIncomeLoss, Revenues, Assets) is extracted correctly
into the expected fact_value/fact_text shape.
"""

from __future__ import annotations

import json

import pytest

from strata.ingest.parse_xbrl import parse_company_facts, CONCEPT_MAP


# ---------------------------------------------------------------------------
# Fixture: minimal company facts JSON matching the EDGAR API shape
# ---------------------------------------------------------------------------
FIXTURE_COMPANY_FACTS = {
    "cik": 1234567890,
    "entityName": "TEST CORP",
    "facts": {
        "us-gaap": {
            "NetIncomeLoss": {
                "label": "Net Income (Loss)",
                "description": "Net income or loss",
                "units": {
                    "USD": [
                        {
                            "val": 50000000,
                            "accn": "0001234567-24-000001",
                            "fy": 2024,
                            "fp": "Q3",
                            "form": "10-Q",
                            "filed": "2024-11-01",
                            "end": "2024-09-30",
                        },
                        {
                            "val": -12000000,
                            "accn": "0001234567-25-000002",
                            "fy": 2024,
                            "fp": "Q3",
                            "form": "10-Q/A",
                            "filed": "2025-02-15",
                            "end": "2024-09-30",
                        },
                    ]
                },
            },
            "Revenues": {
                "label": "Revenues",
                "description": "Total revenues",
                "units": {
                    "USD": [
                        {
                            "val": 200000000,
                            "accn": "0001234567-24-000003",
                            "fy": 2024,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2025-03-01",
                            "end": "2024-12-31",
                        },
                    ]
                },
            },
            "Assets": {
                "label": "Assets",
                "description": "Total assets",
                "units": {
                    "USD": [
                        {
                            "val": 500000000,
                            "accn": "0001234567-24-000004",
                            "fy": 2024,
                            "fp": "Q2",
                            "form": "10-Q",
                            "filed": "2024-08-01",
                            "end": "2024-06-30",
                        },
                    ]
                },
            },
        },
        "dei": {},  # empty — no DEI facts in this fixture
    },
}


class TestParseCompanyFacts:
    """Test suite for parse_company_facts()."""

    def test_extracts_all_three_concepts(self):
        """Verify all three concepts (net_income, revenue, total_assets) are extracted."""
        facts = parse_company_facts(FIXTURE_COMPANY_FACTS, "Test Corp")
        fact_keys = {f["fact_key"] for f in facts}
        assert "net_income" in fact_keys
        assert "revenue" in fact_keys
        assert "total_assets" in fact_keys

    def test_correct_fact_count(self):
        """Four entries total: 2 net_income + 1 revenue + 1 total_assets."""
        facts = parse_company_facts(FIXTURE_COMPANY_FACTS, "Test Corp")
        assert len(facts) == 4

    def test_fact_value_shape(self):
        """Each fact_value should be a JSON string with the expected keys."""
        facts = parse_company_facts(FIXTURE_COMPANY_FACTS, "Test Corp")
        for fact in facts:
            value = json.loads(fact["fact_value"])
            assert "value" in value, "fact_value missing 'value' key"
            assert "unit" in value, "fact_value missing 'unit' key"
            assert "fiscal_period" in value, "fact_value missing 'fiscal_period'"
            assert "fiscal_year" in value, "fact_value missing 'fiscal_year'"
            assert "form" in value, "fact_value missing 'form'"

    def test_fact_text_is_descriptive(self):
        """fact_text should be a human-readable sentence with company name."""
        facts = parse_company_facts(FIXTURE_COMPANY_FACTS, "Test Corp")
        for fact in facts:
            assert "Test Corp" in fact["fact_text"]
            assert fact["fact_key"].replace("_", " ") in fact["fact_text"]
            assert "filed" in fact["fact_text"]

    def test_net_income_values(self):
        """Verify the two net_income entries have correct values."""
        facts = parse_company_facts(FIXTURE_COMPANY_FACTS, "Test Corp")
        net_income_facts = [f for f in facts if f["fact_key"] == "net_income"]
        assert len(net_income_facts) == 2

        values = [json.loads(f["fact_value"])["value"] for f in net_income_facts]
        assert 50000000 in values
        assert -12000000 in values

    def test_restatement_signal_on_amendment(self):
        """10-Q/A filing should have is_restatement_signal = True."""
        facts = parse_company_facts(FIXTURE_COMPANY_FACTS, "Test Corp")
        amended = [
            f for f in facts
            if f["source_type"] == "10-Q/A"
        ]
        assert len(amended) == 1
        assert amended[0]["is_restatement_signal"] is True

    def test_original_filing_not_restatement(self):
        """Original 10-Q/10-K filings should not be restatement signals."""
        facts = parse_company_facts(FIXTURE_COMPANY_FACTS, "Test Corp")
        originals = [
            f for f in facts
            if f["source_type"] in ("10-Q", "10-K")
        ]
        for f in originals:
            assert f["is_restatement_signal"] is False

    def test_source_url_format(self):
        """source_url should point to EDGAR filing index."""
        facts = parse_company_facts(FIXTURE_COMPANY_FACTS, "Test Corp")
        for fact in facts:
            assert fact["source_url"].startswith(
                "https://www.sec.gov/Archives/edgar/data/"
            )

    def test_filed_at_is_present(self):
        """Every fact should have a filed_at date."""
        facts = parse_company_facts(FIXTURE_COMPANY_FACTS, "Test Corp")
        for fact in facts:
            assert fact["filed_at"], f"Missing filed_at on {fact['fact_key']}"

    def test_confidence_values(self):
        """Original filings get 0.8, amendments get 0.7."""
        facts = parse_company_facts(FIXTURE_COMPANY_FACTS, "Test Corp")
        for fact in facts:
            if fact["is_restatement_signal"]:
                assert fact["confidence"] == 0.7
            else:
                assert fact["confidence"] == 0.8


class TestConceptMap:
    """Test the concept mapping configuration."""

    def test_all_expected_concepts_present(self):
        """The concept map should include our three target concepts."""
        assert "NetIncomeLoss" in CONCEPT_MAP
        assert "Revenues" in CONCEPT_MAP
        assert "Assets" in CONCEPT_MAP

    def test_revenue_variant_mapped(self):
        """The alternative revenue XBRL tag should also be mapped."""
        assert "RevenueFromContractWithCustomerExcludingAssessedTax" in CONCEPT_MAP
        assert (
            CONCEPT_MAP["RevenueFromContractWithCustomerExcludingAssessedTax"]
            == "revenue"
        )


class TestEmptyInput:
    """Test edge cases with empty/minimal input."""

    def test_empty_facts(self):
        """Empty facts dict should return empty list."""
        result = parse_company_facts({"facts": {}}, "Empty Corp")
        assert result == []

    def test_no_relevant_concepts(self):
        """Facts with irrelevant concepts should return empty list."""
        data = {
            "facts": {
                "us-gaap": {
                    "SomeIrrelevantConcept": {
                        "units": {"USD": [{"val": 100}]}
                    }
                }
            }
        }
        result = parse_company_facts(data, "Irrelevant Corp")
        assert result == []

    def test_missing_val_skipped(self):
        """Entries without a 'val' field should be skipped."""
        data = {
            "cik": 1,
            "facts": {
                "us-gaap": {
                    "NetIncomeLoss": {
                        "units": {
                            "USD": [
                                {"accn": "0001-24-000001", "fy": 2024, "fp": "Q1",
                                 "form": "10-Q", "filed": "2024-05-01"},
                            ]
                        }
                    }
                }
            }
        }
        result = parse_company_facts(data, "No Val Corp")
        assert result == []
