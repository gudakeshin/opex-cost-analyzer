"""FP&A skills: bva_analyzer, temporal_analyzer, payment_terms_optimizer."""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional

from app.models import NormalizedSpendLine, is_actual

from ._loaders import _get_dpo_benchmarks


# ---------------------------------------------------------------------------
# Budget vs. Actuals Analyzer
# ---------------------------------------------------------------------------

def bva_analyzer(lines: List[NormalizedSpendLine]) -> Dict[str, Any]:
    """Budget vs. Actuals (BvA) analysis."""
    actual_by_cat: Dict[str, float] = defaultdict(float)
    budget_by_cat: Dict[str, float] = defaultdict(float)
    cat_names: Dict[str, str] = {}

    for line in lines:
        amt = line.reporting_amount
        cat_names[line.category_id] = line.category_name
        if line.amount_type == "actual":
            actual_by_cat[line.category_id] += amt
        elif line.amount_type == "budget":
            budget_by_cat[line.category_id] += amt

    all_cats = set(actual_by_cat.keys()) | set(budget_by_cat.keys())
    if not all_cats or not budget_by_cat:
        return {
            "bva_available": False,
            "reason": "No budget lines detected. Upload a budget file to enable BvA.",
            "variances": [],
        }

    variances: List[Dict[str, Any]] = []
    total_actual = 0.0
    total_budget = 0.0
    total_variance = 0.0

    for cid in sorted(all_cats):
        actual_spend = actual_by_cat.get(cid, 0.0)
        budget_spend = budget_by_cat.get(cid, 0.0)
        total_variance_cat = actual_spend - budget_spend
        variance_pct = (total_variance_cat / budget_spend * 100) if budget_spend else None
        flag = (
            "over_budget" if total_variance_cat > 0
            else ("under_budget" if total_variance_cat < 0 else "on_budget")
        )

        variances.append(
            {
                "category_id": cid,
                "category_name": cat_names.get(cid, cid),
                "actual_spend": round(actual_spend, 2),
                "budget_spend": round(budget_spend, 2),
                "total_variance": round(total_variance_cat, 2),
                "variance_pct": round(variance_pct, 1) if variance_pct is not None else None,
                "flag": flag,
                "primary_driver": "spend",
            }
        )
        total_actual += actual_spend
        total_budget += budget_spend
        total_variance += total_variance_cat

    variances.sort(key=lambda x: abs(x["total_variance"]), reverse=True)

    return {
        "bva_available": True,
        "total_actual": round(total_actual, 2),
        "total_budget": round(total_budget, 2),
        "total_variance": round(total_variance, 2),
        "total_variance_pct": round(total_variance / total_budget * 100, 1) if total_budget else None,
        "categories_over_budget": sum(1 for v in variances if v["flag"] == "over_budget"),
        "categories_under_budget": sum(1 for v in variances if v["flag"] == "under_budget"),
        "variances": variances,
        "decomposition_note": (
            "Spend variance only. Price/volume/mix decomposition requires per-unit quantity "
            "data not present in the source file."
        ),
    }


# ---------------------------------------------------------------------------
# Temporal Analyzer
# ---------------------------------------------------------------------------

def _infer_period_grain(periods: List[str]) -> tuple[int, int, str]:
    """Infer ``(months_per_period, periods_per_year, grain_label)`` from fiscal_period strings.

    Recognizes ``YYYY-MM`` (monthly), ``YYYY-Qn`` (quarterly) and ``YYYY`` (annual).
    Picks the dominant recognized format; falls back to monthly when unknown/mixed.
    Without this, CAGR and annualized run-rate silently assume every period is one
    month, over-stating CAGR ~3x and mis-scaling run-rate for quarterly/annual data.
    """
    monthly = quarterly = annual = 0
    for p in periods:
        s = (p or "").strip().upper()
        if len(s) == 7 and s[4] == "-" and s[5:7].isdigit():
            monthly += 1
        elif len(s) >= 6 and s[4] == "-" and s[5] == "Q":
            quarterly += 1
        elif len(s) == 4 and s.isdigit():
            annual += 1
    counts = {"monthly": monthly, "quarterly": quarterly, "annual": annual}
    label = max(counts, key=lambda k: counts[k])
    if counts[label] == 0:
        return 1, 12, "monthly"
    return {"monthly": (1, 12), "quarterly": (3, 4), "annual": (12, 1)}[label] + (label,)


def _prior_year_period(fp: str, grain: str) -> Optional[str]:
    """Return the fiscal_period one year earlier in the same grain format, or None."""
    s = (fp or "").strip()
    try:
        if grain == "monthly" and len(s) == 7 and s[4] == "-":
            return f"{int(s[:4]) - 1}-{s[5:7]}"
        if grain == "quarterly" and len(s) >= 6 and s[4] == "-":
            return f"{int(s[:4]) - 1}-{s[5:]}"
        if grain == "annual" and len(s) == 4:
            return str(int(s) - 1)
    except ValueError:
        return None
    return None


