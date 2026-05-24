"""Savings modeler, value bridge, data validator, IRR helper."""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from app.models import NormalizedSpendLine

from ._loaders import _get_model_params
from .profiler import resolve_eligible_levers


# ---------------------------------------------------------------------------
# IRR helper
# ---------------------------------------------------------------------------

def _compute_irr(
    cashflows: list[float],
    guess: float = 0.1,
    max_iter: int = 100,
    tol: float = 1e-6,
) -> float | None:
    """IRR via Newton-Raphson. Returns percentage (e.g. 23.4) or None if not solvable."""
    signs = {1 if c > 0 else -1 for c in cashflows if c != 0}
    if len(signs) < 2:
        return None
    r = guess
    for _ in range(max_iter):
        npv = sum(cf / (1.0 + r) ** t for t, cf in enumerate(cashflows))
        dnpv = sum(-t * cf / (1.0 + r) ** (t + 1) for t, cf in enumerate(cashflows) if t > 0)
        if abs(dnpv) < 1e-12:
            break
        r_new = r - npv / dnpv
        if abs(r_new - r) < tol:
            return round(r_new * 100.0, 1) if r_new > -1.0 else None
        r = r_new
    return None


# ---------------------------------------------------------------------------
# Savings modeler
# ---------------------------------------------------------------------------

_OCR_HAIRCUTS: Dict[str, float] = {"high": 0.80, "medium": 0.90, "low": 1.0}
_GOVERNANCE_Y3_UPLIFT = 1.06


