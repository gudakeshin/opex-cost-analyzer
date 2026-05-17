"""Strategic skills: scenario_modeler, value_to_shareholder_bridge, peer_disclosure_miner,
contract_lifecycle_manager, conflict_detector, cost_to_serve_analyzer, zbb_modeler."""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import date
from typing import Any, Dict, List, Optional

from app.models import NormalizedSpendLine


# ---------------------------------------------------------------------------
# Peer cost patterns constant
# ---------------------------------------------------------------------------
_PEER_COST_PATTERNS = [
    (r"cost[- ]to[- ]income\s+ratio[^\d]*([\d.]+)\s*%", "cost_to_income_pct"),
    (r"operating\s+expenses?\s+(?:at|of|were|was)\s+(?:₹|rs\.?|inr)?\s*([\d,]+(?:\.\d+)?)\s*(cr|crore|lakh|mn|million)?", "opex_abs"),
    (r"([\d.]+)\s*%\s+(?:of|to)\s+(?:total\s+)?(?:opex|operating\s+exp)", "opex_pct_mention"),
    (r"technology\s+(?:spend|investment|cost)[^\d]*([\d.]+)\s*%", "tech_pct_of_opex"),
    (r"employ(?:ee|ment)\s+cost[^\d]*([\d.]+)\s*%", "employee_cost_pct"),
    (r"energy\s+(?:cost|consumption)[^\d]*([\d.]+)\s*%", "energy_pct"),
    (r"logistics\s+(?:cost|expense)[^\d]*([\d.]+)\s*%", "logistics_pct"),
]


# ---------------------------------------------------------------------------
# Scenario Modeler
# ---------------------------------------------------------------------------

def scenario_modeler(
    lines: List[NormalizedSpendLine],
    initiatives: List[Dict[str, Any]] | None = None,
    *,
    base_savings: float = 0.0,
    wacc: float = 0.12,
    effective_tax_rate: float = 0.2517,
) -> Dict[str, Any]:
    """Build a 6-scenario macro surface for initiative portfolio sensitivity."""
    initiatives = initiatives or []
    total_spend = sum(float(getattr(l, "amount", 0) or 0) for l in lines)

    if base_savings <= 0:
        base_savings = sum(
            float(i.get("p50") or i.get("mid_case_savings") or i.get("deduped_mid_savings") or 0.0)
            for i in initiatives
        )
    if base_savings <= 0:
        base_savings = total_spend * 0.08

    p10_total = sum(float(i.get("p10") or base_savings * 0.70) for i in initiatives) or base_savings * 0.70
    p90_total = sum(float(i.get("p90") or base_savings * 1.35) for i in initiatives) or base_savings * 1.35

    def _npv(savings_annual: float, years: int = 3) -> float:
        after_tax = savings_annual * (1 - effective_tax_rate)
        return round(sum(after_tax / ((1 + wacc) ** y) for y in range(1, years + 1)), 2)

    scenarios = [
        {
            "scenario_id": "base",
            "label": "Base case",
            "description": "P50 savings at planned execution rate",
            "savings_impact": round(base_savings, 2),
            "npv": _npv(base_savings),
            "driver": None,
        },
        {
            "scenario_id": "fx_stress",
            "label": "FX stress (INR -10%)",
            "description": "INR depreciates 10% — import-heavy spend increases; export-denominated savings partially offset",
            "savings_impact": round(base_savings * 0.88, 2),
            "npv": _npv(base_savings * 0.88),
            "driver": "fx",
        },
        {
            "scenario_id": "wage_inflation",
            "label": "Wage inflation (+8% YoY)",
            "description": "People-intensive initiatives lose ~12% of projected savings due to wage drift",
            "savings_impact": round(base_savings * 0.88, 2),
            "npv": _npv(base_savings * 0.88),
            "driver": "wage",
        },
        {
            "scenario_id": "commodity_spike",
            "label": "Commodity spike (+15%)",
            "description": "Raw material and energy cost increases erode 15% of addressable savings",
            "savings_impact": round(base_savings * 0.85, 2),
            "npv": _npv(base_savings * 0.85),
            "driver": "commodity",
        },
        {
            "scenario_id": "execution_slip",
            "label": "Execution slip (30% slippage)",
            "description": "30% of initiatives delayed or partially captured",
            "savings_impact": round(base_savings * 0.70, 2),
            "npv": _npv(base_savings * 0.70),
            "driver": "execution",
        },
        {
            "scenario_id": "upside",
            "label": "Upside (P90)",
            "description": "All initiatives achieve P90 savings; no execution slip",
            "savings_impact": round(p90_total, 2),
            "npv": _npv(p90_total),
            "driver": "upside",
        },
    ]

    base_npv = _npv(base_savings)
    downside_floor = min(s["savings_impact"] for s in scenarios)
    return {
        "scenarios": scenarios,
        "base_savings": round(base_savings, 2),
        "base_npv": base_npv,
        "p10_savings": round(p10_total, 2),
        "p90_savings": round(p90_total, 2),
        "downside_floor": round(downside_floor, 2),
        "downside_floor_pct_of_base": round(downside_floor / base_savings * 100, 1) if base_savings else 0.0,
        "macro_sensitivity_rating": (
            "high" if (base_savings - downside_floor) / max(1, base_savings) > 0.25
            else "medium" if (base_savings - downside_floor) / max(1, base_savings) > 0.12
            else "low"
        ),
        "summary": (
            f"6-scenario range: {downside_floor:,.0f} (execution slip) to {p90_total:,.0f} (P90 upside); "
            f"base case {base_savings:,.0f}."
        ),
    }


