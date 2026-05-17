from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

_MODEL_PARAMS_PATH = (
    Path(__file__).resolve().parents[2]
    / "skills"
    / "savings-modeler"
    / "references"
    / "model_parameters.json"
)


def _load_exec_rate_defaults() -> tuple[float, float]:
    """Read conservative/accelerated execution rates from model_parameters.json.

    T1-5: These were previously hardcoded (0.60 / 0.85).  Loading them from
    model_parameters.json lets a CFO override them without touching code.
    Returns ``(conservative_rate, accelerated_rate)``.
    """
    try:
        params = json.loads(_MODEL_PARAMS_PATH.read_text(encoding="utf-8"))
        defaults = params.get("defaults", {})
        conservative = float(defaults.get("conservative_execution_rate", 0.60))
        accelerated = float(defaults.get("accelerated_execution_rate", 0.85))
        return conservative, accelerated
    except Exception:
        return 0.60, 0.85  # safe fallback if file is missing or malformed


def _npv_phased(
    savings_by_year: List[float],
    costs_by_year: List[float],
    discount_rate: float,
    tax_rate: float,
) -> float:
    """Compute NPV from per-year savings and cost arrays with tax adjustment.

    Year index 0 = Year 1 (discount factor 1/(1+r)^1).
    Tax adjustment: (savings - cost) * (1 - tax_rate) per period.
    """
    npv = 0.0
    for t, (sav, cst) in enumerate(zip(savings_by_year, costs_by_year), start=1):
        after_tax_net = (sav - cst) * (1.0 - tax_rate)
        npv += after_tax_net / (1.0 + discount_rate) ** t
    return npv


