from __future__ import annotations

import pytest

from app.models import NormalizedSpendLine
from app.skills import engine


def _sample_lines() -> list[NormalizedSpendLine]:
    return [
        NormalizedSpendLine(
            row_id=1,
            supplier="AWS",
            description="cloud hosting",
            amount=100000.0,
            category_id="IT",
            category_name="IT & Technology",
            business_unit="BU1",
        ),
        NormalizedSpendLine(
            row_id=2,
            supplier="McKinsey",
            description="consulting project",
            amount=50000.0,
            category_id="PROF_SVCS",
            category_name="Professional Services",
            business_unit="BU2",
        ),
        NormalizedSpendLine(
            row_id=3,
            supplier="AWS",
            description="cloud hosting",
            amount=70000.0,
            category_id="IT",
            category_name="IT & Technology",
            business_unit="BU2",
        ),
    ]


def test_spend_profiler_aggregates_total_and_categories() -> None:
    profile = engine.spend_profiler(_sample_lines())
    assert profile["total_spend"] == 220000.0
    assert len(profile["category_profile"]) == 2
    assert profile["category_profile"][0]["category_id"] == "IT"


def test_internal_benchmarker_flags_spread() -> None:
    result = engine.internal_benchmarker(_sample_lines())
    assert result["internal_variance"]
    it_row = [r for r in result["internal_variance"] if r["category_id"] == "IT"][0]
    assert it_row["flagged_gt_20pct"] is True


def test_value_bridge_and_validator() -> None:
    peer = {"comparisons": [{"category_id": "IT", "estimated_saving_amount": 12000.0}]}
    internal = {"internal_variance": [{"category_id": "IT", "median_spend": 100000.0}]}
    heuristic = {"heuristic_findings": [{"category_id": "IT", "estimated_saving_amount": 8000.0}]}
    bridge = engine.value_bridge_calculator(peer, internal, heuristic, total_spend=200000.0)
    assert bridge["confidence_bands"]["mid"] > 0
    valid = engine.data_validator(bridge)
    assert valid["passed"] is True


def test_root_cause_and_savings_modeler_pipeline() -> None:
    lines = _sample_lines()
    profile = engine.spend_profiler(lines)
    peer = {
        "comparisons": [
            {
                "category_id": "IT",
                "category_name": "IT & Technology",
                "percentile_band": "P75-P90",
                "estimated_saving_amount": 20000.0,
            }
        ]
    }
    internal = {"internal_variance": [{"category_id": "IT", "median_spend": 100000.0}]}
    heuristic = {"heuristic_findings": [{"category_id": "IT", "estimated_saving_amount": 8000.0}]}
    root = engine.root_cause_analyzer(profile, peer, lines)
    raw = engine.value_bridge_calculator(peer, internal, heuristic, total_spend=profile["total_spend"])
    modeled = engine.savings_modeler(raw, root)
    final_bridge = engine.value_bridge_calculator(peer, internal, heuristic, total_spend=profile["total_spend"], savings_model=modeled)
    assert root["root_cause_findings"]
    assert modeled["initiatives"]
    assert final_bridge["confidence_bands"]["mid"] >= 0


# ---------------------------------------------------------------------------
# Gap 1: P25 benchmarking
# ---------------------------------------------------------------------------

def _sample_profile_it(spend: float) -> dict:
    return {
        "category_profile": [
            {"category_id": "IT", "category_name": "IT & Technology", "spend": spend}
        ]
    }


def _technology_benchmark_data() -> dict:
    """Return benchmark data matching industry_benchmarks.json technology/IT: P25=4.5, P50=6.2."""
    return {
        "benchmarks": {
            "technology": {
                "categories": {
                    "IT": {"P25": 4.5, "P50": 6.2, "P75": 8.5, "P90": 11.0}
                }
            }
        }
    }


def test_peer_benchmarker_uses_p25_not_p50() -> None:
    """Savings should be based on the gap to P25 (top-quartile), not P50 (median)."""
    revenue = 100_000_000.0
    # IT spend at 5.5% of revenue — above P25(4.5%) but below P50(6.2%)
    # P25-based saving: (5.5 - 4.5) / 100 * 100M = $1,000,000
    # P50-based saving would be 0 (5.5 < 6.2)
    profile = _sample_profile_it(5_500_000.0)
    result = engine.peer_benchmarker(profile, _technology_benchmark_data(), "technology", revenue)
    comparison = result["comparisons"][0]
    assert comparison["benchmark_target_pct"] == 4.5  # P25 used as target
    assert comparison["benchmark_p50_pct"] == 6.2    # P50 retained as reference
    assert comparison["estimated_saving_amount"] > 0  # Gap to P25 is positive
    # Verify savings are NOT zero (which would happen if P50 were still used as target)
    assert comparison["estimated_saving_amount"] == pytest.approx(1_000_000.0, rel=1e-3)


def test_peer_benchmarker_no_saving_below_p25() -> None:
    """Spend already below P25 should produce zero estimated savings."""
    revenue = 100_000_000.0
    # IT spend at 3% of revenue — already below P25 (4.5%)
    profile = _sample_profile_it(3_000_000.0)
    result = engine.peer_benchmarker(profile, _technology_benchmark_data(), "technology", revenue)
    assert result["comparisons"][0]["estimated_saving_amount"] == 0.0


# ---------------------------------------------------------------------------
# Gap 2: IRR calculation
# ---------------------------------------------------------------------------

