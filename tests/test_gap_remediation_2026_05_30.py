"""Regression tests for the 2026-05-30 gap-remediation batch.

Covers:
- Sensitivity NPV tax: after-tax = pre-tax * (1 - tax) for every scenario; equal at tax=0.
- spend_profiler currency_breakdown reconciles with total_spend (reporting currency).
- temporal_analyzer period-grain handling (quarterly CAGR/YoY).
- _compute_irr never raises on pathological cashflows.
"""
from __future__ import annotations

import pytest

from app.models import NormalizedSpendLine
from app.skills import engine
from app.skills.engine.savings import _compute_irr
from app.services.sensitivity import compute_sensitivity


def _line(row_id, category_id, amount, currency="USD", fx=1.0, fiscal_period="2025-01"):
    return NormalizedSpendLine(
        row_id=row_id,
        supplier=f"V{row_id}",
        description="x",
        category_id=category_id,
        category_name=category_id,
        amount=amount,
        amount_type="actual",
        fiscal_period=fiscal_period,
        currency=currency,
        fx_rate_to_reporting=fx,
        amount_reporting=amount * fx,
    )


_VALUE_BRIDGE = {"confidence_bands": {"low": 80_000.0, "mid": 100_000.0, "high": 120_000.0}}
_SAVINGS_MODEL = {
    "initiatives": [
        {
            "gross_savings": {"y1": 40_000.0, "y2": 40_000.0, "y3": 40_000.0, "total_3yr": 120_000.0},
            "cost_to_achieve": {"y1": 10_000.0, "y2": 5_000.0, "y3": 5_000.0},
            "net_savings": {"total_3yr": 100_000.0},
            "sustainability_score": 0.70,
        }
    ]
}


class TestSensitivityTax:
    def test_aftertax_is_pretax_times_one_minus_tax(self):
        tax = 0.25
        result = compute_sensitivity(
            _VALUE_BRIDGE, savings_model=_SAVINGS_MODEL,
            discount_rate=0.10, effective_tax_rate=tax,
        )
        scenarios = result["scenarios"]
        assert len(scenarios) >= 6
        for sc in scenarios:
            pretax = sc["npv_pretax"]
            aftertax = sc["npv_aftertax"]
            # After-tax must be a clean (1 - tax) haircut of pre-tax — not double-taxed.
            assert aftertax == pytest.approx(pretax * (1.0 - tax), rel=1e-3, abs=1.0), sc["name"]
            if pretax > 0:
                assert aftertax < pretax, sc["name"]

    def test_no_tax_means_pretax_equals_aftertax(self):
        result = compute_sensitivity(
            _VALUE_BRIDGE, savings_model=_SAVINGS_MODEL,
            discount_rate=0.10, effective_tax_rate=0.0,
        )
        for sc in result["scenarios"]:
            assert sc["npv_aftertax"] == pytest.approx(sc["npv_pretax"], abs=0.01), sc["name"]


class TestCurrencyBreakdownReconciles:
    def test_multi_currency_sum_equals_total_spend(self):
        lines = [
            _line(1, "IT", 100.0, currency="GBP", fx=1.27),
            _line(2, "HR", 200.0, currency="EUR", fx=1.08),
            _line(3, "IT", 300.0, currency="USD", fx=1.0),
        ]
        profile = engine.spend_profiler(lines)
        assert profile["multi_currency"] is True
        assert sum(profile["currency_breakdown"].values()) == pytest.approx(
            profile["total_spend"], rel=1e-6
        )


class TestTemporalPeriodGrain:
    def test_quarterly_grain_yoy_and_cagr(self):
        # 5 quarters spanning two years so YoY (Q1->prior Q1) is computable.
        periods = ["2024-Q1", "2024-Q2", "2024-Q3", "2024-Q4", "2025-Q1"]
        lines = [
            _line(i + 1, "IT", 100_000.0 + i * 10_000.0, fiscal_period=p)
            for i, p in enumerate(periods)
        ]
        result = engine.temporal_analyzer(lines)
        assert result["temporal_available"] is True
        assert result["period_grain"] == "quarterly"
        # YoY populated for 2025-Q1 (compares to 2024-Q1).
        q1_2025 = next(p for p in result["period_trends"] if p["period"] == "2025-Q1")
        assert q1_2025["yoy_pct"] is not None
        # CAGR must not be the ~3x-inflated monthly-assumption value.
        # Spend grew 100k->140k over 4 quarters (1 year) ≈ 40% annual.
        assert result["cagr_pct"] is not None
        assert 20.0 < result["cagr_pct"] < 60.0


class TestIRRGuard:
    @pytest.mark.parametrize("cashflows", [
        [-100.0, 200.0, -150.0],
        [-100.0, 0.0, 0.0, 1000.0, -5000.0],
        [-1.0, 100.0, -100.0, 100.0, -100.0],
    ])
    def test_pathological_cashflows_do_not_raise(self, cashflows):
        result = _compute_irr(cashflows)
        assert result is None or isinstance(result, float)