def temporal_analyzer(lines: List[NormalizedSpendLine]) -> Dict[str, Any]:
    """Period-over-period spend trend analysis."""
    actual_lines = [x for x in lines if is_actual(x)]
    if not actual_lines:
        actual_lines = lines

    period_totals: Dict[str, float] = {}
    cat_period: Dict[str, Dict[str, float]] = {}
    cat_names: Dict[str, str] = {}

    for line in actual_lines:
        fp = line.fiscal_period
        if not fp:
            continue
        amt = line.reporting_amount
        period_totals[fp] = period_totals.get(fp, 0.0) + amt
        cat_period.setdefault(line.category_id, {})[fp] = (
            cat_period.get(line.category_id, {}).get(fp, 0.0) + amt
        )
        cat_names[line.category_id] = line.category_name

    sorted_periods = sorted(period_totals.keys())
    if len(sorted_periods) < 2:
        return {
            "temporal_available": False,
            "reason": "Fewer than 2 fiscal periods detected. Ensure spend_date is populated.",
            "period_count": len(sorted_periods),
            "period_trends": [],
            "category_trends": [],
        }

    months_per_period, periods_per_year, grain_label = _infer_period_grain(sorted_periods)

    period_trends: List[Dict[str, Any]] = []
    for i, fp in enumerate(sorted_periods):
        spend = period_totals[fp]
        prev_spend = period_totals[sorted_periods[i - 1]] if i > 0 else None
        mom_delta = spend - prev_spend if prev_spend is not None else None
        mom_pct = (mom_delta / prev_spend * 100) if (mom_delta is not None and prev_spend and prev_spend > 0) else None
        yoy_period = _prior_year_period(fp, grain_label)
        yoy_spend = period_totals.get(yoy_period) if yoy_period else None
        yoy_delta = (spend - yoy_spend) if yoy_spend is not None else None
        yoy_pct = (yoy_delta / yoy_spend * 100) if (yoy_delta is not None and yoy_spend and yoy_spend > 0) else None
        period_trends.append(
            {
                "period": fp,
                "total_spend": round(spend, 2),
                "mom_delta": round(mom_delta, 2) if mom_delta is not None else None,
                "mom_pct": round(mom_pct, 1) if mom_pct is not None else None,
                "yoy_delta": round(yoy_delta, 2) if yoy_delta is not None else None,
                "yoy_pct": round(yoy_pct, 1) if yoy_pct is not None else None,
            }
        )

    if len(sorted_periods) >= periods_per_year:
        annualized_run_rate = sum(period_totals[p] for p in sorted_periods[-periods_per_year:])
        arr_basis = "TTM"
    else:
        recent = sorted_periods[-3:]
        annualized_run_rate = (sum(period_totals[p] for p in recent) / len(recent)) * periods_per_year
        arr_basis = f"{len(recent)}P_extrapolated"

    cagr_pct: float | None = None
    first_total = period_totals[sorted_periods[0]]
    last_total = period_totals[sorted_periods[-1]]
    months_elapsed = (len(sorted_periods) - 1) * months_per_period
    if len(sorted_periods) >= 3 and first_total > 0 and months_elapsed > 0:
        cagr_pct = round(
            ((last_total / first_total) ** (12.0 / months_elapsed) - 1.0) * 100, 1
        )

    category_trends: List[Dict[str, Any]] = []
    for cid, period_map in cat_period.items():
        sorted_ps = sorted(period_map.keys())
        if len(sorted_ps) < 2:
            continue
        first_spend = period_map[sorted_ps[0]]
        last_spend = period_map[sorted_ps[-1]]
        total_change = last_spend - first_spend
        change_pct = (total_change / first_spend * 100) if first_spend > 0 else None
        trend_dir = "increasing" if total_change > 0 else ("decreasing" if total_change < 0 else "flat")

        if len(sorted_ps) >= periods_per_year:
            cat_run_rate = sum(period_map.get(p, 0.0) for p in sorted_ps[-periods_per_year:])
            cat_arr_basis = "TTM"
        else:
            cat_recent = sorted_ps[-3:]
            cat_run_rate = (sum(period_map.get(p, 0.0) for p in cat_recent) / len(cat_recent)) * periods_per_year
            cat_arr_basis = f"{len(cat_recent)}P_extrapolated"

        cat_cagr_pct: float | None = None
        cat_months = (len(sorted_ps) - 1) * months_per_period
        if len(sorted_ps) >= 3 and first_spend > 0 and cat_months > 0:
            cat_cagr_pct = round(
                ((last_spend / first_spend) ** (12.0 / cat_months) - 1.0) * 100, 1
            )

        category_trends.append(
            {
                "category_id": cid,
                "category_name": cat_names.get(cid, cid),
                "periods_available": len(sorted_ps),
                "first_period": sorted_ps[0],
                "last_period": sorted_ps[-1],
                "first_period_spend": round(first_spend, 2),
                "last_period_spend": round(last_spend, 2),
                "total_change": round(total_change, 2),
                "change_pct": round(change_pct, 1) if change_pct is not None else None,
                "trend_direction": trend_dir,
                "annualized_run_rate": round(cat_run_rate, 2),
                "arr_basis": cat_arr_basis,
                "cagr_pct": cat_cagr_pct,
            }
        )

    category_trends.sort(key=lambda x: abs(x["total_change"]), reverse=True)

    return {
        "temporal_available": True,
        "period_count": len(sorted_periods),
        "period_grain": grain_label,
        "first_period": sorted_periods[0],
        "last_period": sorted_periods[-1],
        "annualized_run_rate": round(annualized_run_rate, 2),
        "arr_basis": arr_basis,
        "cagr_pct": cagr_pct,
        "period_trends": period_trends,
        "category_trends": category_trends,
    }