def compute_sensitivity(
    value_bridge: Dict[str, Any],
    savings_model: Dict[str, Any] | None = None,
    discount_rate: float = 0.10,
    effective_tax_rate: float = 0.0,
    drivers: Dict[str, float] | None = None,
) -> Dict[str, Any]:
    """Compute sensitivity scenarios for the savings portfolio.

    Parameters
    ----------
    value_bridge : dict
        Output from value_bridge_calculator (provides confidence_bands.mid baseline).
    savings_model : dict, optional
        Output from savings_modeler — used for phased cash flow NPV and partial-success scenario.
    discount_rate : float
        WACC / hurdle rate (default 10%).
    effective_tax_rate : float
        Corporate tax rate applied to after-tax NPV computation (default 0 = pre-tax).
    drivers : dict, optional
        Business driver overrides for scenario modelling. Supported keys:
        - "headcount_growth_pct"  : e.g. 0.10 for +10% headcount growth
        - "revenue_growth_pct"    : e.g. 0.15 for +15% revenue growth
        - "execution_rate_pct"    : override execution probability (0.0–1.0)
        - "timeline_compression_factor": e.g. 0.75 to compress 36 months to 27 months
    """
    conf = value_bridge.get("confidence_bands", {})
    mid = float(conf.get("mid", 0.0))
    low_band = float(conf.get("low", mid * 0.8))
    high_band = float(conf.get("high", mid * 1.2))

    drivers = drivers or {}
    execution_override = drivers.get("execution_rate_pct")
    timeline_factor = float(drivers.get("timeline_compression_factor", 1.0))

    # Build phased cash flows from savings_model when available
    phased_savings: List[float] = [0.0, 0.0, 0.0]
    phased_costs: List[float] = [0.0, 0.0, 0.0]
    partial_savings_3yr = mid  # fallback: use mid band

    if savings_model and savings_model.get("initiatives"):
        for init in savings_model["initiatives"]:
            gs = init.get("gross_savings", {})
            cta = init.get("cost_to_achieve", {})
            phased_savings[0] += float(gs.get("y1", 0.0))
            phased_savings[1] += float(gs.get("y2", 0.0))
            phased_savings[2] += float(gs.get("y3", 0.0))
            phased_costs[0] += float(cta.get("y1", 0.0))
            phased_costs[1] += float(cta.get("y2", 0.0))
            phased_costs[2] += float(cta.get("y3", 0.0))

        # Partial success: top-3 initiatives by 3yr net savings
        top3 = sorted(
            savings_model["initiatives"],
            key=lambda i: i.get("net_savings", {}).get("total_3yr", 0.0),
            reverse=True,
        )[:3]
        partial_savings_3yr = sum(i.get("net_savings", {}).get("total_3yr", 0.0) for i in top3)

    def _scenario_npv(exec_rate: float, tl_months: int, savings_override: List[float] | None = None) -> float:
        sav = savings_override or [s * exec_rate for s in phased_savings]
        # If timeline compressed, shift more savings earlier (simplified linear ramp)
        return _npv_phased(sav, phased_costs, discount_rate, effective_tax_rate)

    def _simple_npv(annual_savings: float, years: float) -> float:
        per_yr = annual_savings / years if years > 0 else 0
        return sum(
            per_yr * (1.0 - effective_tax_rate) / (1.0 + discount_rate) ** t
            for t in range(1, int(years) + 1)
        )

    # T1-5: Load execution rate multipliers from model_parameters.json (configurable).
    _conservative_rate, _accelerated_rate = _load_exec_rate_defaults()

    # Determine execution rates for each scenario (driver override takes precedence)
    base_exec = float(execution_override) if execution_override is not None else 1.0
    conservative_exec = base_exec * _conservative_rate
    accelerated_exec = base_exec * _accelerated_rate

    # Driver-adjusted savings (e.g., headcount growth increases HR/IT spend opportunity)
    headcount_growth = float(drivers.get("headcount_growth_pct", 0.0))
    revenue_growth = float(drivers.get("revenue_growth_pct", 0.0))
    # If business grows, addressable spend pool grows proportionally in volume-driven categories
    volume_growth_factor = 1.0 + max(headcount_growth, revenue_growth)

    scenarios: List[Dict[str, Any]] = [
        {
            "name": "conservative",
            "key_assumption": (
                f"{conservative_exec:.0%} execution rate — change management risk; "
                + (f"headcount +{headcount_growth:.0%}" if headcount_growth else "baseline business drivers")
            ),
            "savings_3yr": round(mid * conservative_exec, 2),
            "timeline_months": int(36 * timeline_factor),
            "npv_pretax": round(_simple_npv(mid * conservative_exec, 3.0 * timeline_factor), 2),
            "npv_aftertax": round(_simple_npv(mid * conservative_exec, 3.0 * timeline_factor) * (1.0 - effective_tax_rate), 2),
            "execution_rate": conservative_exec,
            "driver_adjusted": bool(drivers),
        },
        {
            "name": "base",
            "key_assumption": (
                f"{base_exec:.0%} execution rate — all initiatives delivered on plan; "
                + (f"revenue growth +{revenue_growth:.0%}" if revenue_growth else "steady-state business")
            ),
            "savings_3yr": round(mid * base_exec, 2),
            "timeline_months": int(36 * timeline_factor),
            "npv_pretax": round(_scenario_npv(base_exec, int(36 * timeline_factor)), 2),
            "npv_aftertax": round(_scenario_npv(base_exec, int(36 * timeline_factor)) * (1.0 - effective_tax_rate) if not phased_savings[0] else _scenario_npv(base_exec, int(36 * timeline_factor)), 2),
            "execution_rate": base_exec,
            "driver_adjusted": bool(drivers),
        },
        {
            "name": "accelerated",
            "key_assumption": (
                f"{accelerated_exec:.0%} savings in 18 months — rapid consolidation; "
                + (f"timeline compressed ×{timeline_factor:.2f}" if timeline_factor != 1.0 else "compressed delivery")
            ),
            "savings_3yr": round(mid * accelerated_exec, 2),
            "timeline_months": int(18 * timeline_factor),
            "npv_pretax": round(_simple_npv(mid * accelerated_exec, 1.5 * timeline_factor), 2),
            "npv_aftertax": round(_simple_npv(mid * accelerated_exec, 1.5 * timeline_factor) * (1.0 - effective_tax_rate), 2),
            "execution_rate": accelerated_exec,
            "driver_adjusted": bool(drivers),
        },
        {
            "name": "delayed",
            "key_assumption": "Full savings but 48-month timeline — contract lock-ins and organizational friction",
            "savings_3yr": round(mid * base_exec, 2),
            "timeline_months": int(48 * timeline_factor),
            "npv_pretax": round(_simple_npv(mid * base_exec, 4.0 * timeline_factor), 2),
            "npv_aftertax": round(_simple_npv(mid * base_exec, 4.0 * timeline_factor) * (1.0 - effective_tax_rate), 2),
            "execution_rate": base_exec,
            "driver_adjusted": bool(drivers),
        },
        {
            "name": "partial_success",
            "key_assumption": "Only top-3 categories deliver — lower-priority initiatives not executed",
            "savings_3yr": round(partial_savings_3yr, 2),
            "timeline_months": int(36 * timeline_factor),
            "npv_pretax": round(_simple_npv(partial_savings_3yr, 3.0 * timeline_factor), 2),
            "npv_aftertax": round(_simple_npv(partial_savings_3yr, 3.0 * timeline_factor) * (1.0 - effective_tax_rate), 2),
            "execution_rate": 1.0,
            "driver_adjusted": False,
        },
        {
            "name": "volume_growth",
            "key_assumption": (
                f"Business grows {volume_growth_factor - 1:.0%} — addressable spend pool expands; "
                "savings opportunity scales with volume"
            ),
            "savings_3yr": round(mid * base_exec * volume_growth_factor, 2),
            "timeline_months": int(36 * timeline_factor),
            "npv_pretax": round(_simple_npv(mid * base_exec * volume_growth_factor, 3.0 * timeline_factor), 2),
            "npv_aftertax": round(_simple_npv(mid * base_exec * volume_growth_factor, 3.0 * timeline_factor) * (1.0 - effective_tax_rate), 2),
            "execution_rate": base_exec,
            "driver_adjusted": True,
        },
    ]

    # Scenario 7: bounce_back — high bounce-back risk levers (sustainability_score < 0.50) revert
    # 80% of their savings by month 30. This scenario quantifies the NPV cost of not sustaining savings.
    bounce_back_reversion_rate = 0.80
    low_sustainability_threshold = 0.50
    bounce_back_month = 30  # savings start reverting at month 30

    if savings_model and savings_model.get("initiatives"):
        at_risk_3yr = 0.0
        sustained_3yr = 0.0
        for init in savings_model["initiatives"]:
            sust = float(init.get("sustainability_score", 0.65))
            gs = init.get("gross_savings", {})
            total_3yr = float(gs.get("total_3yr", 0.0))
            if sust < low_sustainability_threshold:
                # Only Y1+Y2 savings are realised; Y3 reverts at bounce_back_reversion_rate
                y1 = float(gs.get("y1", 0.0))
                y2 = float(gs.get("y2", 0.0))
                y3_reversion = float(gs.get("y3", 0.0)) * bounce_back_reversion_rate
                at_risk_3yr += y1 + y2 - y3_reversion
            else:
                sustained_3yr += total_3yr
        bounce_back_3yr = at_risk_3yr + sustained_3yr
        bounce_back_npv_pretax = _scenario_npv(base_exec, int(36 * timeline_factor),
                                               savings_override=[phased_savings[0], phased_savings[1],
                                                                  phased_savings[2] * (1.0 - bounce_back_reversion_rate)])
    else:
        bounce_back_3yr = mid * base_exec * (1.0 - bounce_back_reversion_rate * 0.33)
        bounce_back_npv_pretax = _simple_npv(bounce_back_3yr, 3.0 * timeline_factor)

    bounce_back_npv_aftertax = bounce_back_npv_pretax * (1.0 - effective_tax_rate)

    scenarios.append({
        "name": "bounce_back",
        "key_assumption": (
            f"Levers with sustainability score < {low_sustainability_threshold} (demand management, maverick compliance, etc.) "
            f"revert {bounce_back_reversion_rate:.0%} of savings by month {bounce_back_month}. "
            "Structural/technology levers remain intact."
        ),
        "savings_3yr": round(bounce_back_3yr, 2),
        "timeline_months": int(36 * timeline_factor),
        "npv_pretax": round(bounce_back_npv_pretax, 2),
        "npv_aftertax": round(bounce_back_npv_aftertax, 2),
        "execution_rate": base_exec,
        "driver_adjusted": False,
        "bounce_back_warning": True,
    })

    return {
        "discount_rate": discount_rate,
        "effective_tax_rate": effective_tax_rate,
        "baseline_mid_savings": mid,
        "confidence_bands": {"low": low_band, "mid": mid, "high": high_band},
        "driver_inputs": drivers,
        "scenarios": scenarios,
        "methodology_note": (
            "NPV computed on after-tax net savings using phased cash flows where available. "
            "Pre-tax NPV also provided for operational planning. "
            "Volume growth scenario scales the addressable spend pool by the larger of "
            "headcount or revenue growth rate. "
            "Bounce-back scenario models reversion risk for low-sustainability levers "
            "(sustainability score < 0.50) which revert 80% of savings by month 30."
        ),
    }
