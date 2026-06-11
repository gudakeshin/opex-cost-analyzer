"""tests/test_data_quality.py — P2-15: data-quality propagation."""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# _compute_line_quality_score
# ---------------------------------------------------------------------------

def test_full_quality_score():
    from app.services.ingestion import _compute_line_quality_score

    score = _compute_line_quality_score(
        supplier="Acme Corp",
        description="IT Services",
        category_id="it_software",
        gl_code="4001",
        cost_center="CC-100",
        spend_date="2025-01-15",
    )
    assert score == 1.0


def test_minimal_quality_score_unknown_supplier():
    from app.services.ingestion import _compute_line_quality_score

    score = _compute_line_quality_score(
        supplier="Unknown",
        description="N/A",
        category_id="uncategorized",
        gl_code=None,
        cost_center=None,
        spend_date=None,
    )
    assert score == 0.0


def test_partial_quality_no_gl_or_cc():
    from app.services.ingestion import _compute_line_quality_score

    score = _compute_line_quality_score(
        supplier="Vendor X",
        description="Consulting",
        category_id="professional_services",
        gl_code=None,
        cost_center=None,
        spend_date=None,
    )
    # supplier 0.25 + description 0.20 + category 0.25 = 0.70
    assert score == pytest.approx(0.70, abs=0.01)


def test_quality_score_clamped_to_one():
    from app.services.ingestion import _compute_line_quality_score

    # All fields populated — should not exceed 1.0
    score = _compute_line_quality_score("V", "D", "c_id", "GL", "CC", "2025-01")
    assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# _is_credit_or_reversal
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("amount,description,expected", [
    (-500.0, "Invoice #123",   True),   # negative amount
    (500.0,  "Invoice #123",   False),  # normal positive
    (500.0,  "Credit note #5", True),   # credit keyword
    (500.0,  "Refund for SLA", True),   # refund keyword
    (500.0,  "REVERSAL entry", True),   # reversal keyword (case-insensitive)
    (500.0,  "Annual rebate",  True),   # rebate keyword
    (500.0,  "IT Services Q1", False),  # no keyword
    (0.0,    "Zero-value line",False),  # zero, no keyword
])
def test_credit_or_reversal_detection(amount, description, expected):
    from app.services.ingestion import _is_credit_or_reversal

    assert _is_credit_or_reversal(amount, description) == expected


# ---------------------------------------------------------------------------
# NormalizedSpendLine carries new fields
# ---------------------------------------------------------------------------

def test_normalized_spend_line_default_quality():
    from app.models import NormalizedSpendLine

    line = NormalizedSpendLine(
        row_id=1, supplier="Test", description="Desc",
        amount=1000.0, category_id="it", category_name="IT",
    )
    assert line.data_quality_score == 0.0
    assert line.is_credit_or_reversal is False


def test_normalized_spend_line_explicit_quality():
    from app.models import NormalizedSpendLine

    line = NormalizedSpendLine(
        row_id=1, supplier="Test", description="Desc",
        amount=-200.0, category_id="it", category_name="IT",
        data_quality_score=0.75, is_credit_or_reversal=True,
    )
    assert line.data_quality_score == 0.75
    assert line.is_credit_or_reversal is True


# ---------------------------------------------------------------------------
# _band_factors widens when quality < 1.0
# ---------------------------------------------------------------------------

def test_band_factors_full_quality():
    from app.skills.engine.savings import _band_factors

    low, high = _band_factors(0.65, 0.70, 1.0)
    assert low == pytest.approx(0.80, abs=0.01)
    assert high == pytest.approx(1.20, abs=0.01)


def test_band_factors_low_quality_widens():
    from app.skills.engine.savings import _band_factors

    low_q, high_q = _band_factors(0.65, 0.70, 0.50)
    low_full, high_full = _band_factors(0.65, 0.70, 1.0)

    assert low_q < low_full, "Low band should shrink when quality is low"
    assert high_q > high_full, "High band should grow when quality is low"


def test_band_factors_zero_quality_clamped():
    from app.skills.engine.savings import _band_factors

    low, high = _band_factors(0.65, 0.70, 0.0)
    assert low >= 0.55
    assert high <= 1.55


# ---------------------------------------------------------------------------
# savings_modeler records portfolio quality in summary
# ---------------------------------------------------------------------------

def test_savings_modeler_portfolio_quality_in_summary():
    from app.models import NormalizedSpendLine
    from app.skills.engine.savings import savings_modeler

    # High-quality lines
    lines = [
        NormalizedSpendLine(
            row_id=i, supplier="VendorA", description="IT",
            amount=1_000_000.0, category_id="it_software",
            category_name="IT Software", data_quality_score=0.90,
            is_credit_or_reversal=False,
        )
        for i in range(5)
    ]

    result = savings_modeler(
        value_bridge_raw={"raw_rows": []},
        root_cause_outputs={"root_cause_findings": []},
        spend_lines=lines,
    )
    summary = result["summary"]
    assert "portfolio_data_quality_score" in summary
    assert summary["portfolio_data_quality_score"] == pytest.approx(0.90, abs=0.01)
    assert summary["credit_or_reversal_lines_excluded"] == 0


def test_savings_modeler_excludes_credit_lines():
    from app.models import NormalizedSpendLine
    from app.skills.engine.savings import savings_modeler

    lines = [
        NormalizedSpendLine(
            row_id=1, supplier="Vendor", description="Service",
            amount=500_000.0, category_id="it", category_name="IT",
            data_quality_score=0.80, is_credit_or_reversal=False,
        ),
        NormalizedSpendLine(
            row_id=2, supplier="Vendor", description="Credit note",
            amount=-10_000.0, category_id="it", category_name="IT",
            data_quality_score=0.40, is_credit_or_reversal=True,
        ),
    ]

    result = savings_modeler(
        value_bridge_raw={"raw_rows": []},
        root_cause_outputs={"root_cause_findings": []},
        spend_lines=lines,
    )
    summary = result["summary"]
    assert summary["credit_or_reversal_lines_excluded"] == 1
    # Portfolio quality should only reflect the non-credit line
    assert summary["portfolio_data_quality_score"] == pytest.approx(0.80, abs=0.01)


def test_savings_modeler_low_quality_note():
    from app.models import NormalizedSpendLine
    from app.skills.engine.savings import savings_modeler

    lines = [
        NormalizedSpendLine(
            row_id=i, supplier="Unknown", description="N/A",
            amount=100.0, category_id="uncategorized",
            category_name="Other", data_quality_score=0.20,
            is_credit_or_reversal=False,
        )
        for i in range(3)
    ]

    result = savings_modeler(
        value_bridge_raw={"raw_rows": []},
        root_cause_outputs={"root_cause_findings": []},
        spend_lines=lines,
    )
    summary = result["summary"]
    assert summary["confidence_band_quality_note"] is not None
    assert "widened" in summary["confidence_band_quality_note"].lower()