# ---------------------------------------------------------------------------
# Payment Terms Optimizer
# ---------------------------------------------------------------------------

def payment_terms_optimizer(
    lines: List[NormalizedSpendLine],
    wacc: float = 0.10,
    industry: str = "default",
) -> Dict[str, Any]:
    """Identifies working capital improvement from extending payment terms (DPO)."""
    dpo_ref = _get_dpo_benchmarks()
    category_benchmarks = dpo_ref.get("category_benchmarks", {})
    industry_adjustments = dpo_ref.get("industry_adjustments", {})
    default_target_dpo = int(dpo_ref.get("default_target_dpo", 45))
    industry_adj = float(industry_adjustments.get(industry.lower(), industry_adjustments.get("default", 1.0)))

    cat_spend: Dict[str, float] = defaultdict(float)
    cat_terms_weighted: Dict[str, float] = defaultdict(float)
    cat_terms_lines: Dict[str, int] = defaultdict(int)
    cat_names: Dict[str, str] = {}
    actual_lines = [x for x in lines if is_actual(x)]
    if not actual_lines:
        actual_lines = lines

    for line in actual_lines:
        amt = line.reporting_amount
        cat_spend[line.category_id] += amt
        cat_names[line.category_id] = line.category_name
        if line.payment_terms_days is not None:
            cat_terms_weighted[line.category_id] += line.payment_terms_days * amt
            cat_terms_lines[line.category_id] += 1

    total_lines = len(actual_lines)
    if total_lines == 0:
        return {"payment_terms_available": False, "reason": "No spend lines.", "opportunities": []}

    lines_with_terms = sum(1 for x in actual_lines if x.payment_terms_days is not None)
    if lines_with_terms == 0:
        return {
            "payment_terms_available": False,
            "reason": "No payment_terms_days data found. Add a 'Payment Terms' column to your spend file.",
            "coverage_pct": 0.0,
            "opportunities": [],
        }

    opportunities: List[Dict[str, Any]] = []
    total_wc_release = 0.0
    total_annual_value = 0.0

    for cid, spend in cat_spend.items():
        if cid not in cat_terms_weighted or spend <= 0:
            continue
        current_dpo = cat_terms_weighted[cid] / spend

        bench = category_benchmarks.get(cid, category_benchmarks.get("OTHER", {}))
        target_dpo_raw = float(bench.get("p50_dpo", default_target_dpo)) * industry_adj
        stretch_dpo = float(bench.get("p75_dpo", target_dpo_raw * 1.3)) * industry_adj
        bench_note = bench.get("notes", "")

        if current_dpo >= stretch_dpo:
            continue

        effective_target = min(stretch_dpo, target_dpo_raw + 15)
        dpo_improvement = effective_target - current_dpo
        if dpo_improvement <= 0:
            continue

        wc_release = (dpo_improvement / 365.0) * spend
        annual_value = wc_release * wacc

        total_wc_release += wc_release
        total_annual_value += annual_value

        opportunities.append(
            {
                "category_id": cid,
                "category_name": cat_names.get(cid, cid),
                "annual_spend": round(spend, 2),
                "current_dpo_days": round(current_dpo, 1),
                "target_dpo_days": round(effective_target, 1),
                "dpo_improvement_days": round(dpo_improvement, 1),
                "working_capital_release": round(wc_release, 2),
                "annual_cash_value_at_wacc": round(annual_value, 2),
                "wacc_used": wacc,
                "benchmark_note": bench_note,
                "lines_with_terms": cat_terms_lines.get(cid, 0),
            }
        )

    opportunities.sort(key=lambda x: x["working_capital_release"], reverse=True)

    return {
        "payment_terms_available": True,
        "wacc": wacc,
        "industry": industry,
        "coverage_pct": round(lines_with_terms / total_lines * 100, 1),
        "total_working_capital_release": round(total_wc_release, 2),
        "total_annual_cash_value": round(total_annual_value, 2),
        "opportunity_count": len(opportunities),
        "opportunities": opportunities,
        "note": "Working capital release is a one-time cash flow benefit. Annual value represents the WACC-based opportunity cost of capital freed.",
    }
