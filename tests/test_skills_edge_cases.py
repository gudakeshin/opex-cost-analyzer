"""T4-2: Edge case tests for all FP&A skills.

Validates graceful degradation (not crashes) for:
- Empty spend list
- All-zero amounts
- Negative amounts
- Missing fiscal_period on all lines
- Missing payment_terms_days on all lines
- Single supplier (HHI = 1.0)

Each skill must return a structured dict (possibly with *_available = False)
rather than raising ZeroDivisionError, KeyError, or any other exception.
"""
from __future__ import annotations

from typing import Any, Dict, List

import pytest

from app.models import NormalizedSpendLine
from app.skills import engine


# ---------------------------------------------------------------------------
# Test data helpers
# ---------------------------------------------------------------------------

def _line(
    row_id: int = 1,
    supplier: str = "Vendor",
    category_id: str = "IT",
    category_name: str = "IT",
    amount: float = 100.0,
    amount_type: str = "actual",
    spend_date: str = "2025-01-15",
    fiscal_period: str | None = "2025-01",
    payment_terms_days: int | None = 30,
    currency: str = "USD",
    fx_rate: float = 1.0,
) -> NormalizedSpendLine:
    return NormalizedSpendLine(
        row_id=row_id,
        supplier=supplier,
        description="Test",
        category_id=category_id,
        category_name=category_name,
        amount=amount,
        spend_date=spend_date,
        fiscal_period=fiscal_period,
        amount_type=amount_type,
        currency=currency,
        fx_rate_to_reporting=fx_rate,
        amount_reporting=amount * fx_rate,
        payment_terms_days=payment_terms_days,
    )


def _budget_line(row_id: int, category_id: str, amount: float) -> NormalizedSpendLine:
    return _line(row_id=row_id, category_id=category_id, amount=amount, amount_type="budget")


# ---------------------------------------------------------------------------
# TestEdgeCases — spend_profiler
# ---------------------------------------------------------------------------

class TestSpendProfilerEdgeCases:
    """spend_profiler must never raise for any input."""

    def test_empty_list(self):
        result = engine.spend_profiler([])
        # Empty input should return a valid dict with zero total spend
        assert isinstance(result, dict)
        assert result.get("total_spend", 0.0) == 0.0

    def test_all_zero_amounts(self):
        lines = [_line(row_id=i, amount=0.0) for i in range(5)]
        result = engine.spend_profiler(lines)
        assert isinstance(result, dict)
        assert result.get("total_spend") == pytest.approx(0.0)

    def test_negative_amounts_no_crash(self):
        """Negative amounts (credit notes / reversals) must not crash."""
        lines = [
            _line(row_id=1, amount=-50_000.0),
            _line(row_id=2, amount=100_000.0),
        ]
        result = engine.spend_profiler(lines)
        assert isinstance(result, dict)
        assert "category_profile" in result

    def test_hhi_single_supplier(self):
        """Single supplier → HHI = 1.0, flag = 'high'."""
        lines = [
            _line(row_id=1, supplier="Sole", category_id="SW", category_name="Software", amount=500_000.0),
            _line(row_id=2, supplier="Sole", category_id="SW", category_name="Software", amount=500_000.0),
        ]
        result = engine.spend_profiler(lines)
        profiles = result.get("category_profile", [])
        assert profiles, "Expected at least one category profile"
        sw = next((p for p in profiles if p["category_id"] == "SW"), None)
        assert sw is not None
        assert sw.get("hhi") == pytest.approx(1.0, abs=0.001)
        assert sw.get("concentration_flag") == "high"

    def test_hhi_multi_supplier_competitive(self):
        """Equal-share 4-supplier split → HHI = 0.25 (exactly at moderate boundary)."""
        lines = [
            _line(row_id=i + 1, supplier=f"V{i}", category_id="SW", category_name="SW", amount=25_000.0)
            for i in range(4)
        ]
        result = engine.spend_profiler(lines)
        sw = next((p for p in result.get("category_profile", []) if p["category_id"] == "SW"), None)
        assert sw is not None
        # HHI = 4 * (0.25)^2 = 0.25 (boundary between "moderate" and "high")
        assert sw.get("hhi") == pytest.approx(0.25, abs=0.01)


# ---------------------------------------------------------------------------
# TestEdgeCases — bva_analyzer
# ---------------------------------------------------------------------------

class TestBvAAnalyzerEdgeCases:
    """bva_analyzer must degrade gracefully for edge inputs."""

    def test_empty_list(self):
        result = engine.bva_analyzer([])
        assert result.get("bva_available") is False

    def test_actuals_only_no_budget(self):
        lines = [_line(row_id=i + 1, amount_type="actual", amount=50_000.0) for i in range(3)]
        result = engine.bva_analyzer(lines)
        assert result.get("bva_available") is False

    def test_budget_only_no_actuals(self):
        """Budget-only data: BvA runs but total actual spend is zero (all under budget)."""
        lines = [_line(row_id=i + 1, amount_type="budget", amount=50_000.0) for i in range(3)]
        result = engine.bva_analyzer(lines)
        # Engine produces a valid BvA with zero actual spend — not an error state
        assert result.get("bva_available") is True
        assert result.get("total_actual", 0.0) == 0.0

    def test_zero_budget_no_crash(self):
        """If budget = 0, variance_pct could be division by zero — must not raise."""
        lines = [
            _line(row_id=1, amount=50_000.0, amount_type="actual"),
            _budget_line(row_id=2, category_id="IT", amount=0.0),
        ]
        result = engine.bva_analyzer(lines)
        assert isinstance(result, dict)

    def test_on_budget_category(self):
        """Actual == Budget → flag must be 'on_budget', variance must be 0."""
        lines = [
            _line(row_id=1, amount=100_000.0, amount_type="actual"),
            _budget_line(row_id=2, category_id="IT", amount=100_000.0),
        ]
        result = engine.bva_analyzer(lines)
        if result.get("bva_available"):
            variances = {v["category_id"]: v for v in result.get("variances", [])}
            it = variances.get("IT", {})
            assert it.get("flag") == "on_budget"
            assert abs(it.get("total_variance", 99)) < 1.0