# ---------------------------------------------------------------------------
# Value to Shareholder Bridge
# ---------------------------------------------------------------------------

def value_to_shareholder_bridge(
    lines: List[NormalizedSpendLine],
    initiatives: List[Dict[str, Any]] | None = None,
    *,
    annual_revenue: float = 0.0,
    ebitda_margin_pct: float = 15.0,
    wacc: float = 0.12,
    shares_outstanding: float = 100_000_000.0,
    share_price: float = 100.0,
) -> Dict[str, Any]:
    """Translate the OpEx initiative portfolio into shareholder-value metrics."""
    initiatives = initiatives or []
    total_mid_savings = sum(
        float(i.get("mid_case_savings") or i.get("deduped_mid_savings") or 0.0)
        for i in initiatives
    )
    total_spend = sum(float(getattr(l, "amount", 0) or 0) for l in lines)
    effective_tax = 0.2517

    delta_ebitda = total_mid_savings
    revenue = annual_revenue if annual_revenue > 0 else max(total_spend / 0.35, 1.0)
    delta_ebitda_bps = round((delta_ebitda / revenue) * 10000, 1) if revenue > 0 else 0.0

    current_ebitda = revenue * (ebitda_margin_pct / 100)
    capital_employed = revenue * 1.2
    current_roce = (current_ebitda / capital_employed) * 100 if capital_employed > 0 else 0.0
    new_ebitda = current_ebitda + delta_ebitda
    new_roce = (new_ebitda / capital_employed) * 100 if capital_employed > 0 else 0.0
    delta_roce_pp = round(new_roce - current_roce, 2)

    delta_pat = delta_ebitda * (1 - effective_tax)
    delta_eps = round(delta_pat / max(1, shares_outstanding), 4) if shares_outstanding > 0 else 0.0

    delta_fcf = round(delta_pat * 0.90, 2)

    pe_ratio = (share_price / (delta_pat / max(1, shares_outstanding))) if delta_pat > 0 and shares_outstanding > 0 else 15.0
    pe_ratio = max(8.0, min(35.0, pe_ratio))
    delta_equity_value = round(delta_pat * pe_ratio, 2)

    per_initiative: List[Dict[str, Any]] = []
    for init in initiatives:
        mid = float(init.get("mid_case_savings") or init.get("deduped_mid_savings") or 0.0)
        if mid <= 0:
            continue
        share = mid / total_mid_savings if total_mid_savings > 0 else 0.0
        per_initiative.append({
            "initiative_id": str(init.get("category_id") or init.get("initiative_id") or "unknown"),
            "category_name": init.get("category_name") or init.get("category_id") or "Unknown",
            "mid_savings": round(mid, 2),
            "delta_ebitda_bps": round((mid / revenue) * 10000, 1) if revenue > 0 else 0.0,
            "delta_eps_contribution": round(mid * (1 - effective_tax) / max(1, shares_outstanding), 6),
            "value_share_pct": round(share * 100, 1),
        })

    return {
        "total_mid_savings": round(total_mid_savings, 2),
        "delta_ebitda": round(delta_ebitda, 2),
        "delta_ebitda_bps": delta_ebitda_bps,
        "delta_roce_pp": delta_roce_pp,
        "delta_eps": delta_eps,
        "delta_fcf": delta_fcf,
        "delta_equity_value": delta_equity_value,
        "assumptions": {
            "effective_tax_rate": effective_tax,
            "wacc": wacc,
            "pe_ratio_used": round(pe_ratio, 1),
            "capital_employed_proxy": round(capital_employed, 2),
            "revenue_used": round(revenue, 2),
        },
        "per_initiative": per_initiative,
        "summary": (
            f"Portfolio mid-case savings: {total_mid_savings:,.0f}; "
            f"ΔEBITDA +{delta_ebitda_bps:.0f} bps; "
            f"ΔROCE +{delta_roce_pp:.2f} pp; "
            f"ΔEPS +{delta_eps:.4f}; "
            f"ΔEquity value {delta_equity_value:,.0f}."
        ),
    }


