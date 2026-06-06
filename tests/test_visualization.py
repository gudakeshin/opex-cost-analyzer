"""Tests for the dynamic chart-spec builder (app/opar/visualization.py).

Guarantees: (1) datasets are built only from skills that actually ran, (2) every
number in a chart traces back to the skill output (no hallucination), (3) the
deterministic fallback selects sensible charts without the LLM.
"""
from __future__ import annotations

from app.opar.visualization import (
    build_chart_catalog,
    build_chart_specs,
    resolve_chart_specs,
    suggest_charts_fallback,
)


def _spend_output() -> dict:
    return {
        "spend-profiler": {
            "total_spend": 1000.0,
            "category_profile": [
                {
                    "category_id": "IT",
                    "category_name": "IT",
                    "spend": 600.0,
                    "addressable_spend": 300.0,
                    "fixed_spend": 200.0,
                    "semi_variable_spend": 100.0,
                    "variable_spend": 300.0,
                    "share_of_total": 0.6,
                },
                {
                    "category_id": "HR",
                    "category_name": "HR",
                    "spend": 400.0,
                    "addressable_spend": 100.0,
                    "fixed_spend": 300.0,
                    "semi_variable_spend": 50.0,
                    "variable_spend": 50.0,
                    "share_of_total": 0.4,
                },
            ],
            "trend_analysis": {
                "period_totals": {"2024-01": 450.0, "2024-02": 550.0},
                "distinct_periods": ["2024-01", "2024-02"],
            },
        }
    }


def test_catalog_empty_when_no_skills() -> None:
    assert build_chart_catalog({}) == []
    assert build_chart_specs("anything", {}) == []


def test_spend_datasets_present_and_data_backed() -> None:
    catalog = build_chart_catalog(_spend_output())
    ids = {d["dataset_id"] for d in catalog}
    assert {"spend_by_category", "addressability_split", "spend_trend"} <= ids

    by_cat = next(d for d in catalog if d["dataset_id"] == "spend_by_category")
    # Numbers must equal the skill output (provenance), highest spend first.
    assert by_cat["data"][0] == {"label": "IT", "spend": 600.0}
    assert by_cat["data"][1] == {"label": "HR", "spend": 400.0}
    assert by_cat["unit"] == "currency"

    trend = next(d for d in catalog if d["dataset_id"] == "spend_trend")
    assert trend["default_type"] == "line"
    assert [r["spend"] for r in trend["data"]] == [450.0, 550.0]


def test_savings_waterfall_uses_net_savings() -> None:
    validated = {
        "savings-modeler": {
            "initiatives": [
                {
                    "category_id": "IT",
                    "lever_name": "Renegotiation",
                    "net_savings": {"total_3yr": 120.0},
                    "cost_to_achieve": {"total_3yr": 20.0},
                    "payback_months": 8,
                },
            ]
        }
    }
    catalog = build_chart_catalog(validated)
    wf = next(d for d in catalog if d["dataset_id"] == "savings_waterfall")
    assert wf["default_type"] == "waterfall"
    assert wf["data"][0] == {"label": "Renegotiation", "value": 120.0}


def test_bva_bridge_anchors_budget_and_actual() -> None:
    validated = {
        "bva-analyzer": {
            "bva_available": True,
            "total_actual": 1100.0,
            "total_budget": 1000.0,
            "total_variance": 100.0,
            "variances": [
                {"category_id": "IT", "category_name": "IT", "actual_spend": 700.0,
                 "budget_spend": 600.0, "total_variance": 100.0, "flag": "over_budget"},
            ],
        }
    }
    catalog = build_chart_catalog(validated)
    bridge = next(d for d in catalog if d["dataset_id"] == "bva_variance_bridge")
    assert bridge["data"][0] == {"label": "Budget", "value": 1000.0, "is_total": True}
    assert bridge["data"][-1] == {"label": "Actual", "value": 1100.0, "is_total": True}


def test_unavailable_skills_yield_no_datasets() -> None:
    validated = {
        "bva-analyzer": {"bva_available": False, "variances": []},
        "payment-terms-optimizer": {"payment_terms_available": False, "opportunities": []},
    }
    assert build_chart_catalog(validated) == []


def test_fallback_keyword_selection() -> None:
    catalog = build_chart_catalog(_spend_output())
    picks = suggest_charts_fallback("show me the spend trend over time", catalog)
    assert picks[0]["dataset_id"] == "spend_trend"

    # No keyword match -> single most universally relevant view (spend by category).
    default = suggest_charts_fallback("zzzz unrelated", catalog)
    assert [p["dataset_id"] for p in default] == ["spend_by_category"]


def test_resolve_specs_carry_real_data() -> None:
    catalog = build_chart_catalog(_spend_output())
    suggestions = [{"dataset_id": "spend_by_category", "type": "pie", "title": "T", "rationale": "R"}]
    specs = resolve_chart_specs(suggestions, catalog)
    assert len(specs) == 1
    spec = specs[0]
    assert spec["type"] == "pie"  # LLM-chosen type honored
    assert spec["title"] == "T"
    assert spec["data"][0]["spend"] == 600.0  # data still sourced from skill output


def test_build_chart_specs_returns_renderable(monkeypatch) -> None:
    # Force the deterministic path (no LLM) so the test is hermetic.
    monkeypatch.setattr("app.opar.visualization.suggest_charts_llm", lambda *a, **k: None)
    specs = build_chart_specs("where can we save the most?", _spend_output())
    assert specs, "expected at least one chart spec"
    for s in specs:
        assert s["type"] in {
            "bar", "hbar", "line", "stacked_bar", "grouped_bar", "pie", "waterfall", "scatter",
        }
        assert s["data"] and s["series"]
