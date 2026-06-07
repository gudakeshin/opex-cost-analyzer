"""Indian compliance skills: indian_tax_optimizer, gstr_reconciler,
msme_compliance_checker, brsr_cobenefit_calculator."""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional, cast

from app.models import NormalizedSpendLine

from ._loaders import _get_gst_rules


# ---------------------------------------------------------------------------
# Indian Tax Optimizer
# ---------------------------------------------------------------------------

def indian_tax_optimizer(
    lines: List[NormalizedSpendLine],
    effective_tax_rate: float = 0.0,
    blended_gst_rate: float = 0.18,
    itc_leakage_rate: float = 0.20,
) -> Dict[str, Any]:
    """Identify GST ITC leakage, RCM exposure, inverted-duty refund opportunities,
    and TDS gaps from Indian enterprise spend lines."""
    rules = _get_gst_rules()
    itc_eligible_kw = [k.lower() for k in rules.get("itc_eligible_keywords", [])]
    itc_ineligible_kw = [k.lower() for k in rules.get("itc_ineligible_keywords", [])]
    rcm_kw = [k.lower() for k in rules.get("rcm_keywords", [])]

    total_lines = len(lines)
    if total_lines == 0:
        return {
            "tax_optimization_available": False,
            "note": "No spend lines provided.",
        }

    tagged_lines = sum(1 for x in lines if x.gst_treatment)
    tag_coverage = tagged_lines / total_lines

    itc_eligible_spend = 0.0
    itc_ineligible_spend = 0.0
    rcm_spend = 0.0
    itc_by_category: Dict[str, float] = defaultdict(float)
    rcm_by_category: Dict[str, float] = defaultdict(float)

    for line in lines:
        if line.amount_type != "actual":
            continue
        amt = line.reporting_amount
        text = f"{line.description} {line.supplier} {line.category_name}".lower()
        treatment = line.gst_treatment

        if treatment == "itc_eligible" or (
            not treatment and any(k in text for k in itc_eligible_kw)
            and not any(k in text for k in itc_ineligible_kw)
        ):
            itc_eligible_spend += amt
            itc_by_category[line.category_id] += amt
        elif treatment == "ineligible" or any(k in text for k in itc_ineligible_kw):
            itc_ineligible_spend += amt
        elif treatment == "rcm" or any(k in text for k in rcm_kw):
            rcm_spend += amt
            rcm_by_category[line.category_id] += amt

    estimated_itc_pool = itc_eligible_spend * blended_gst_rate
    estimated_itc_leakage = estimated_itc_pool * itc_leakage_rate
    estimated_rcm_liability = rcm_spend * blended_gst_rate

    top_itc_categories = sorted(
        [{"category_id": k, "spend": round(v, 2)} for k, v in itc_by_category.items()],
        key=lambda x: cast(float, x["spend"]),
        reverse=True,
    )[:5]
    rcm_categories = sorted(
        [{"category_id": k, "spend": round(v, 2)} for k, v in rcm_by_category.items()],
        key=lambda x: cast(float, x["spend"]),
        reverse=True,
    )[:5]

    section_115BAA_rate = rules.get("section_115BAA", {}).get("effective_rate_pct", 25.17)
    on_concessional = abs(effective_tax_rate * 100 - section_115BAA_rate) < 1.0

    if tag_coverage >= 0.80:
        confidence = "high"
    elif tag_coverage >= 0.40:
        confidence = "medium"
    else:
        confidence = "low"

    total_opportunity = estimated_itc_leakage + estimated_rcm_liability

    return {
        "tax_optimization_available": True,
        "itc_leakage": {
            "total_spend_itc_eligible": round(itc_eligible_spend, 2),
            "estimated_itc_pool": round(estimated_itc_pool, 2),
            "estimated_itc_leakage": round(estimated_itc_leakage, 2),
            "leakage_rate_pct": round(itc_leakage_rate * 100, 1),
            "blended_gst_rate_pct": round(blended_gst_rate * 100, 1),
            "top_categories": top_itc_categories,
        },
        "rcm_exposure": {
            "total_rcm_spend": round(rcm_spend, 2),
            "estimated_rcm_gst_liability": round(estimated_rcm_liability, 2),
            "categories": rcm_categories,
        },
        "inverted_duty": {
            "applicable": False,
            "note": "Requires sector classification and GST return data; flag for manual review if client is in textiles, fertilizers, footwear, mobile, or solar.",
        },
        "section_115BAA": {
            "applicable": on_concessional,
            "effective_rate_pct": section_115BAA_rate,
            "npv_adjustment_note": (
                "Client appears to be on 115BAA concessional regime (22% + surcharge). "
                "After-tax NPV of initiatives adjusted to 25.17% effective rate."
            ) if on_concessional else "Not on 115BAA; standard corporate tax rate assumed.",
        },
        "tds_gaps": {
            "note": "TDS gap analysis requires 26AS data; not computed from spend lines alone.",
            "categories_with_potential_gap": [],
            "estimated_tds_at_risk": 0.0,
        },
        "total_tax_opportunity": round(total_opportunity, 2),
        "tag_coverage_pct": round(tag_coverage * 100, 1),
        "confidence": confidence,
        "assumptions": [
            f"Blended GST rate assumed at {round(blended_gst_rate * 100)}% across eligible spend.",
            f"ITC leakage rate assumed at {round(itc_leakage_rate * 100)}% of eligible pool (industry default; refine with client GSTR-2A/2B data).",
            "RCM self-assessment assumed nil unless tagged; verify with client GST returns.",
        ],
        "data_limitations": [
            "gst_treatment field coverage: {:.0f}% of spend lines tagged".format(tag_coverage * 100),
            "Inverted duty and TDS gap analysis require additional data (GST returns, 26AS).",
        ],
    }