def savings_modeler(
    value_bridge_raw: Dict[str, Any],
    root_cause_outputs: Dict[str, Any],
    discount_rate: float | None = None,
    planning_horizon_years: int | None = None,
    cost_to_achieve_inputs: Dict[str, Dict[str, float]] | None = None,
    effective_tax_rate: float | None = None,
    industry: str = "",
    spend_profile: Dict[str, Any] | None = None,
    headcount: float = 0.0,
    annual_revenue: float = 0.0,
    tco_inputs: Optional[Dict[str, Dict[str, float]]] = None,
) -> Dict[str, Any]:
    params = _get_model_params()
    defaults = params.get("defaults", {})
    lever_by_source = params.get("lever_by_source", {})
    phasing_curves = params.get("phasing_curves", {})
    savings_type_by_lever = params.get("savings_type_by_lever", {})
    impl_cost_phasing = params.get("implementation_cost_phasing", {})
    discount_rate = float(discount_rate if discount_rate is not None else defaults.get("discount_rate", 0.1))
    planning_horizon_years = int(planning_horizon_years if planning_horizon_years is not None else defaults.get("planning_horizon_years", 3))
    tax_rate = float(effective_tax_rate if effective_tax_rate is not None else defaults.get("effective_tax_rate", 0.0))
    cta_y2_fraction = float(defaults.get("cta_y2_fraction_of_y1", 0.25))

    cost_to_achieve_inputs = cost_to_achieve_inputs or {}
    root_by_cat = {x["category_id"]: x for x in root_cause_outputs.get("root_cause_findings", [])}

    root_cause_list = root_cause_outputs.get("root_cause_findings", [])
    eligible_levers = resolve_eligible_levers(
        industry=industry,
        spend_profile=spend_profile or {},
        headcount=headcount,
        annual_revenue=annual_revenue,
        root_causes=root_cause_list,
    )
    lever_meta_by_id: Dict[str, Dict[str, Any]] = {lv["lever_id"]: lv for lv in reversed(eligible_levers)}
    best_lever_for_category: Dict[str, str] = {}
    for lv in eligible_levers:
        if "universal_lever" in lv["trigger_signals"] and not lv["root_cause_match"]:
            continue
        for sig in lv["trigger_signals"]:
            if sig.startswith("category:") and sig.endswith("_present"):
                cid_from_sig = sig.split(":")[1].replace("_present", "")
                if cid_from_sig not in best_lever_for_category:
                    best_lever_for_category[cid_from_sig] = lv["lever_id"]

    initiatives: List[Dict[str, Any]] = []
    default_cta_rate_by_lever = {
        "supplier_consolidation": 0.06,
        "contract_renegotiation": 0.05,
        "payment_terms": 0.02,
        "maverick_compliance": 0.04,
        "demand_management": 0.05,
        "process_standardization": 0.08,
        "automation": 0.1,
        "insourcing": 0.12,
        "outsourcing": 0.09,
    }

    for row in value_bridge_raw.get("raw_rows", []):
        cid = row["category_id"]
        gap = max(float(row.get("estimated_saving_amount", 0.0)), 0.0)
        if gap <= 0:
            continue

        lever = best_lever_for_category.get(cid) or lever_by_source.get(row.get("source", ""), "contract_renegotiation")
        root = root_by_cat.get(cid, {})
        best_cause = (root.get("root_causes") or [{}])[0]
        if best_cause.get("recommended_lever"):
            lever = best_cause["recommended_lever"]

        lv_meta = lever_meta_by_id.get(lever, {})
        sustainability_score = lv_meta.get("sustainability_score", 0.65)
        bounce_back_risk = lv_meta.get("bounce_back_risk", "medium")
        condition_precedents = lv_meta.get("condition_precedents", [])
        org_change_risk = lv_meta.get("org_change_risk", "low")
        base_exec_raw = float(lv_meta.get("base_execution_probability", 0.70))
        base_execution_probability = base_exec_raw * _OCR_HAIRCUTS.get(org_change_risk, 1.0)

        # TCO adjustment: reduce gap by lifecycle costs when tco_inputs provided for this category
        tco_adjusted = False
        tco_breakdown: Dict[str, float] = {}
        if tco_inputs and cid in tco_inputs:
            tco = tco_inputs[cid]
            impl = float(tco.get("implementation_cost", 0.0))
            support = float(tco.get("annual_support", 0.0))
            migration = float(tco.get("migration_cost", 0.0))
            lifecycle_deduction = impl / 3.0 + support + migration / 3.0
            gap = max(0.0, gap - lifecycle_deduction)
            tco_adjusted = True
            tco_breakdown = {"implementation_cost": impl, "annual_support": support, "migration_cost": migration, "lifecycle_deduction": round(lifecycle_deduction, 2)}

        curve = lv_meta.get("phasing_curve") or phasing_curves.get(lever, [0.25, 0.5, 0.25])

        savings_type = lv_meta.get("savings_type") or savings_type_by_lever.get(lever, "run_rate")

        run_rate_savings = gap * max(curve) if savings_type in ("run_rate", "mixed") else 0.0

        cta_input = cost_to_achieve_inputs.get(cid, {})
        consulting = float(cta_input.get("consulting_fees", 0.0))
        technology = float(cta_input.get("technology_investment", 0.0))
        internal = float(cta_input.get("internal_resource_cost", 0.0))

        def _phase(total: float, key: str) -> Tuple[float, float, float]:
            ph = impl_cost_phasing.get(key, [0.65, 0.25, 0.10])
            return total * ph[0], total * ph[1], total * (ph[2] if len(ph) > 2 else 0.0)

        c_y1, c_y2, c_y3 = _phase(consulting, "consulting_fees")
        t_y1, t_y2, t_y3 = _phase(technology, "technology_investment")
        i_y1, i_y2, i_y3 = _phase(internal, "internal_resource_cost")

        if not (consulting or technology or internal):
            default_rate = float(default_cta_rate_by_lever.get(lever, 0.07))
            cta_total = gap * default_rate
            cta_y1 = cta_total * (1.0 - cta_y2_fraction)
            cta_y2 = cta_total * cta_y2_fraction
            cta_y3 = 0.0
        else:
            cta_y1 = c_y1 + t_y1 + i_y1
            cta_y2 = c_y2 + t_y2 + i_y2
            cta_y3 = c_y3 + t_y3 + i_y3
            cta_total = consulting + technology + internal

        y1 = gap * curve[0]
        y2 = gap * curve[1]
        y3 = gap * curve[2]

        ny1 = y1 - cta_y1
        ny2 = y2 - cta_y2
        ny3 = y3 - cta_y3

        tax_multiplier = 1.0 - tax_rate
        any1 = ny1 * tax_multiplier
        any2 = ny2 * tax_multiplier
        any3 = ny3 * tax_multiplier

        npv_pretax = (
            ny1 / ((1 + discount_rate) ** 1)
            + ny2 / ((1 + discount_rate) ** 2)
            + ny3 / ((1 + discount_rate) ** 3)
        )
        npv_aftertax = (
            any1 / ((1 + discount_rate) ** 1)
            + any2 / ((1 + discount_rate) ** 2)
            + any3 / ((1 + discount_rate) ** 3)
        )

        irr_cashflows = [-cta_y1 * tax_multiplier, any1, any2, any3]
        irr_pct = _compute_irr(irr_cashflows) if cta_y1 > 0 else None

        payback_months = 60
        if ny1 > 0:
            payback_months = max(1, int((cta_y1 / y1) * 12)) if y1 > 0 else 12
        elif (ny1 + ny2) > 0:
            remaining = cta_y1 - ny1
            payback_months = 12 + max(1, int((remaining / ny2) * 12)) if ny2 > 0 else 24
        elif (ny1 + ny2 + ny3) > 0:
            payback_months = 36

        initiative_dict: Dict[str, Any] = {
            "category_id": cid,
            "category_name": row.get("category_name", cid),
            "lever": lever,
            "lever_name": lv_meta.get("lever_name", lever.replace("_", " ").title()),
            "lever_family": lv_meta.get("lever_family", "supply"),
            "savings_type": savings_type,
            "annualized_run_rate_savings": round(run_rate_savings, 2),
            "org_change_risk": org_change_risk,
            "root_cause": best_cause.get("diagnosis", "Benchmark gap above norm"),
            "confidence": best_cause.get("confidence", "medium"),
            "sustainability_score": round(float(sustainability_score), 2),
            "bounce_back_risk": bounce_back_risk,
            "condition_precedents": condition_precedents,
            "assumptions": condition_precedents,
            "base_execution_probability": round(float(base_execution_probability), 2),
            "tco_adjusted": tco_adjusted,
            "gross_savings": {"y1": y1, "y2": y2, "y3": y3, "total_3yr": y1 + y2 + y3},
            "cost_to_achieve": {
                "y1": cta_y1, "y2": cta_y2, "y3": cta_y3,
                "total_3yr": cta_y1 + cta_y2 + cta_y3,
                "phasing_note": (
                    "Front-loaded by cost type"
                    if (consulting or technology or internal)
                    else "Modeled default CTA applied from lever baseline"
                ),
            },
            "net_savings": {
                "y1": ny1, "y2": ny2, "y3": ny3,
                "total_3yr": ny1 + ny2 + ny3,
                "npv_pretax": round(npv_pretax, 2),
                "npv_aftertax": round(npv_aftertax, 2),
                "npv_10pct": round(npv_pretax, 2),
                "effective_tax_rate": tax_rate,
            },
            "payback_months": payback_months,
            "irr_pct": irr_pct,
        }
        if tco_adjusted:
            initiative_dict["tco_breakdown"] = tco_breakdown
        initiatives.append(initiative_dict)

    # Governance Y3 uplift: if cost_governance lever is present, boost Y3 net savings of all others by 6%
    if any(i["lever"] == "cost_governance" for i in initiatives):
        for i in initiatives:
            if i["lever"] != "cost_governance":
                i["net_savings"]["y3"] = round(i["net_savings"]["y3"] * _GOVERNANCE_Y3_UPLIFT, 2)
                i["net_savings"]["total_3yr"] = round(
                    i["net_savings"]["y1"] + i["net_savings"]["y2"] + i["net_savings"]["y3"], 2
                )

    total_run_rate = sum(
        i["annualized_run_rate_savings"] for i in initiatives if i["savings_type"] in ("run_rate", "mixed")
    )
    total_one_time = sum(
        i["gross_savings"]["y1"] for i in initiatives if i["savings_type"] == "one_time"
    )
    total_cost_avoidance = sum(
        i["gross_savings"]["total_3yr"] for i in initiatives if i["savings_type"] == "cost_avoidance"
    )

    return {
        "discount_rate": discount_rate,
        "effective_tax_rate": tax_rate,
        "planning_horizon_years": planning_horizon_years,
        "initiatives": initiatives,
        "eligible_levers": eligible_levers,
        "summary": {
            "total_run_rate_savings": round(total_run_rate, 2),
            "total_one_time_savings": round(total_one_time, 2),
            "total_cost_avoidance": round(total_cost_avoidance, 2),
            "run_rate_initiative_count": sum(1 for i in initiatives if i["savings_type"] in ("run_rate", "mixed")),
            "one_time_initiative_count": sum(1 for i in initiatives if i["savings_type"] == "one_time"),
            "cost_avoidance_initiative_count": sum(1 for i in initiatives if i["savings_type"] == "cost_avoidance"),
            "eligible_lever_count": len(eligible_levers),
            "high_bounce_back_count": sum(1 for lv in eligible_levers if lv["bounce_back_risk"] == "high"),
            "governance_y3_uplift_applied": any(i["lever"] == "cost_governance" for i in initiatives),
        },
    }