# ---------------------------------------------------------------------------
# Peer Disclosure Miner
# ---------------------------------------------------------------------------

def peer_disclosure_miner(
    lines: List[NormalizedSpendLine],
    peer_set: List[Dict] | None = None,
    *,
    target_categories: List[str] | None = None,
    mode: str = "M1",
) -> Dict[str, Any]:
    """Mine peer cost commentary from available filing text."""
    peers = peer_set or []
    target_cats = target_categories or []

    scanned_texts = [
        " ".join(filter(None, [
            str(getattr(ln, "supplier", None) or getattr(ln, "vendor_name", None) or ""),
            str(ln.description or ""),
            str(getattr(ln, "category_name", "") or ""),
        ]))
        for ln in (lines or [])
    ]

    extractions: List[Dict] = []
    for text in scanned_texts[:500]:
        for pattern, field_name in _PEER_COST_PATTERNS:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                extractions.append({
                    "field": field_name,
                    "raw_match": m.group(0)[:120],
                    "value_str": m.group(1),
                    "confidence": 0.35,
                })

    peer_disclosures = []
    for peer in peers:
        peer_disclosures.append({
            "peer_name": peer.get("name", "Unknown"),
            "ticker": peer.get("ticker"),
            "filing_type": "annual_report",
            "fiscal_year": "FY25",
            "cost_category": target_cats[0] if target_cats else "general_opex",
            "disclosed_value_cr": None,
            "disclosed_pct_of_opex": None,
            "commentary": None,
            "source_page": None,
            "confidence": 0.20 if mode == "M1" else 0.75,
        })

    llm_degraded = mode == "M1"
    m1_note = (
        "M1 mode active: keyword-regex extraction only (~25% recall). "
        "Upgrade to M2 for full LLM-powered peer filing extraction."
        if llm_degraded else None
    )

    return {
        "peer_disclosures": peer_disclosures,
        "m1_regex_extractions": extractions if llm_degraded else [],
        "portfolio_coverage": round(len(extractions) / max(len(scanned_texts), 1), 3),
        "llm_degraded": llm_degraded,
        "m1_recall_note": m1_note,
        "extraction_mode": mode,
        "summary": (
            f"Peer disclosure mining completed in {mode} mode. "
            f"{len(peer_disclosures)} peers profiled; "
            f"{len(extractions)} regex signal(s) found from spend line text."
            + (f" {m1_note}" if m1_note else "")
        ),
    }


# ---------------------------------------------------------------------------
# Contract Lifecycle Manager
# ---------------------------------------------------------------------------

