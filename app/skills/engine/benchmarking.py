"""Peer benchmarker, internal benchmarker, heuristic analyzer, root cause analyzer."""
from __future__ import annotations

import math
from collections import defaultdict
from statistics import median
from typing import Any, Dict, List, Optional, Tuple

from app.models import NormalizedSpendLine

from ._loaders import (
    _get_heuristic_ranges,
    _get_per_employee_targets,
    _get_root_cause_thresholds,
    _HEADCOUNT_APPLICABLE_CATEGORIES,
)
from .profiler import resolve_eligible_levers


def _category_pct_of_revenue(category_spend: float, revenue: float) -> float:
    if revenue <= 0:
        return 0.0
    return (category_spend / revenue) * 100


def peer_benchmarker(
    profile: Dict[str, Any],
    benchmark_data: Dict[str, Any],
    industry: str,
    revenue: float,
    selected_dataset: Dict[str, Any] | None = None,
    selection_rationale: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    category_bench = benchmark_data.get("benchmarks", {}).get(industry, {}).get("categories", {})
    rows = []
    source_name = "industry_benchmarks.json"
    if selected_dataset:
        source_name = str(selected_dataset.get("source") or selected_dataset.get("dataset_id") or source_name)
    for row in profile.get("category_profile", []):
        cid = row["category_id"]
        metrics = category_bench.get(cid)
        if not metrics:
            continue
        actual_pct = _category_pct_of_revenue(row["spend"], revenue)
        p50 = metrics.get("P50", 0.0)
        p25 = metrics.get("P25", 0.0)
        if actual_pct >= metrics.get("P90", 999):
            percentile = "P90+"
        elif actual_pct >= metrics.get("P75", 999):
            percentile = "P75-P90"
        elif actual_pct >= p50:
            percentile = "P50-P75"
        elif actual_pct >= p25:
            percentile = "P25-P50"
        else:
            percentile = "<P25"
        saving_pct = max(actual_pct - p25, 0.0)
        rows.append(
            {
                "category_id": cid,
                "category_name": row["category_name"],
                "actual_pct_of_revenue": actual_pct,
                "benchmark_target_pct": p25,
                "benchmark_p50_pct": p50,
                "percentile_band": percentile,
                "estimated_saving_amount": (saving_pct / 100) * revenue,
                "source": source_name,
            }
        )

    sample_n = int((selected_dataset or {}).get("sample_size") or 0)
    vintage_date = (selected_dataset or {}).get("vintage_date")
    specificity = float((selected_dataset or {}).get("specificity_score") or 0.5)

    _ci_half = max(0.05, 0.20 / math.sqrt(max(sample_n, 1))) * (1.0 - 0.5 * specificity)

    for row in rows:
        target = row["benchmark_target_pct"]
        row["benchmark_sample_n"] = sample_n
        row["benchmark_vintage"] = vintage_date
        row["benchmark_ci"] = {
            "lower": round(max(target * (1 - _ci_half), 0.0), 4),
            "upper": round(target * (1 + _ci_half), 4),
            "half_width_pct": round(_ci_half * 100, 2),
        }

    benchmark_metadata: Dict[str, Any] = {}
    if selected_dataset:
        is_seed = selected_dataset.get("source") == "platform_seed"
        benchmark_metadata = {
            "source_name": f"{source_name} (illustrative)" if is_seed else source_name,
            "vintage_date": vintage_date,
            "specificity_score": specificity,
            "sample_n": sample_n,
            "data_quality_note": selected_dataset.get("data_quality_note", ""),
            "ci_half_width_pct": round(_ci_half * 100, 2),
        }
    return {
        "industry": industry,
        "comparisons": rows,
        "benchmark_dataset": selected_dataset or {},
        "selection_rationale": selection_rationale or {},
        "benchmark_metadata": benchmark_metadata,
    }


def internal_benchmarker(lines: List[NormalizedSpendLine]) -> Dict[str, Any]:
    by_bu_category: Dict[Tuple[str, str], float] = defaultdict(float)
    for line in lines:
        bu = line.business_unit or "Unknown BU"
        by_bu_category[(bu, line.category_id)] += line.amount

    categories: Dict[str, List[Tuple[str, float]]] = defaultdict(list)
    for (bu, cat), amount in by_bu_category.items():
        categories[cat].append((bu, amount))

    variances = []
    for cat, pairs in categories.items():
        values = [x[1] for x in pairs]
        if len(values) < 2:
            continue
        max_v, min_v = max(values), min(values)
        spread = ((max_v - min_v) / max_v) if max_v else 0.0
        variances.append(
            {
                "category_id": cat,
                "max_spend": max_v,
                "min_spend": min_v,
                "median_spend": median(values),
                "internal_spread": spread,
                "flagged_gt_20pct": spread > 0.2,
                "segments": [{"segment": bu, "spend": amount} for bu, amount in pairs],
            }
        )
    return {"internal_variance": variances}


def heuristic_analyzer(
    profile: Dict[str, Any],
    revenue: float,
    headcount: float | None = None,
) -> Dict[str, Any]:
    ranges = _get_heuristic_ranges()
    per_emp_targets = _get_per_employee_targets()
    rows = []
    for cat in profile.get("category_profile", []):
        cid = cat["category_id"]
        actual = _category_pct_of_revenue(cat["spend"], revenue)
        target = ranges.get(cid, actual)
        gap = max(actual - target, 0.0)
        row: Dict[str, Any] = {
            "category_id": cid,
            "actual_pct_of_revenue": actual,
            "heuristic_target_pct": target,
            "estimated_saving_amount": (gap / 100) * revenue,
        }
        if headcount and headcount > 0 and cid in _HEADCOUNT_APPLICABLE_CATEGORIES:
            emp_target = per_emp_targets.get(cid)
            if emp_target:
                actual_per_emp = cat["spend"] / headcount
                emp_gap = max(actual_per_emp - emp_target, 0.0)
                row["headcount_based_saving_amount"] = emp_gap * headcount
                row["actual_cost_per_employee"] = round(actual_per_emp, 2)
                row["target_cost_per_employee"] = emp_target
        rows.append(row)
    return {"heuristic_findings": rows}


def root_cause_analyzer(
    profile: Dict[str, Any],
    peer: Dict[str, Any],
    lines: List[NormalizedSpendLine],
    headcount: float | None = None,
    transaction_count: float | None = None,
    industry: str = "",
    annual_revenue: float = 0.0,
) -> Dict[str, Any]:
    cfg = _get_root_cause_thresholds()
    th = cfg.get("thresholds", {})
    rates = cfg.get("addressable_rates", {})
    include_bands = set(th.get("peer_percentile_include", ["P50-P75", "P75-P90", "P90+"]))
    hhi_max = float(th.get("supplier_fragmentation_hhi_max", 0.15))
    min_suppliers = int(th.get("supplier_fragmentation_min_suppliers", 5))
    maverick_min = float(th.get("maverick_spend_ratio_min", 0.2))
    cpt_max = float(th.get("cost_per_transaction_max", 1000.0))

    spend_by_cat = {c["category_id"]: c for c in profile.get("category_profile", [])}
    suppliers_by_cat: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    po_spend_by_cat: Dict[str, float] = defaultdict(float)
    off_po_spend_by_cat: Dict[str, float] = defaultdict(float)

    for line in lines:
        suppliers_by_cat[line.category_id][line.supplier] += line.amount
        desc = (line.description or "").lower()
        if "po" in desc:
            po_spend_by_cat[line.category_id] += line.amount
        else:
            off_po_spend_by_cat[line.category_id] += line.amount

    eligible_levers = resolve_eligible_levers(
        industry=industry,
        spend_profile=profile,
        headcount=float(headcount or 0.0),
        annual_revenue=annual_revenue,
        root_causes=[],
    )
    eligible_lever_by_id: Dict[str, Dict[str, Any]] = {lv["lever_id"]: lv for lv in eligible_levers}
    levers_for_category: Dict[str, List[Dict[str, Any]]] = {}
    for lv in eligible_levers:
        for sig in lv["trigger_signals"]:
            if sig.startswith("category:") and sig.endswith("_present"):
                cid_sig = sig.split(":")[1].replace("_present", "")
                levers_for_category.setdefault(cid_sig, []).append(lv)

    outputs: List[Dict[str, Any]] = []
    for cmp_row in peer.get("comparisons", []):
        cid = cmp_row["category_id"]
        percentile_band = cmp_row.get("percentile_band", "")
        if percentile_band not in include_bands:
            continue
        cat = spend_by_cat.get(cid, {})
        total = float(cat.get("spend", 0.0))
        if total <= 0:
            continue

        supplier_map = suppliers_by_cat.get(cid, {})
        hhi = 0.0
        if total > 0:
            hhi = sum((amt / total) ** 2 for amt in supplier_map.values())
        maverick = off_po_spend_by_cat.get(cid, 0.0) / total if total else 0.0

        root_causes: List[Dict[str, Any]] = []
        if hhi < hhi_max and len(supplier_map) >= min_suppliers:
            root_causes.append(
                {
                    "diagnosis": f"Supplier fragmentation with {len(supplier_map)} active suppliers (HHI {hhi:.2f})",
                    "confidence": "high",
                    "addressable_spend": total * float(rates.get("supplier_consolidation", 0.2)),
                    "recommended_lever": "supplier_consolidation",
                    "implementation_approach": "Consolidate vendors and rebid top spend clusters.",
                    "implementation_complexity": "medium",
                    "estimated_timeline_months": 12,
                }
            )

        if maverick > maverick_min:
            root_causes.append(
                {
                    "diagnosis": f"High maverick buying ({maverick:.0%} off-PO spend)",
                    "confidence": "medium",
                    "addressable_spend": total * float(rates.get("maverick_compliance", 0.1)),
                    "recommended_lever": "maverick_compliance",
                    "implementation_approach": "Enforce PO-first buying and renegotiate non-compliant contracts.",
                    "implementation_complexity": "low",
                    "estimated_timeline_months": 6,
                }
            )

        if transaction_count and transaction_count > 0 and (total / transaction_count) > cpt_max:
            root_causes.append(
                {
                    "diagnosis": "Cost per transaction above expected norm",
                    "confidence": "medium",
                    "addressable_spend": total * float(rates.get("demand_management", 0.08)),
                    "recommended_lever": "demand_management",
                    "implementation_approach": "Tighten demand policies and approvals for low-value requests.",
                    "implementation_complexity": "medium",
                    "estimated_timeline_months": 9,
                }
            )

        if not root_causes:
            root_causes.append(
                {
                    "diagnosis": "No strong structural driver detected; baseline commercial optimization applicable",
                    "confidence": "low",
                    "addressable_spend": total * float(rates.get("baseline_optimization", 0.05)),
                    "recommended_lever": "contract_renegotiation",
                    "implementation_approach": "Targeted renegotiation on top suppliers.",
                    "implementation_complexity": "low",
                    "estimated_timeline_months": 6,
                }
            )

        cat_levers = levers_for_category.get(cid, [])
        if not cat_levers:
            cat_levers = [lv for lv in eligible_levers if "universal_lever" in lv["trigger_signals"]][:5]
        top_levers = sorted(cat_levers, key=lambda x: x["eligibility_score"], reverse=True)[:5]

        outputs.append(
            {
                "category_id": cid,
                "category_name": cmp_row.get("category_name", cid),
                "root_causes": root_causes,
                "eligible_levers": [
                    {
                        "lever_id": lv["lever_id"],
                        "lever_name": lv["lever_name"],
                        "lever_family": lv["lever_family"],
                        "eligibility_score": lv["eligibility_score"],
                        "sustainability_score": lv["sustainability_score"],
                        "bounce_back_risk": lv["bounce_back_risk"],
                        "complexity_tier": lv["complexity_tier"],
                        "condition_precedents": lv["condition_precedents"],
                    }
                    for lv in top_levers
                ],
                "non_addressable_rationale": "Portion may be constrained by contractual or regulatory obligations.",
            }
        )
    return {"root_cause_findings": outputs, "eligible_levers_summary": eligible_levers}