# ---------------------------------------------------------------------------
# Value bridge
# ---------------------------------------------------------------------------

def build_raw_rows(
    peer: Dict[str, Any],
    internal: Dict[str, Any],
    heuristic: Dict[str, Any],
) -> List[Dict[str, Any]]:
    params = _get_model_params()
    internal_capture = float(params.get("defaults", {}).get("internal_variance_capture_rate", 0.1))
    """Extract savings rows from benchmarking outputs without building the full matrix."""
    raw_rows: List[Dict[str, Any]] = []
    for row in peer.get("comparisons", []):
        raw_rows.append(
            {
                "category_id": row["category_id"],
                "category_name": row.get("category_name", row["category_id"]),
                "source": "peer",
                "estimated_saving_amount": row.get("estimated_saving_amount", 0.0),
            }
        )
    for row in heuristic.get("heuristic_findings", []):
        raw_rows.append(
            {
                "category_id": row["category_id"],
                "category_name": row.get("category_name", row["category_id"]),
                "source": "heuristic",
                "estimated_saving_amount": row.get("estimated_saving_amount", 0.0),
            }
        )
    for row in internal.get("internal_variance", []):
        raw_rows.append(
            {
                "category_id": row["category_id"],
                "category_name": row.get("category_name", row["category_id"]),
                "source": "internal",
                "estimated_saving_amount": max(row.get("median_spend", 0.0) * internal_capture, 0.0),
            }
        )
    return raw_rows