def contract_lifecycle_manager(lines: List[NormalizedSpendLine]) -> Dict[str, Any]:
    """Identify contract renewal risks, auto-renewal exposures, and spend blocked by
    in-contract lock-ins."""
    today = date.today()

    supplier_spend: Dict[str, float] = defaultdict(float)
    supplier_info: Dict[str, Dict[str, Any]] = {}

    for line in lines:
        key = line.vendor_gstin or line.supplier or "UNKNOWN"
        supplier_spend[key] += line.reporting_amount
        if key not in supplier_info:
            supplier_info[key] = {
                "supplier": line.supplier or "Unknown",
                "vendor_gstin": line.vendor_gstin,
                "contract_expiry_date": line.contract_expiry_date,
                "contract_status": line.contract_status,
            }

    renewal_alerts: List[Dict[str, Any]] = []
    savings_blocked = 0.0

    for key, annual_spend in supplier_spend.items():
        info = supplier_info[key]
        expiry = info.get("contract_expiry_date")
        status = str(info.get("contract_status") or "")

        days_to_expiry: Optional[int] = None
        alert_type: Optional[str] = None

        if expiry:
            days_to_expiry = (expiry - today).days
            if days_to_expiry < 0:
                alert_type = "expired"
            elif days_to_expiry <= 30:
                alert_type = "renewal_due"
            elif days_to_expiry <= 90:
                alert_type = "at_risk"

        if status == "rolling" and not alert_type:
            alert_type = "auto_renewal_risk"
        elif status in ("expired", "at_risk") and not alert_type:
            alert_type = status

        if status == "in_contract" and expiry and (expiry - today).days > 90:
            savings_blocked += annual_spend

        if alert_type:
            supplier_lower = (info["supplier"] or "").lower()
            is_tech = any(kw in supplier_lower for kw in ("tech", " it ", "software", "saas", "cloud"))
            penalty_pct = 0.20 if is_tech and annual_spend >= 1_000_000 else 0.10 if annual_spend >= 500_000 else 0.05
            renewal_alerts.append({
                "supplier": info["supplier"],
                "vendor_gstin": info["vendor_gstin"],
                "contract_expiry_date": str(expiry) if expiry else None,
                "contract_status": status or None,
                "annual_spend": round(annual_spend, 2),
                "estimated_exit_penalty": round(annual_spend * penalty_pct, 2),
                "days_to_expiry": days_to_expiry,
                "alert_type": alert_type,
            })

    renewal_alerts.sort(key=lambda r: r["annual_spend"], reverse=True)

    exit_penalty_exposure = sum(r["estimated_exit_penalty"] for r in renewal_alerts)
    at_risk_spend = sum(
        r["annual_spend"] for r in renewal_alerts if r["alert_type"] in ("at_risk", "expired")
    )
    expired_spend = sum(r["annual_spend"] for r in renewal_alerts if r["alert_type"] == "expired")

    return {
        "contracts_analyzed": len(supplier_info),
        "renewal_alerts": renewal_alerts,
        "exit_penalty_exposure": round(exit_penalty_exposure, 2),
        "savings_blocked_by_contract": round(savings_blocked, 2),
        "at_risk_spend": round(at_risk_spend, 2),
        "expired_contracts_spend": round(expired_spend, 2),
    }


# ---------------------------------------------------------------------------
# Conflict Detector
# ---------------------------------------------------------------------------