def test_irr_calculation_positive_case() -> None:
    """Newton-Raphson IRR for [-100, 50, 50, 50] should be approximately 23.4%."""
    irr = engine._compute_irr([-100.0, 50.0, 50.0, 50.0])
    assert irr is not None
    assert 20.0 < irr < 30.0  # IRR ≈ 23.4%


def test_irr_returns_none_no_sign_change() -> None:
    """All-negative cashflows have no IRR."""
    irr = engine._compute_irr([-100.0, -50.0, -30.0])
    assert irr is None


def test_irr_computed_with_default_cta_rates() -> None:
    """savings_modeler applies a lever-weighted default CTA rate when no
    explicit cost_to_achieve_inputs are provided, so irr_pct is always
    computed (not None) as long as cta_y1 > 0.

    Renamed from test_irr_returns_none_no_investment: the old assertion
    expected CTA=0 but the engine now always applies a default rate (7% of
    savings gap) to keep economics realistic (T1-1 aligned change).
    """
    peer = {
        "comparisons": [
            {
                "category_id": "IT",
                "category_name": "IT & Technology",
                "percentile_band": "P75-P90",
                "estimated_saving_amount": 500_000.0,
            }
        ]
    }
    internal: dict = {"internal_variance": []}
    heuristic: dict = {"heuristic_findings": []}
    root: dict = {"root_cause_findings": []}
    raw = engine.build_raw_rows(peer, internal, heuristic)
    # No explicit cost_to_achieve_inputs → engine falls back to default 7% CTA
    # rate → cta_y1 > 0 → IRR is computed.
    result = engine.savings_modeler({"raw_rows": raw}, root)
    initiative = result["initiatives"][0]
    assert initiative["irr_pct"] is not None, (
        "IRR should be computed when default CTA rates are applied"
    )
    assert initiative["cost_to_achieve"]["y1"] > 0, (
        "Default CTA rate should produce a positive Y1 implementation cost"
    )


def test_savings_modeler_includes_irr_field() -> None:
    """Every initiative in savings_modeler output must have an irr_pct key."""
    peer = {
        "comparisons": [
            {
                "category_id": "IT",
                "category_name": "IT & Technology",
                "percentile_band": "P75-P90",
                "estimated_saving_amount": 200_000.0,
            }
        ]
    }
    raw = engine.build_raw_rows(peer, {"internal_variance": []}, {"heuristic_findings": []})
    result = engine.savings_modeler({"raw_rows": raw}, {"root_cause_findings": []})
    assert result["initiatives"]
    assert "irr_pct" in result["initiatives"][0]


# ---------------------------------------------------------------------------
# Gap 3: Headcount threading in heuristic_analyzer
# ---------------------------------------------------------------------------

def test_heuristic_analyzer_with_headcount() -> None:
    """Headcount-applicable categories should emit per-employee fields."""
    revenue = 100_000_000.0
    headcount = 1000.0
    # HR spend: $3,000,000 → $3,000/employee. Target is $2,500/employee.
    # headcount_based_saving_amount = (3000 - 2500) * 1000 = $500,000
    profile = {
        "category_profile": [
            {"category_id": "HR", "category_name": "Human Resources", "spend": 3_000_000.0}
        ]
    }
    result = engine.heuristic_analyzer(profile, revenue, headcount=headcount)
    finding = result["heuristic_findings"][0]
    assert finding.get("actual_cost_per_employee") == 3000.0
    assert finding.get("target_cost_per_employee") == 2500.0
    assert finding.get("headcount_based_saving_amount") == pytest.approx(500_000.0, rel=1e-3)


def test_heuristic_analyzer_without_headcount() -> None:
    """Without headcount, per-employee fields must NOT appear (backward compat)."""
    profile = {
        "category_profile": [
            {"category_id": "HR", "category_name": "Human Resources", "spend": 3_000_000.0}
        ]
    }
    result = engine.heuristic_analyzer(profile, 100_000_000.0)
    finding = result["heuristic_findings"][0]
    assert "headcount_based_saving_amount" not in finding
    assert "actual_cost_per_employee" not in finding
    assert "target_cost_per_employee" not in finding


# ---------------------------------------------------------------------------
# Gap 7: Time-series trending in spend_profiler
# ---------------------------------------------------------------------------

def test_spend_profiler_trend_analysis_two_periods() -> None:
    """Two distinct monthly periods should produce trend_analysis with MoM growth."""
    lines = [
        NormalizedSpendLine(
            row_id=1, supplier="AWS", description="cloud", amount=80_000.0,
            category_id="IT", category_name="IT", business_unit="BU1",
            spend_date="2026-01-15",
        ),
        NormalizedSpendLine(
            row_id=2, supplier="AWS", description="cloud", amount=100_000.0,
            category_id="IT", category_name="IT", business_unit="BU1",
            spend_date="2026-02-15",
        ),
    ]
    result = engine.spend_profiler(lines)
    assert "trend_analysis" in result
    ta = result["trend_analysis"]
    assert "2026-01" in ta["distinct_periods"]
    assert "2026-02" in ta["distinct_periods"]
    it_trend = ta["category_trends"]["IT"]
    assert it_trend["mom_growth_pct"] == pytest.approx(25.0, rel=1e-2)  # 20k / 80k * 100


def test_spend_profiler_no_trend_single_period() -> None:
    """A single period should not add trend_analysis key."""
    lines = [
        NormalizedSpendLine(
            row_id=1, supplier="AWS", description="cloud", amount=100_000.0,
            category_id="IT", category_name="IT", business_unit="BU1",
            spend_date="2026-01-15",
        ),
    ]
    result = engine.spend_profiler(lines)
    assert "trend_analysis" not in result