# ---------------------------------------------------------------------------
# TestEdgeCases — temporal_analyzer
# ---------------------------------------------------------------------------

class TestTemporalAnalyzerEdgeCases:
    """temporal_analyzer must return temporal_available=False gracefully for sparse data."""

    def test_empty_list(self):
        result = engine.temporal_analyzer([])
        assert result.get("temporal_available") is False

    def test_no_fiscal_period_set(self):
        """Lines without fiscal_period → cannot group by period → temporal_available=False."""
        lines = [_line(row_id=i + 1, fiscal_period=None, amount=50_000.0) for i in range(5)]
        result = engine.temporal_analyzer(lines)
        assert result.get("temporal_available") is False

    def test_single_period_not_available(self):
        """Only 1 distinct fiscal_period → temporal_available must be False."""
        lines = [
            _line(row_id=1, fiscal_period="2025-01", amount=50_000.0),
            _line(row_id=2, fiscal_period="2025-01", amount=30_000.0),
        ]
        result = engine.temporal_analyzer(lines)
        assert result.get("temporal_available") is False

    def test_two_periods_available(self):
        lines = [
            _line(row_id=1, fiscal_period="2025-01", amount=50_000.0),
            _line(row_id=2, fiscal_period="2025-02", amount=60_000.0),
        ]
        result = engine.temporal_analyzer(lines)
        assert result.get("temporal_available") is True

    def test_cagr_none_for_two_periods(self):
        """CAGR requires ≥3 periods; must be None for 2."""
        lines = [
            _line(row_id=1, fiscal_period="2025-01", amount=50_000.0),
            _line(row_id=2, fiscal_period="2025-02", amount=60_000.0),
        ]
        result = engine.temporal_analyzer(lines)
        assert result.get("cagr_pct") is None

    def test_ttm_arr_for_12_periods(self):
        """With ≥12 periods, arr_basis must be 'TTM'."""
        lines = [
            _line(row_id=i + 1, fiscal_period=f"2024-{i + 1:02d}", amount=100_000.0)
            for i in range(12)
        ]
        result = engine.temporal_analyzer(lines)
        assert result.get("arr_basis") == "TTM"
        # TTM = 12 * 100k = 1_200_000
        assert result.get("annualized_run_rate") == pytest.approx(1_200_000.0, rel=0.01)

    def test_arr_basis_3m_for_less_than_12_periods(self):
        """With < 12 periods, arr_basis must be '3M_extrapolated'."""
        lines = [
            _line(row_id=i + 1, fiscal_period=f"2025-0{i + 1}", amount=100_000.0)
            for i in range(3)
        ]
        result = engine.temporal_analyzer(lines)
        assert result.get("arr_basis") == "3M_extrapolated"


# ---------------------------------------------------------------------------
# TestEdgeCases — payment_terms_optimizer
# ---------------------------------------------------------------------------

class TestPaymentTermsOptimizerEdgeCases:
    """payment_terms_optimizer must handle missing terms gracefully."""

    def test_empty_list(self):
        result = engine.payment_terms_optimizer([])
        assert isinstance(result, dict)
        assert result.get("payment_terms_available") is False or result.get("total_working_capital_release", 0.0) == 0.0

    def test_no_payment_terms_set(self):
        """All lines have payment_terms_days=None → no opportunities generated."""
        lines = [
            _line(row_id=i + 1, payment_terms_days=None, amount=100_000.0)
            for i in range(5)
        ]
        result = engine.payment_terms_optimizer(lines)
        assert isinstance(result, dict)
        opps = result.get("opportunities", [])
        # No payment terms → no working capital opportunity
        total_wc = result.get("total_working_capital_release", 0.0)
        assert total_wc == pytest.approx(0.0) or len(opps) == 0

    def test_already_at_benchmark_no_opportunity(self):
        """If current DPO already meets or exceeds benchmark, opportunity should be zero."""
        # Most benchmarks are ~30-45 days. Payment terms of 90 days should exceed them.
        lines = [
            _line(row_id=1, payment_terms_days=90, amount=500_000.0),
        ]
        result = engine.payment_terms_optimizer(lines)
        assert isinstance(result, dict)
        # Either no opportunities or zero WC release for this category
        for opp in result.get("opportunities", []):
            if opp.get("category_id") == "IT":
                assert opp.get("working_capital_release", 0.0) <= 0.0


# ---------------------------------------------------------------------------
# TestEdgeCases — heuristic_analyzer (zero revenue edge case)
# ---------------------------------------------------------------------------

class TestHeuristicAnalyzerEdgeCases:
    """heuristic_analyzer must handle zero revenue without dividing by zero."""

    def test_zero_revenue_no_crash(self):
        lines = [_line(row_id=1, amount=500_000.0)]
        profile = engine.spend_profiler(lines)
        result = engine.heuristic_analyzer(profile, revenue=0.0)
        assert isinstance(result, dict)

    def test_empty_profile_no_crash(self):
        result = engine.heuristic_analyzer({}, revenue=0.0)
        assert isinstance(result, dict)
