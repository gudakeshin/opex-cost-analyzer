"""Layer 1: Golden dataset unit tests.

Each test loads a fixture from tests/eval/golden/, invokes the skill directly,
and asserts completeness + format compliance.

No LLM calls are made here — fully deterministic CI tests.
LLM faithfulness scoring is in test_layer2_trace.py (gated by llm_judge marker).

Key: actual output key names from engine.py
  bva_analyzer:              variances[].total_variance  (not category_variances / variance_amount)
  temporal_analyzer:         period_trends, category_trends  — requires fiscal_period set on lines
  payment_terms_optimizer:   total_working_capital_release, opportunities  (not supplier_opportunities)
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.eval.golden import GoldenResult, run_golden_suite

GOLDEN_DIR = Path(__file__).parent / "golden"


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _load(fixture_name: str) -> GoldenResult:
    return run_golden_suite(GOLDEN_DIR / fixture_name)


# ---------------------------------------------------------------------------
# spend-profiler
# ---------------------------------------------------------------------------

class TestGoldenSpendProfiler:
    def test_passes(self):
        result = _load("spend_profiler.json")
        assert result.passed, f"Failures: {result.failures}"

    def test_total_spend_correct(self):
        result = _load("spend_profiler.json")
        assert result.output.get("total_spend") == 600_000.0

    def test_three_categories_returned(self):
        result = _load("spend_profiler.json")
        cats = result.output.get("category_profile", [])
        assert len(cats) >= 3

    def test_category_ids_present(self):
        result = _load("spend_profiler.json")
        ids = {c["category_id"] for c in result.output.get("category_profile", [])}
        assert "software" in ids
        assert "professional_services" in ids
        assert "facilities" in ids

    def test_shares_sum_to_one(self):
        result = _load("spend_profiler.json")
        total_share = sum(
            c.get("share_of_total", 0.0)
            for c in result.output.get("category_profile", [])
        )
        assert abs(total_share - 1.0) < 0.01, f"Shares sum to {total_share}"


# ---------------------------------------------------------------------------
# bva-analyzer
# ---------------------------------------------------------------------------

class TestGoldenBvAAnalyzer:
    def test_passes(self):
        result = _load("bva_analyzer.json")
        assert result.passed, f"Failures: {result.failures}"

    def test_bva_available(self):
        result = _load("bva_analyzer.json")
        assert result.output.get("bva_available") is True

    def test_three_variances(self):
        result = _load("bva_analyzer.json")
        variances = result.output.get("variances", [])
        assert len(variances) >= 3

    def test_all_variances_unfavorable(self):
        """All actuals > budget in the fixture, so total_variance > 0 for each category."""
        result = _load("bva_analyzer.json")
        for var in result.output.get("variances", []):
            delta = var.get("total_variance", 0.0)
            assert delta > 0, (
                f"Expected unfavorable variance, got {delta} for {var.get('category_id')}"
            )

    def test_cloud_variance_fifty_k(self):
        """cloud: actual 150k - budget 100k = 50k overrun."""
        result = _load("bva_analyzer.json")
        variances = {v["category_id"]: v for v in result.output.get("variances", [])}
        cloud = variances.get("cloud", {})
        assert abs(cloud.get("total_variance", 0.0) - 50_000.0) < 1.0

    def test_primary_driver_in_each_variance(self):
        """Each variance row should carry a primary_driver field."""
        result = _load("bva_analyzer.json")
        for var in result.output.get("variances", []):
            assert "primary_driver" in var, f"Missing primary_driver in: {var}"

    def test_required_keys(self):
        result = _load("bva_analyzer.json")
        for key in ("bva_available", "total_actual", "total_budget", "variances"):
            assert key in result.output, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# temporal-analyzer
# ---------------------------------------------------------------------------

class TestGoldenTemporalAnalyzer:
    def test_passes(self):
        result = _load("temporal_analyzer.json")
        assert result.passed, f"Failures: {result.failures}"

    def test_temporal_available(self):
        result = _load("temporal_analyzer.json")
        assert result.output.get("temporal_available") is True

    def test_period_count_at_least_four(self):
        result = _load("temporal_analyzer.json")
        assert result.output.get("period_count", 0) >= 4

    def test_period_trends_present(self):
        result = _load("temporal_analyzer.json")
        trends = result.output.get("period_trends", [])
        assert len(trends) >= 4

    def test_software_category_present(self):
        result = _load("temporal_analyzer.json")
        ids = [t.get("category_id") for t in result.output.get("category_trends", [])]
        assert "software" in ids

    def test_increasing_trend_for_software(self):
        """Monthly spend increases monotonically in fixture: 50k to 85k."""
        result = _load("temporal_analyzer.json")
        for trend in result.output.get("category_trends", []):
            if trend.get("category_id") == "software":
                direction = trend.get("trend_direction", "")
                assert direction in ("increasing", "rising"), (
                    f"Expected increasing trend, got '{direction}'"
                )
                break

    def test_annualized_run_rate_positive(self):
        result = _load("temporal_analyzer.json")
        arr = result.output.get("annualized_run_rate", 0.0)
        assert arr > 0, "Annualized run rate should be positive"

    def test_required_keys(self):
        result = _load("temporal_analyzer.json")
        for key in ("temporal_available", "period_count", "period_trends", "category_trends"):
            assert key in result.output, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# payment-terms-optimizer
# ---------------------------------------------------------------------------

class TestGoldenPaymentTermsOptimizer:
    def test_passes(self):
        result = _load("payment_terms_optimizer.json")
        assert result.passed, f"Failures: {result.failures}"

    def test_payment_terms_available(self):
        result = _load("payment_terms_optimizer.json")
        assert result.output.get("payment_terms_available") is True

    def test_wc_release_positive(self):
        result = _load("payment_terms_optimizer.json")
        wc = result.output.get("total_working_capital_release", 0.0)
        assert wc > 0, "Working capital release should be positive"

    def test_opportunities_found(self):
        result = _load("payment_terms_optimizer.json")
        opps = result.output.get("opportunities", [])
        assert len(opps) >= 1

    def test_required_keys(self):
        result = _load("payment_terms_optimizer.json")
        for key in ("payment_terms_available", "total_working_capital_release", "opportunities"):
            assert key in result.output, f"Missing key: {key}"

    def test_all_opportunities_have_category_id(self):
        """payment_terms_optimizer groups by category_id (not supplier)."""
        result = _load("payment_terms_optimizer.json")
        for opp in result.output.get("opportunities", []):
            assert "category_id" in opp, f"Missing 'category_id' field in opportunity: {opp}"
            assert opp.get("working_capital_release", 0.0) > 0, (
                f"Expected positive WC release in opportunity: {opp}"
            )


# ---------------------------------------------------------------------------
# T4-1: New golden fixtures — BvA all-favorable adversarial
# ---------------------------------------------------------------------------

class TestGoldenBvAAllFavorable:
    """T4-1: All actuals below budget — adversarial fixture."""

    def test_passes(self):
        result = _load("bva_analyzer_all_favorable.json")
        assert result.passed, f"Failures: {result.failures}"

    def test_bva_available(self):
        result = _load("bva_analyzer_all_favorable.json")
        assert result.output.get("bva_available") is True

    def test_all_variances_favorable(self):
        """All actuals < budget → every total_variance must be negative."""
        result = _load("bva_analyzer_all_favorable.json")
        for var in result.output.get("variances", []):
            delta = var.get("total_variance", 0.0)
            assert delta < 0, (
                f"Expected favorable (negative) variance for {var.get('category_id')}, got {delta}"
            )

    def test_categories_under_budget_count(self):
        result = _load("bva_analyzer_all_favorable.json")
        assert result.output.get("categories_under_budget", 0) == 3
        assert result.output.get("categories_over_budget", 0) == 0


# ---------------------------------------------------------------------------
# T4-1: New golden fixtures — temporal single period (adversarial)
# ---------------------------------------------------------------------------

class TestGoldenTemporalSinglePeriod:
    """T4-1: Only one fiscal period → temporal_available must be False."""

    def test_passes(self):
        result = _load("temporal_analyzer_single_period.json")
        assert result.passed, f"Failures: {result.failures}"

    def test_temporal_not_available(self):
        result = _load("temporal_analyzer_single_period.json")
        assert result.output.get("temporal_available") is False

    def test_required_key_present(self):
        result = _load("temporal_analyzer_single_period.json")
        assert "temporal_available" in result.output


# ---------------------------------------------------------------------------
# T4-1: New golden fixtures — temporal 12-month TTM ARR
# ---------------------------------------------------------------------------

class TestGoldenTemporal12Mo:
    """T4-1: 12 months → arr_basis must be 'TTM'; also tests CAGR presence."""

    def test_passes(self):
        result = _load("temporal_analyzer_12mo.json")
        assert result.passed, f"Failures: {result.failures}"

    def test_arr_basis_is_ttm(self):
        result = _load("temporal_analyzer_12mo.json")
        assert result.output.get("arr_basis") == "TTM", (
            f"Expected arr_basis='TTM', got {result.output.get('arr_basis')!r}"
        )

    def test_ttm_arr_equals_sum_of_12_periods(self):
        """TTM ARR = sum of all 12 periods (= 100k+102k+...+122k = 1,332,000)."""
        result = _load("temporal_analyzer_12mo.json")
        expected_ttm = sum(100_000 + i * 2_000 for i in range(12))  # 1_332_000
        arr = result.output.get("annualized_run_rate", 0.0)
        assert abs(arr - expected_ttm) < 1.0, (
            f"Expected TTM ARR {expected_ttm}, got {arr}"
        )

    def test_cagr_pct_present_and_positive(self):
        """12-month increasing spend → CAGR must be positive."""
        result = _load("temporal_analyzer_12mo.json")
        cagr = result.output.get("cagr_pct")
        assert cagr is not None, "cagr_pct should not be None for 12 periods"
        assert cagr > 0, f"Expected positive CAGR for monotonically increasing spend, got {cagr}"

    def test_period_count_12(self):
        result = _load("temporal_analyzer_12mo.json")
        assert result.output.get("period_count") == 12


# ---------------------------------------------------------------------------
# T4-1: New golden fixtures — spend profiler HHI
# ---------------------------------------------------------------------------

class TestGoldenSpendProfilerHHI:
    """T4-1: Single-supplier category → HHI = 1.0, concentration_flag = 'high'."""

    def test_passes(self):
        result = _load("spend_profiler_hhi.json")
        assert result.passed, f"Failures: {result.failures}"

    def test_hhi_present_and_one(self):
        """Single supplier monopoly: HHI must equal 1.0."""
        result = _load("spend_profiler_hhi.json")
        profiles = result.output.get("category_profile", [])
        assert profiles, "Expected at least one category profile"
        cloud = next((p for p in profiles if p.get("category_id") == "cloud"), None)
        assert cloud is not None, "Cloud category not found"
        assert cloud.get("hhi") == pytest.approx(1.0, abs=0.001), (
            f"Expected HHI=1.0 for single supplier, got {cloud.get('hhi')}"
        )

    def test_concentration_flag_high(self):
        result = _load("spend_profiler_hhi.json")
        profiles = result.output.get("category_profile", [])
        cloud = next((p for p in profiles if p.get("category_id") == "cloud"), None)
        assert cloud is not None
        assert cloud.get("concentration_flag") == "high", (
            f"Expected 'high' concentration for monopoly supplier, got {cloud.get('concentration_flag')!r}"
        )


# ---------------------------------------------------------------------------
# model-contextualizer
# ---------------------------------------------------------------------------

class TestGoldenModelContextualizer:
    def test_simple_fixture_passes(self):
        result = _load("model_contextualizer_simple.json")
        assert result.passed, f"Failures: {result.failures}"
        assert result.output.get("ingestion_strategy") == "hybrid"
        assert result.output.get("model_type") in {"planning", "scenario", "forecast"}

    def test_scenario_fixture_detects_scenarios(self):
        result = _load("model_contextualizer_scenario.json")
        assert result.passed, f"Failures: {result.failures}"
        assert len(result.output.get("scenarios", [])) >= 2

    def test_low_confidence_fixture_marks_notes(self):
        result = _load("model_contextualizer_low_confidence.json")
        assert result.passed, f"Failures: {result.failures}"
        assert float(result.output.get("confidence", 0.0)) < 0.70
        assert "could not be confidently classified" in str(result.output.get("ingestion_notes", "")).lower()

    def test_hybrid_fixture_has_hybrid_strategy(self):
        result = _load("model_contextualizer_hybrid.json")
        assert result.passed, f"Failures: {result.failures}"
        assert result.output.get("ingestion_strategy") == "hybrid"


# ---------------------------------------------------------------------------
# Parametric smoke test — all fixtures must produce non-empty output
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fixture", [
    "spend_profiler.json",
    "bva_analyzer.json",
    "temporal_analyzer.json",
    "payment_terms_optimizer.json",
    # T4-1: new fixtures
    "bva_analyzer_all_favorable.json",
    "temporal_analyzer_single_period.json",
    "temporal_analyzer_12mo.json",
    "spend_profiler_hhi.json",
    "model_contextualizer_simple.json",
    "model_contextualizer_scenario.json",
    "model_contextualizer_low_confidence.json",
    "model_contextualizer_hybrid.json",
])
def test_fixture_produces_output(fixture):
    result = run_golden_suite(GOLDEN_DIR / fixture)
    assert result.output, f"Fixture {fixture} produced empty output"
    assert result.passed, f"Fixture {fixture} failed: {result.failures}"