def conflict_detector(
    lines: List[NormalizedSpendLine],
    benchmarks: Optional[List[Dict[str, Any]]] = None,
    entity_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Run all 7 conflict detectors via ConflictResolver and return the summary dict."""
    from app.services.conflict_resolver import ConflictResolver

    resolver = ConflictResolver()
    conflicts = resolver.run_all(lines, benchmarks=benchmarks, entity_ids=entity_ids)
    raw = resolver.summary(conflicts)
    raw["conflict_count"] = raw.pop("total", 0)
    return raw


# ---------------------------------------------------------------------------
# Cost-to-Serve Analyzer
# ---------------------------------------------------------------------------

def cost_to_serve_analyzer(
    lines: List[NormalizedSpendLine],
    segment_revenue: Optional[Dict[str, float]] = None,
    annual_revenue: float = 0.0,
    headcount: float = 0.0,
) -> Dict[str, Any]:
    """Map OpEx to customer/product/geography segments to surface per-unit cost drivers."""
    if not lines:
        return {
            "cost_to_serve_available": False,
            "reason": "No spend lines provided.",
            "segments": [],
            "cost_per_employee": None,
            "top_cost_drivers": [],
            "unprofitable_segments": [],
            "total_opex_allocated": 0.0,
            "total_opex_unallocated": 0.0,
        }

    total_opex = sum(l.reporting_amount for l in lines)

    cost_per_employee: Optional[Dict[str, float]] = None
    if headcount and headcount > 0:
        by_cat: Dict[str, float] = defaultdict(float)
        for l in lines:
            by_cat[l.category_id] += l.reporting_amount
        cost_per_employee = {
            "total": round(total_opex / headcount, 2),
            "by_category": {cat: round(spend / headcount, 2) for cat, spend in sorted(by_cat.items(), key=lambda x: -x[1])[:10]},
        }

    cat_spend: Dict[str, float] = defaultdict(float)
    cat_names: Dict[str, str] = {}
    for l in lines:
        cat_spend[l.category_id] += l.reporting_amount
        cat_names[l.category_id] = l.category_name or l.category_id

    top_drivers = sorted(
        [{"category_id": cid, "category_name": cat_names.get(cid, cid), "spend": round(amt, 2),
          "pct_of_opex": round(amt / max(total_opex, 1) * 100, 2)}
         for cid, amt in cat_spend.items()],
        key=lambda x: -x["spend"],
    )[:10]

    if not segment_revenue:
        return {
            "cost_to_serve_available": True,
            "segment_revenue_provided": False,
            "reason": "No segment revenue data — showing entity-level cost drivers only.",
            "segments": [],
            "cost_per_employee": cost_per_employee,
            "top_cost_drivers": top_drivers,
            "unprofitable_segments": [],
            "total_opex_allocated": 0.0,
            "total_opex_unallocated": round(total_opex, 2),
        }

    total_seg_rev = sum(segment_revenue.values()) or 1.0

    fixed_pool: List[NormalizedSpendLine] = []
    allocable: List[NormalizedSpendLine] = []
    for l in lines:
        if (l.spend_type or "").lower() in ("lease", "statutory"):
            fixed_pool.append(l)
        else:
            allocable.append(l)

    total_allocable = sum(l.reporting_amount for l in allocable)
    total_fixed = sum(l.reporting_amount for l in fixed_pool)

    seg_direct: Dict[str, float] = {seg: 0.0 for seg in segment_revenue}
    unattributed: List[NormalizedSpendLine] = []
    for l in allocable:
        text = ((l.description or "") + " " + (l.supplier or "")).lower()
        matched = False
        for seg in segment_revenue:
            if seg.lower() in text:
                seg_direct[seg] += l.reporting_amount
                matched = True
                break
        if not matched:
            unattributed.append(l)

    total_indirect = sum(l.reporting_amount for l in unattributed)

    seg_indirect: Dict[str, float] = {}
    for seg, rev in segment_revenue.items():
        rev_share = rev / total_seg_rev
        seg_indirect[seg] = total_indirect * rev_share

    segments = []
    total_allocated = 0.0
    for seg, seg_rev in segment_revenue.items():
        seg_cost = seg_direct.get(seg, 0.0) + seg_indirect.get(seg, 0.0)
        total_allocated += seg_cost
        cost_pct = round(seg_cost / max(seg_rev, 1) * 100, 2) if seg_rev else None
        segments.append({
            "segment": seg,
            "revenue": round(seg_rev, 2),
            "total_cost": round(seg_cost, 2),
            "direct_cost": round(seg_direct.get(seg, 0.0), 2),
            "indirect_cost_allocated": round(seg_indirect.get(seg, 0.0), 2),
            "cost_pct_of_revenue": cost_pct,
            "is_unprofitable": cost_pct is not None and cost_pct > 100,
        })

    segments.sort(key=lambda x: -(x.get("cost_pct_of_revenue") or 0))
    unprofitable = [s["segment"] for s in segments if s.get("is_unprofitable")]

    return {
        "cost_to_serve_available": True,
        "segment_revenue_provided": True,
        "segments": segments,
        "cost_per_employee": cost_per_employee,
        "top_cost_drivers": top_drivers,
        "unprofitable_segments": unprofitable,
        "total_opex_allocated": round(total_allocated, 2),
        "total_opex_unallocated": round(total_fixed, 2),
        "fixed_cost_pool": round(total_fixed, 2),
        "direct_attribution_pct": round((total_allocable - total_indirect) / max(total_opex, 1) * 100, 2),
    }


# ---------------------------------------------------------------------------
# ZBB Modeler
# ---------------------------------------------------------------------------

def zbb_modeler(
    lines: List[NormalizedSpendLine],
    drivers: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Zero-based budgeting: compare actual spend against driver-based should-cost."""
    drivers = drivers or {}
    headcount = float(drivers.get("headcount") or 0)
    revenue = float(drivers.get("revenue") or 0)

    _PER_HC: Dict[str, float] = {
        "it": 150_000,
        "hr": 25_000,
        "facilities": 80_000,
        "travel": 30_000,
        "training": 15_000,
    }

    _PCT_REV: Dict[str, float] = {
        "it": 0.045,
        "hr": 0.08,
        "hr_payroll": 0.25,
        "facilities": 0.03,
        "marketing": 0.05,
        "travel": 0.010,
        "professional_services": 0.025,
        "legal": 0.008,
        "finance": 0.015,
        "logistics": 0.06,
        "r&d": 0.04,
    }

    actual_by_cat: Dict[str, float] = defaultdict(float)
    cat_names: Dict[str, str] = {}

    for line in lines:
        if line.amount_type not in (None, "actual"):
            continue
        cat_id = (line.category_id or "uncategorized").lower()
        actual_by_cat[cat_id] += line.reporting_amount
        cat_names[cat_id] = line.category_name or line.category_id or cat_id

    if not actual_by_cat:
        return {
            "zbb_available": False,
            "reason": "No actual spend lines found. ZBB modeling requires actual spend data.",
            "total_actual_spend": 0.0,
            "total_should_cost": 0.0,
            "total_gap": 0.0,
            "realization_rate": 0.0,
            "category_gaps": [],
            "top_redesign_opportunities": [],
        }

    category_gaps: List[Dict[str, Any]] = []
    total_should_cost = 0.0

    for cat_id, actual_spend in actual_by_cat.items():
        should_cost: Optional[float] = None
        driver_used: Optional[str] = None
        driver_value: Optional[float] = None
        driver_unit: Optional[str] = None

        if headcount > 0:
            for key, rate in _PER_HC.items():
                if key in cat_id:
                    should_cost = rate * headcount
                    driver_used = "headcount"
                    driver_value = headcount
                    driver_unit = "employees"
                    break

        if should_cost is None and revenue > 0:
            for key, pct in _PCT_REV.items():
                if key in cat_id:
                    should_cost = revenue * pct
                    driver_used = "revenue_pct"
                    driver_value = revenue
                    driver_unit = "INR_revenue"
                    break

        if should_cost is None:
            should_cost = actual_spend * 0.85
            driver_used = "heuristic_15pct"

        gap = actual_spend - should_cost
        gap_pct = round(gap / max(actual_spend, 1) * 100, 1) if actual_spend > 0 else None
        total_should_cost += should_cost

        category_gaps.append({
            "category_id": cat_id,
            "category_name": cat_names.get(cat_id, cat_id),
            "actual_spend": round(actual_spend, 2),
            "should_cost": round(should_cost, 2),
            "gap": round(gap, 2),
            "gap_pct": gap_pct,
            "driver": driver_used,
            "driver_value": driver_value,
            "driver_unit": driver_unit,
        })

    category_gaps.sort(key=lambda r: r["gap"], reverse=True)
    total_actual = sum(actual_by_cat.values())
    total_gap = total_actual - total_should_cost
    realization_rate = round(total_should_cost / max(total_actual, 1), 4)

    top_opportunities = [
        f"{g['category_name']}: ₹{g['gap']:,.0f} gap ({g['gap_pct']}% above should-cost)"
        for g in category_gaps
        if (g.get("gap_pct") or 0) > 15
    ][:5]

    return {
        "zbb_available": True,
        "reason": None,
        "total_actual_spend": round(total_actual, 2),
        "total_should_cost": round(total_should_cost, 2),
        "total_gap": round(total_gap, 2),
        "realization_rate": realization_rate,
        "category_gaps": category_gaps,
        "top_redesign_opportunities": top_opportunities,
    }