# ---------------------------------------------------------------------------
# GSTR Reconciler
# ---------------------------------------------------------------------------

def gstr_reconciler(
    lines: List[NormalizedSpendLine],
    gstr_2a: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Reconcile AP spend lines against GSTR-2A / GSTR-2B data."""
    gstr_rows = gstr_2a or []

    if not gstr_rows:
        gst_ingested = [ln for ln in lines if getattr(ln, "gst_treatment", None)]
        if not gst_ingested:
            return {
                "gstr_available": False,
                "reason": (
                    "No GSTR-2A data provided. Upload a GSTR-2A/2B CSV via the GST portal "
                    "connector, or pass gstr_2a rows directly to this skill."
                ),
                "total_ap_lines": len(lines),
                "matched_count": 0,
                "unmatched_count": 0,
                "amount_mismatch_count": 0,
                "itc_at_risk": 0.0,
                "recovery_opportunity": 0.0,
                "coverage_pct": 0.0,
                "line_matches": [],
            }
        gstr_rows = [
            {
                "gstin": ln.vendor_gstin or "",
                "invoice_no": ln.source_record_id or str(ln.row_id),
                "amount": ln.reporting_amount,
            }
            for ln in gst_ingested
        ]

    ap_by_gstin: Dict[str, List[NormalizedSpendLine]] = defaultdict(list)
    for line in lines:
        if line.vendor_gstin:
            ap_by_gstin[line.vendor_gstin.upper().strip()].append(line)

    matched_count = 0
    unmatched_count = 0
    amount_mismatch_count = 0
    itc_at_risk = 0.0
    line_matches: List[Dict[str, Any]] = []

    for gstr_row in gstr_rows:
        gstin = str(gstr_row.get("gstin") or "").upper().strip()
        gstr_amount = float(gstr_row.get("amount") or 0.0)
        invoice_ref = str(gstr_row.get("invoice_no") or gstr_row.get("source_record_id") or "")

        ap_lines = ap_by_gstin.get(gstin, [])
        if not ap_lines:
            itc_on_line = round(gstr_amount * 0.18, 2)
            itc_at_risk += itc_on_line
            unmatched_count += 1
            line_matches.append({
                "invoice_ref": invoice_ref,
                "supplier_gstin": gstin,
                "ap_amount": 0.0,
                "gstr_amount": gstr_amount,
                "status": "unmatched_in_ap",
                "itc_at_risk": itc_on_line,
            })
            continue

        best: Optional[NormalizedSpendLine] = None
        for ap_line in ap_lines:
            if gstr_amount > 0 and abs(ap_line.reporting_amount - gstr_amount) / gstr_amount < 0.01:
                best = ap_line
                break

        if best:
            matched_count += 1
            line_matches.append({
                "invoice_ref": invoice_ref,
                "supplier_gstin": gstin,
                "ap_amount": round(best.reporting_amount, 2),
                "gstr_amount": gstr_amount,
                "status": "matched",
                "itc_at_risk": 0.0,
            })
        else:
            ap_amount = ap_lines[0].reporting_amount
            delta = abs(ap_amount - gstr_amount)
            itc_on_delta = round(delta * 0.18, 2)
            itc_at_risk += itc_on_delta
            amount_mismatch_count += 1
            line_matches.append({
                "invoice_ref": invoice_ref,
                "supplier_gstin": gstin,
                "ap_amount": round(ap_amount, 2),
                "gstr_amount": gstr_amount,
                "status": "amount_mismatch",
                "itc_at_risk": itc_on_delta,
            })

    coverage_pct = round(matched_count / max(len(gstr_rows), 1) * 100, 1)
    recovery_opportunity = round(itc_at_risk * 0.60, 2)

    return {
        "gstr_available": True,
        "reason": None,
        "total_ap_lines": len(lines),
        "matched_count": matched_count,
        "unmatched_count": unmatched_count,
        "amount_mismatch_count": amount_mismatch_count,
        "itc_at_risk": round(itc_at_risk, 2),
        "recovery_opportunity": recovery_opportunity,
        "coverage_pct": coverage_pct,
        "line_matches": line_matches[:100],
    }


# ---------------------------------------------------------------------------
# MSME Compliance Checker
# ---------------------------------------------------------------------------

def msme_compliance_checker(lines: List[NormalizedSpendLine]) -> Dict[str, Any]:
    """Flag MSME vendors with payment terms exceeding 45 days (MSMED Act Section 15)."""
    MSME_LIMIT_DAYS = 45
    PENALTY_RATE_ANNUAL = 0.12

    msme_lines = [ln for ln in lines if ln.vendor_msme_flag is True]
    if not msme_lines:
        has_any_flag = any(ln.vendor_msme_flag is not None for ln in lines)
        return {
            "msme_data_available": False,
            "reason": (
                "No MSME vendors found. Enrich vendor master with MSME classification "
                "(vendor_msme_flag=True) to enable compliance scoring."
                if not has_any_flag else
                "No lines flagged as MSME (vendor_msme_flag=True). "
                "All flagged vendors are non-MSME."
            ),
            "total_msme_spend": 0.0,
            "at_risk_spend": 0.0,
            "compliant_spend": 0.0,
            "compliance_score": 1.0,
            "penalty_exposure": 0.0,
            "at_risk_count": 0,
            "at_risk_payments": [],
        }

    supplier_spend: Dict[str, float] = defaultdict(float)
    supplier_info: Dict[str, Dict[str, Any]] = {}

    for line in msme_lines:
        key = line.vendor_gstin or line.supplier or "UNKNOWN"
        supplier_spend[key] += line.reporting_amount
        if key not in supplier_info:
            supplier_info[key] = {
                "supplier": line.supplier or "Unknown",
                "vendor_gstin": line.vendor_gstin,
                "msme_flag": line.vendor_msme_flag,
                "payment_terms_days": line.payment_terms_days,
            }

    at_risk: List[Dict[str, Any]] = []
    at_risk_spend = 0.0
    compliant_spend = 0.0
    penalty_exposure = 0.0

    for key, annual_spend in supplier_spend.items():
        info = supplier_info[key]
        terms = info.get("payment_terms_days")

        if terms is not None and terms > MSME_LIMIT_DAYS:
            days_over = terms - MSME_LIMIT_DAYS
            penalty = annual_spend * (PENALTY_RATE_ANNUAL / 365) * days_over
            at_risk_spend += annual_spend
            penalty_exposure += penalty
            at_risk.append({
                "supplier": info["supplier"],
                "vendor_gstin": info["vendor_gstin"],
                "msme_flag": info["msme_flag"],
                "annual_spend": round(annual_spend, 2),
                "payment_terms_days": terms,
                "days_over_limit": days_over,
                "penalty_interest_exposure": round(penalty, 2),
                "alert": (
                    f"Payment terms ({terms} days) exceed MSME statutory limit "
                    f"of {MSME_LIMIT_DAYS} days — Section 15 MSMED Act"
                ),
            })
        else:
            compliant_spend += annual_spend

    total_msme_spend = sum(supplier_spend.values())
    compliance_score = round(compliant_spend / max(total_msme_spend, 1), 4)
    at_risk.sort(key=lambda r: r["penalty_interest_exposure"], reverse=True)

    return {
        "msme_data_available": True,
        "reason": None,
        "total_msme_spend": round(total_msme_spend, 2),
        "at_risk_spend": round(at_risk_spend, 2),
        "compliant_spend": round(compliant_spend, 2),
        "compliance_score": compliance_score,
        "penalty_exposure": round(penalty_exposure, 2),
        "at_risk_count": len(at_risk),
        "at_risk_payments": at_risk,
    }


# ---------------------------------------------------------------------------
# BRSR Co-benefit Calculator
# ---------------------------------------------------------------------------

def brsr_cobenefit_calculator(
    lines: List[NormalizedSpendLine],
    initiatives: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    """Map OpEx initiatives to BRSR principles and estimate environmental co-benefits."""
    initiatives = initiatives or []

    _SCOPE2_FACTOR = 0.45
    _SCOPE3_FACTOR = 0.28
    _WATER_FACTOR = 18.0
    _WASTE_FACTOR = 0.12

    _CATEGORY_MAP: Dict[str, Dict[str, Any]] = {
        "energy":         {"principle": "P6", "scope2": True},
        "utilities":      {"principle": "P6", "scope2": True},
        "logistics":      {"principle": "P6", "scope3": True},
        "travel":         {"principle": "P6", "scope3": True},
        "facilities":     {"principle": "P6", "water": True},
        "manufacturing":  {"principle": "P6", "waste": True},
        "packaging":      {"principle": "P6", "waste": True},
        "professional_services": {"principle": "P1"},
        "hr":             {"principle": "P8"},
        "it_software":    {"principle": "P1"},
    }

    cobenefit_items: List[Dict[str, Any]] = []
    total_scope2 = 0.0
    total_scope3 = 0.0
    total_water = 0.0
    total_waste = 0.0

    for init in initiatives:
        cat_id = str(init.get("category_id") or "").lower()
        mid_cr = float(init.get("p50") or init.get("mid_case_savings") or init.get("deduped_mid_savings") or 0.0) / 1e7
        mapping = _CATEGORY_MAP.get(cat_id, {"principle": "P1"})

        scope2 = round(mid_cr * _SCOPE2_FACTOR, 2) if mapping.get("scope2") else 0.0
        scope3 = round(mid_cr * _SCOPE3_FACTOR, 2) if mapping.get("scope3") else 0.0
        water = round(mid_cr * _WATER_FACTOR, 1) if mapping.get("water") else 0.0
        waste = round(mid_cr * _WASTE_FACTOR, 2) if mapping.get("waste") else 0.0

        total_scope2 += scope2
        total_scope3 += scope3
        total_water += water
        total_waste += waste

        cobenefit_items.append({
            "initiative_id": str(init.get("category_id") or init.get("initiative_id") or "unknown"),
            "category_name": init.get("category_name") or init.get("category_id") or "Unknown",
            "brsr_principle": mapping.get("principle", "P1"),
            "delta_scope2_tco2e": scope2,
            "delta_scope3_tco2e": scope3,
            "delta_water_kl": water,
            "delta_waste_tonnes": waste,
            "cobenefit_note": (
                f"Maps to BRSR {mapping.get('principle', 'P1')}; "
                f"primary co-benefit: {'Scope-2 reduction' if scope2 else 'Scope-3 reduction' if scope3 else 'Water' if water else 'Waste' if waste else 'Governance'}."
            ),
        })

    return {
        "cobenefit_items": cobenefit_items,
        "portfolio_totals": {
            "delta_scope2_tco2e": round(total_scope2, 2),
            "delta_scope3_tco2e": round(total_scope3, 2),
            "delta_water_kl": round(total_water, 1),
            "delta_waste_tonnes": round(total_waste, 2),
        },
        "brsr_principles_addressed": sorted(
            {item["brsr_principle"] for item in cobenefit_items}
        ),
        "emission_factors": {
            "scope2_tco2e_per_cr": _SCOPE2_FACTOR,
            "scope3_tco2e_per_cr": _SCOPE3_FACTOR,
            "water_kl_per_cr": _WATER_FACTOR,
            "waste_tonnes_per_cr": _WASTE_FACTOR,
            "note": "Default generic factors; replace with client-specific BRSR actuals.",
        },
        "summary": (
            f"{len(cobenefit_items)} initiative(s) mapped to BRSR; "
            f"ΔScope-2: {total_scope2:.1f} tCO₂e; "
            f"ΔScope-3: {total_scope3:.1f} tCO₂e; "
            f"Δwater: {total_water:.0f} kL; "
            f"Δwaste: {total_waste:.1f} t."
        ),
    }