def value_bridge_calculator(
    peer: Dict[str, Any],
    internal: Dict[str, Any],
    heuristic: Dict[str, Any],
    total_spend: float,
    savings_model: Dict[str, Any] | None = None,
    committed_initiatives: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    vb_cfg = _get_model_params().get("defaults", {}).get("value_bridge", {})
    dedup_mid_factor = float(vb_cfg.get("dedup_mid_factor", 0.75))
    low_factor = float(vb_cfg.get("low_factor", 0.8))
    high_factor = float(vb_cfg.get("high_factor", 1.2))

    if savings_model and savings_model.get("initiatives"):
        committed = committed_initiatives or []
        committed_lookup = {
            (i.get("category_id"), i.get("lever")): float(i.get("committed_savings", 0.0))
            for i in committed
            if i.get("stage") in ("committed", "in_flight", "realized")
        }
        matrix = []
        low = mid = high = 0.0
        confidence_penalty = 0.0
        for item in savings_model.get("initiatives", []):
            cat = item.get("category_id")
            lever = item.get("lever")
            gross = float(item.get("net_savings", {}).get("total_3yr", 0.0))
            already = committed_lookup.get((cat, lever), 0.0)
            deduped_mid = max(0.0, gross - already)
            deduped_low = deduped_mid * low_factor
            deduped_high = deduped_mid * high_factor
            low += deduped_low
            mid += deduped_mid
            high += deduped_high
            matrix.append(
                {
                    "category_id": cat,
                    "category_name": item.get("category_name", cat),
                    "lever": lever,
                    "root_cause": item.get("root_cause", ""),
                    "gross_3yr": item.get("gross_savings", {}).get("total_3yr", 0.0),
                    "cost_to_achieve_3yr": item.get("cost_to_achieve", {}).get("total_3yr", 0.0),
                    "net_npv": item.get("net_savings", {}).get("npv_10pct", 0.0),
                    "payback_months": item.get("payback_months", 0),
                    "confidence": item.get("confidence", "medium"),
                    "deduped_mid_savings": deduped_mid,
                }
            )
            confidence = str(item.get("confidence", "medium")).lower()
            if confidence == "low":
                confidence_penalty += 0.03
            elif confidence == "mid":
                confidence_penalty += 0.01
        confidence_penalty = min(0.2, confidence_penalty)
        confidence_adjustment = max(0.8, 1.0 - confidence_penalty)
        return {
            "value_matrix": sorted(matrix, key=lambda x: x["deduped_mid_savings"], reverse=True),
            "confidence_bands": {
                "low": low * confidence_adjustment,
                "mid": mid * confidence_adjustment,
                "high": high * confidence_adjustment,
            },
            "addressable_pct_of_total_spend": (mid / total_spend) if total_spend else 0.0,
            "confidence_adjustment": {"factor": confidence_adjustment, "penalty": confidence_penalty},
        }

    raw_rows = build_raw_rows(peer, internal, heuristic)
    merged: Dict[str, Dict[str, float]] = defaultdict(lambda: {"peer": 0.0, "internal": 0.0, "heuristic": 0.0})
    for row in raw_rows:
        merged[row["category_id"]][row["source"]] = row["estimated_saving_amount"]

    matrix = []
    low = mid = high = 0.0
    for cat, values in merged.items():
        combined = values["peer"] + values["internal"] + values["heuristic"]
        deduped_mid = combined * dedup_mid_factor
        deduped_low = deduped_mid * low_factor
        deduped_high = deduped_mid * high_factor
        low += deduped_low
        mid += deduped_mid
        high += deduped_high
        matrix.append(
            {
                "category_id": cat,
                "peer_savings": values["peer"],
                "internal_savings": values["internal"],
                "heuristic_savings": values["heuristic"],
                "deduped_mid_savings": deduped_mid,
            }
        )

    return {
        "value_matrix": sorted(matrix, key=lambda x: x["deduped_mid_savings"], reverse=True),
        "confidence_bands": {"low": low, "mid": mid, "high": high},
        "addressable_pct_of_total_spend": (mid / total_spend) if total_spend else 0.0,
        "raw_rows": raw_rows,
    }


def data_validator(value_bridge: Dict[str, Any]) -> Dict[str, Any]:
    conf = value_bridge.get("confidence_bands", {})
    low, mid, high = conf.get("low", 0.0), conf.get("mid", 0.0), conf.get("high", 0.0)
    checks = {
        "bands_monotonic": low <= mid <= high,
        "non_negative": low >= 0 and mid >= 0 and high >= 0,
        "non_empty_matrix": len(value_bridge.get("value_matrix", [])) > 0,
    }
    return {"checks": checks, "passed": all(checks.values())}
