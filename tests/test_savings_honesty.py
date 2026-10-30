"""Savings/benchmark honesty: risk-adjusted view, uplift provenance, no false precision."""
from __future__ import annotations

import pytest

from app.skills import engine
from app.skills.engine.savings import _overlap_factor


def _modeled():
    rows = [
        {"category_id": "IT", "category_name": "IT", "source": "peer", "estimated_saving_amount": 500_000.0},
        {"category_id": "TRAVEL", "category_name": "Travel", "source": "peer", "estimated_saving_amount": 300_000.0},
    ]
    root = {
        "root_cause_findings": [
            {
                "category_id": "TRAVEL",
                "root_causes": [{"recommended_lever": "cost_governance", "confidence": "high", "diagnosis": "x"}],
            }
        ]
    }
    return engine.savings_modeler({"raw_rows": rows}, root)


def test_risk_adjusted_view_is_below_full_delivery():
    result = _modeled()
    for init in result["initiatives"]:
        ra = init["risk_adjusted"]
        assert 0 < ra["execution_probability"] <= 1
        assert ra["expected_gross_3yr"] == pytest.approx(init["gross_savings"]["total_3yr"] * ra["execution_probability"], abs=0.01)
    s = result["summary"]
    assert 0 < s["total_expected_net_3yr"] < s["total_net_3yr_full_delivery"]


def test_governance_uplift_keeps_npv_provenance_consistent():
    result = _modeled()
    assert result["summary"]["governance_y3_uplift_applied"]
    uplifted = next(i for i in result["initiatives"] if i["lever"] != "cost_governance")
    ns = uplifted["net_savings"]
    r = result["discount_rate"]
    expected = ns["y1"] / (1 + r) + ns["y2"] / (1 + r) ** 2 + ns["y3"] / (1 + r) ** 3
    assert ns["npv_pretax"] == pytest.approx(expected, abs=0.01)
    assert uplifted["provenance"]["npv_pretax"]["value"] == pytest.approx(ns["npv_pretax"])
    assert uplifted["provenance"]["governance_y3_uplift_applied"] is True


def test_overlap_factor_honours_explicit_zero():
    assert _overlap_factor("a", "b", {"a:b": 0.0}, 0.5) == 0.0
    assert _overlap_factor("a", "b", {"b:a": 0.0}, 0.5) == 0.0
    assert _overlap_factor("a", "b", {}, 0.5) == 0.5


def _peer(revenue: float, sample_size: int):
    profile = {"category_profile": [{"category_id": "IT", "category_name": "IT", "spend": 100_000.0}]}
    data = {"benchmarks": {"technology": {"categories": {"IT": {"P25": 1.0, "P50": 2.0, "P75": 3.0, "P90": 4.0}}}}}
    ds = {"dataset_id": "seed-industry-benchmarks", "source": "X (illustrative)", "sample_size": sample_size}
    return engine.peer_benchmarker(profile, data, "technology", revenue, selected_dataset=ds)


def test_no_confidence_interval_without_a_sample():
    out = _peer(10_000_000.0, 0)
    assert out["comparisons"][0]["benchmark_ci"] is None
    assert out["benchmark_metadata"]["ci_half_width_pct"] is None
    assert out["benchmark_metadata"]["is_illustrative"] is True


def test_confidence_interval_with_real_sample():
    out = _peer(10_000_000.0, 100)
    assert out["comparisons"][0]["benchmark_ci"]["half_width_pct"] > 0


def test_zero_revenue_warns():
    out = _peer(0.0, 0)
    assert any("revenue" in w.lower() for w in out["warnings"])
