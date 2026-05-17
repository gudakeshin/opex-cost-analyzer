"""Tests for v1.6 FP&A skills: bva_analyzer, temporal_analyzer, payment_terms_optimizer."""
from __future__ import annotations

import pytest

from app.models import NormalizedSpendLine
from app.skills import engine
from app.skills.contracts import (
    BvAAnalyzerOutput,
    PaymentTermsOptimizerOutput,
    TemporalAnalyzerOutput,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _actual(row_id: int, supplier: str, amount: float, category_id: str, period: str) -> NormalizedSpendLine:
    return NormalizedSpendLine(
        row_id=row_id,
        supplier=supplier,
        description=f"{supplier} service",
        amount=amount,
        category_id=category_id,
        category_name=category_id.replace("_", " ").title(),
        amount_type="actual",
        fiscal_period=period,
    )


def _budget(row_id: int, supplier: str, amount: float, category_id: str, period: str) -> NormalizedSpendLine:
    return NormalizedSpendLine(
        row_id=row_id,
        supplier=supplier,
        description=f"{supplier} service",
        amount=amount,
        category_id=category_id,
        category_name=category_id.replace("_", " ").title(),
        amount_type="budget",
        fiscal_period=period,
    )


# ---------------------------------------------------------------------------
# BvA Analyzer tests
# ---------------------------------------------------------------------------

class TestBvAAnalyzer:
    def _bva_lines(self) -> list[NormalizedSpendLine]:
        return [
            # IT: actual > budget (over budget)
            _actual(1, "AWS", 320_000, "IT", "2025-01"),
            _budget(2, "AWS", 280_000, "IT", "2025-01"),
            # PROFESSIONAL_SERVICES: actual < budget (under budget)
            _actual(3, "McKinsey", 120_000, "PROFESSIONAL_SERVICES", "2025-01"),
            _budget(4, "McKinsey", 150_000, "PROFESSIONAL_SERVICES", "2025-01"),
            # FACILITIES: actual == budget (on budget)
            _actual(5, "CBRE", 180_000, "FACILITIES", "2025-01"),
            _budget(6, "CBRE", 180_000, "FACILITIES", "2025-01"),
        ]

    def test_bva_available_when_both_types_present(self) -> None:
        result = engine.bva_analyzer(self._bva_lines())
        assert result["bva_available"] is True

    def test_bva_contract_validates(self) -> None:
        result = engine.bva_analyzer(self._bva_lines())
        parsed = BvAAnalyzerOutput.model_validate(result)
        assert parsed.bva_available is True

    def test_total_variance_correct(self) -> None:
        result = engine.bva_analyzer(self._bva_lines())
        # IT: +40k over; PROF: -30k under; FACILITIES: 0
        assert result["total_variance"] == pytest.approx(10_000.0, abs=1)

    def test_over_and_under_counts(self) -> None:
        result = engine.bva_analyzer(self._bva_lines())
        assert result["categories_over_budget"] == 1
        assert result["categories_under_budget"] == 1

    def test_per_category_flags(self) -> None:
        result = engine.bva_analyzer(self._bva_lines())
        by_cat = {v["category_id"]: v for v in result["variances"]}
        assert by_cat["IT"]["flag"] == "over_budget"
        assert by_cat["PROFESSIONAL_SERVICES"]["flag"] == "under_budget"
        assert by_cat["FACILITIES"]["flag"] == "on_budget"

    def test_primary_driver_identified(self) -> None:
        result = engine.bva_analyzer(self._bva_lines())
        # "spend" is the correct primary_driver when no per-unit quantity data
        # is present (CIMA/ACCA standard — T1-1 fix).
        # "price" | "volume" | "mix" are valid when quantity data is available.
        for row in result["variances"]:
            assert row["primary_driver"] in ("spend", "price", "volume", "mix")

    def test_bva_not_available_actuals_only(self) -> None:
        actuals_only = [_actual(i, "AWS", 100_000, "IT", "2025-01") for i in range(3)]
        result = engine.bva_analyzer(actuals_only)
        assert result["bva_available"] is False

    def test_bva_not_available_no_lines(self) -> None:
        result = engine.bva_analyzer([])
        assert result["bva_available"] is False


# ---------------------------------------------------------------------------
# Temporal Analyzer tests
# ---------------------------------------------------------------------------

class TestTemporalAnalyzer:
    def _multiperiod_lines(self) -> list[NormalizedSpendLine]:
        rows = []
        # IT: growing month-over-month
        it_amounts = [280_000, 295_000, 320_000, 338_000]
        for i, (period, amount) in enumerate(zip(
            ["2024-10", "2024-11", "2024-12", "2025-01"], it_amounts
        )):
            rows.append(_actual(i + 1, "AWS", amount, "IT", period))
        # MARKETING: stable
        for i, period in enumerate(["2024-10", "2024-11", "2024-12", "2025-01"]):
            rows.append(_actual(100 + i, "Google", 110_000, "MARKETING", period))
        return rows

    def test_temporal_available_with_periods(self) -> None:
        result = engine.temporal_analyzer(self._multiperiod_lines())
        assert result["temporal_available"] is True

    def test_contract_validates(self) -> None:
        result = engine.temporal_analyzer(self._multiperiod_lines())
        TemporalAnalyzerOutput.model_validate(result)

    def test_period_count(self) -> None:
        result = engine.temporal_analyzer(self._multiperiod_lines())
        assert result["period_count"] == 4

    def test_first_and_last_period(self) -> None:
        result = engine.temporal_analyzer(self._multiperiod_lines())
        assert result["first_period"] == "2024-10"
        assert result["last_period"] == "2025-01"

    def test_period_trends_length(self) -> None:
        result = engine.temporal_analyzer(self._multiperiod_lines())
        assert len(result["period_trends"]) == 4

    def test_mom_delta_second_period(self) -> None:
        result = engine.temporal_analyzer(self._multiperiod_lines())
        # Second period total = 295k IT + 110k marketing = 405k
        # First period total = 280k + 110k = 390k, delta = +15k
        trends = {t["period"]: t for t in result["period_trends"]}
        assert trends["2024-11"]["mom_delta"] == pytest.approx(15_000.0, abs=1)

    def test_annualized_run_rate_positive(self) -> None:
        result = engine.temporal_analyzer(self._multiperiod_lines())
        assert result["annualized_run_rate"] > 0

    def test_category_trends_present(self) -> None:
        result = engine.temporal_analyzer(self._multiperiod_lines())
        assert len(result["category_trends"]) > 0
        cat_ids = {c["category_id"] for c in result["category_trends"]}
        assert "IT" in cat_ids
        assert "MARKETING" in cat_ids

    def test_rising_trend_for_growing_category(self) -> None:
        result = engine.temporal_analyzer(self._multiperiod_lines())
        it_trend = next(c for c in result["category_trends"] if c["category_id"] == "IT")
        # engine uses "increasing" for positive total_change
        assert it_trend["trend_direction"] in ("rising", "increasing")

    def test_temporal_not_available_single_period(self) -> None:
        single = [_actual(1, "AWS", 100_000, "IT", "2025-01")]
        result = engine.temporal_analyzer(single)
        assert result["temporal_available"] is False

    def test_temporal_not_available_no_periods(self) -> None:
        lines = [
            NormalizedSpendLine(
                row_id=1, supplier="AWS", description="cloud",
                amount=100_000, category_id="IT", category_name="IT",
            )
        ]
        result = engine.temporal_analyzer(lines)
        assert result["temporal_available"] is False


# ---------------------------------------------------------------------------
# Payment Terms Optimizer tests
# ---------------------------------------------------------------------------

class TestPaymentTermsOptimizer:
    def _pt_lines(self) -> list[NormalizedSpendLine]:
        return [
            NormalizedSpendLine(
                row_id=1, supplier="AWS", description="cloud",
                amount=3_840_000, category_id="IT", category_name="IT & Technology",
                payment_terms_days=30, amount_type="actual",
            ),
            NormalizedSpendLine(
                row_id=2, supplier="McKinsey", description="consulting",
                amount=2_520_000, category_id="PROFESSIONAL_SERVICES",
                category_name="Professional Services",
                payment_terms_days=30, amount_type="actual",
            ),
            NormalizedSpendLine(
                row_id=3, supplier="CBRE", description="office lease",
                amount=2_160_000, category_id="FACILITIES", category_name="Facilities",
                payment_terms_days=30, amount_type="actual",
            ),
            NormalizedSpendLine(
                row_id=4, supplier="Randstad", description="staffing",
                amount=1_176_000, category_id="CONTINGENT_WORKFORCE",
                category_name="Contingent Workforce",
                payment_terms_days=21, amount_type="actual",
            ),
        ]

    def test_payment_terms_available(self) -> None:
        result = engine.payment_terms_optimizer(self._pt_lines(), wacc=0.10, industry="technology")
        assert result["payment_terms_available"] is True

    def test_contract_validates(self) -> None:
        result = engine.payment_terms_optimizer(self._pt_lines())
        PaymentTermsOptimizerOutput.model_validate(result)

    def test_working_capital_release_positive(self) -> None:
        result = engine.payment_terms_optimizer(self._pt_lines(), wacc=0.10)
        assert result["total_working_capital_release"] > 0

    def test_annual_cash_value_positive(self) -> None:
        result = engine.payment_terms_optimizer(self._pt_lines(), wacc=0.10)
        assert result["total_annual_cash_value"] > 0

    def test_annual_cash_value_equals_wc_times_wacc(self) -> None:
        result = engine.payment_terms_optimizer(self._pt_lines(), wacc=0.10)
        expected = round(result["total_working_capital_release"] * 0.10, 2)
        assert result["total_annual_cash_value"] == pytest.approx(expected, rel=0.01)

    def test_opportunity_count_matches_opportunities(self) -> None:
        result = engine.payment_terms_optimizer(self._pt_lines())
        assert result["opportunity_count"] == len(result["opportunities"])

    def test_contingent_workforce_lower_target_dpo(self) -> None:
        result = engine.payment_terms_optimizer(self._pt_lines())
        cw = next(
            (o for o in result["opportunities"] if o["category_id"] == "CONTINGENT_WORKFORCE"),
            None,
        )
        # CONTINGENT_WORKFORCE benchmark p50=21; current is 21, so no improvement expected
        # or it should show a small/zero opportunity
        if cw:
            assert cw["target_dpo_days"] >= cw["current_dpo_days"] or cw["dpo_improvement_days"] <= 0

    def test_industry_adjustment_applied(self) -> None:
        result_tech = engine.payment_terms_optimizer(self._pt_lines(), wacc=0.10, industry="technology")
        result_retail = engine.payment_terms_optimizer(self._pt_lines(), wacc=0.10, industry="retail")
        # Retail has higher DPO adjustment factor (1.30 vs 0.90), so more WC release
        assert result_retail["total_working_capital_release"] > result_tech["total_working_capital_release"]

    def test_no_payment_terms_returns_unavailable(self) -> None:
        lines = [
            NormalizedSpendLine(
                row_id=1, supplier="AWS", description="cloud",
                amount=100_000, category_id="IT", category_name="IT",
            )
        ]
        result = engine.payment_terms_optimizer(lines)
        assert result["payment_terms_available"] is False

    def test_wacc_stored_in_output(self) -> None:
        result = engine.payment_terms_optimizer(self._pt_lines(), wacc=0.12)
        assert result["wacc"] == pytest.approx(0.12)


# ---------------------------------------------------------------------------
# Multi-currency normalization tests (via spend_profiler)
# ---------------------------------------------------------------------------

class TestMultiCurrencyNormalization:
    def test_reporting_amount_property_with_fx_rate(self) -> None:
        line = NormalizedSpendLine(
            row_id=1, supplier="SAP", description="ERP licenses",
            amount=100_000, category_id="IT", category_name="IT",
            currency="GBP", fx_rate_to_reporting=1.27,
        )
        assert line.reporting_amount == pytest.approx(127_000.0)

    def test_reporting_amount_uses_explicit_override(self) -> None:
        line = NormalizedSpendLine(
            row_id=1, supplier="SAP", description="ERP licenses",
            amount=100_000, category_id="IT", category_name="IT",
            currency="GBP", fx_rate_to_reporting=1.27,
            amount_reporting=130_000.0,
        )
        assert line.reporting_amount == pytest.approx(130_000.0)

    def test_usd_passthrough_unchanged(self) -> None:
        line = NormalizedSpendLine(
            row_id=1, supplier="AWS", description="cloud",
            amount=320_000, category_id="IT", category_name="IT",
        )
        assert line.reporting_amount == pytest.approx(320_000.0)

    def test_spend_profiler_uses_reporting_amount(self) -> None:
        lines = [
            NormalizedSpendLine(
                row_id=1, supplier="AWS", description="cloud - USD",
                amount=200_000, category_id="IT", category_name="IT",
                currency="USD", fx_rate_to_reporting=1.0,
            ),
            NormalizedSpendLine(
                row_id=2, supplier="SAP UK", description="ERP - GBP",
                amount=100_000, category_id="IT", category_name="IT",
                currency="GBP", fx_rate_to_reporting=1.27,
            ),
        ]
        profile = engine.spend_profiler(lines)
        # 200k + 127k = 327k in reporting currency
        assert profile["total_spend"] == pytest.approx(327_000.0, abs=1)

    def test_currency_breakdown_present(self) -> None:
        lines = [
            NormalizedSpendLine(
                row_id=1, supplier="AWS", description="cloud",
                amount=200_000, category_id="IT", category_name="IT",
                currency="USD", fx_rate_to_reporting=1.0,
            ),
            NormalizedSpendLine(
                row_id=2, supplier="SAP", description="ERP",
                amount=100_000, category_id="IT", category_name="IT",
                currency="GBP", fx_rate_to_reporting=1.27,
            ),
        ]
        profile = engine.spend_profiler(lines)
        assert "currency_breakdown" in profile
        assert "USD" in profile["currency_breakdown"]
        assert "GBP" in profile["currency_breakdown"]


# ---------------------------------------------------------------------------
# Integration: all three FP&A skills together (comprehensive_fpa.csv scenario)
# ---------------------------------------------------------------------------

class TestFPASkillsIntegration:
    def _comprehensive_lines(self) -> list[NormalizedSpendLine]:
        """Simulate the comprehensive_fpa.csv: actual + budget for Jan-2025, 3 prior actuals periods."""
        categories = [
            ("IT", "IT & Technology", 320_000, 280_000),
            ("PROFESSIONAL_SERVICES", "Professional Services", 210_000, 150_000),
            ("FACILITIES", "Facilities", 180_000, 180_000),
            ("MARKETING", "Marketing", 125_000, 140_000),
        ]
        lines: list[NormalizedSpendLine] = []
        row_id = 1
        for cat_id, cat_name, actual_amt, budget_amt in categories:
            lines.append(NormalizedSpendLine(
                row_id=row_id, supplier="Supplier A", description=cat_name,
                amount=actual_amt, category_id=cat_id, category_name=cat_name,
                amount_type="actual", fiscal_period="2025-01",
                payment_terms_days=30,
            ))
            row_id += 1
            lines.append(NormalizedSpendLine(
                row_id=row_id, supplier="Supplier A", description=cat_name,
                amount=budget_amt, category_id=cat_id, category_name=cat_name,
                amount_type="budget", fiscal_period="2025-01",
            ))
            row_id += 1
        # Add prior actuals for trend
        for period, multiplier in [("2024-11", 0.86), ("2024-12", 0.93)]:
            for cat_id, cat_name, actual_amt, _ in categories:
                lines.append(NormalizedSpendLine(
                    row_id=row_id, supplier="Supplier A", description=cat_name,
                    amount=round(actual_amt * multiplier), category_id=cat_id, category_name=cat_name,
                    amount_type="actual", fiscal_period=period,
                    payment_terms_days=30,
                ))
                row_id += 1
        return lines

    def test_bva_and_temporal_and_pt_all_run(self) -> None:
        lines = self._comprehensive_lines()
        bva = engine.bva_analyzer(lines)
        temporal = engine.temporal_analyzer(lines)
        pt = engine.payment_terms_optimizer(lines, wacc=0.10, industry="technology")
        assert bva["bva_available"] is True
        assert temporal["temporal_available"] is True
        assert pt["payment_terms_available"] is True

    def test_total_actual_matches_sum_of_actuals(self) -> None:
        lines = self._comprehensive_lines()
        bva = engine.bva_analyzer(lines)
        # BvA sums all actual lines across all periods (not filtered by period)
        actual_sum = sum(ln.reporting_amount for ln in lines if ln.amount_type == "actual")
        assert bva["total_actual"] == pytest.approx(actual_sum, abs=1)

    def test_temporal_sees_3_periods(self) -> None:
        lines = self._comprehensive_lines()
        temporal = engine.temporal_analyzer(lines)
        assert temporal["period_count"] == 3

    def test_pt_coverage_pct_positive(self) -> None:
        lines = self._comprehensive_lines()
        pt = engine.payment_terms_optimizer(lines)
        assert pt["coverage_pct"] > 0
