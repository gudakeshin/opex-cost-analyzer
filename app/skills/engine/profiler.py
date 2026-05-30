"""Spend profiler, chart builder, classify_line helpers, document contextualizer,
industry inference, addressability helpers, and lever resolution."""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from app.models import NormalizedSpendLine, is_actual

from ._loaders import (
    _get_classification_rules,
    _get_regulatory_exclusions,
    _get_switching_costs,
    _get_model_params,
    _get_sector_levers,
    _resolve_pack_id,
    _HEADCOUNT_APPLICABLE_CATEGORIES,
    _get_heuristic_ranges,
    _get_per_employee_targets,
)

# ---------------------------------------------------------------------------
# Document industry signals constant
# ---------------------------------------------------------------------------
_DOC_INDUSTRY_SIGNALS: Dict[str, List[str]] = {
    "bfsi_banks": ["npa", "credit rating", "loan book", "casa ratio", "core banking", "nbfc", "rbi circular"],
    "it_ites": ["software license", "cloud infrastructure", "saas", "bpo", "ites", "data centre", "devops"],
    "fmcg_consumer": ["sku", "distributor", "trade promotion", "shelf space", "fmcg", "consumer goods", "retail chain"],
    "pharma_lifesciences": ["clinical trial", "regulatory submission", "api manufacturing", "pharmacovigilance", "drug master file"],
    "energy_utilities": ["power plant", "generation capacity", "transmission", "at&c loss", "renewable energy", "grid"],
    "insurance_general": ["claims ratio", "loss ratio", "underwriting", "reinsurance", "actuarial", "premium income"],
    "retail_organized": ["same store sales", "square footage", "footfall", "inventory turnover", "shrinkage"],
    "telecom_infra": ["spectrum", "rpu", "arpu", "tower", "ran", "5g", "telecom"],
    "manufacturing_diversified": ["plant maintenance", "oee", "downtime", "production capacity", "raw material", "packaging material"],
    "psu_cpse": ["psu", "cpse", "public sector", "gem portal", "dgs&d", "pat cycle"],
    "conglomerate": ["holding company", "subsidiary", "group revenue", "inter-company", "conglomerate"],
    "healthcare_hospitals": ["bed capacity", "nabh", "ot utilization", "inpatient", "outpatient", "clinical staff", "occupancy rate", "nurse", "physician", "pharmacy formulary", "revenue cycle", "denial rate"],
    "hospitality_travel": ["revpar", "adr", "ota commission", "food and beverage", "room nights", "channel manager", "pms", "housekeeping", "occupancy rate", "booking engine"],
    "financial_services_nonbank": ["aum", "fund management", "asset management", "fintech", "mifid", "sebi amc", "nav", "portfolio management", "broker vote", "custody fee", "performance attribution"],
    "gcc_capability_centers": [
        "global capability center", "gcc", "captive center", "shared service center", "ssc",
        "center of excellence", "coe", "offshore delivery", "captive unit", "nasscom gcc",
        "fte cost", "seat cost", "attrition", "bench management", "automation ops",
    ],
}


# ---------------------------------------------------------------------------
# Kraljic quadrant helper
# ---------------------------------------------------------------------------

def _assign_kraljic_quadrant(share_of_total: float, hhi: float) -> str:
    """Classify a spend category into a Kraljic portfolio quadrant.

    Quadrants:
      leverage  — high spend, low supplier concentration → aggressive negotiation
      strategic — high spend, high concentration → partnership management
      bottleneck — low spend, high concentration → risk mitigation
      tail      — low spend, low concentration → automate / catalogue buying
    """
    high_spend = share_of_total > 0.05
    high_concentration = hhi > 0.20
    if high_spend and not high_concentration:
        return "leverage"
    if high_spend and high_concentration:
        return "strategic"
    if not high_spend and high_concentration:
        return "bottleneck"
    return "tail"


# ---------------------------------------------------------------------------
# Addressability helpers
# ---------------------------------------------------------------------------

def _contract_addressability_multiplier(line: NormalizedSpendLine) -> float:
    """Return the addressability multiplier based on contract status and remaining term."""
    exclusions = _get_regulatory_exclusions()
    contract_cfg = exclusions.get("contract_based_exclusions", {})

    status = line.contract_status
    if status is None:
        return 1.0

    if status == "expired":
        return float(contract_cfg.get("expired_contract_addressability_multiplier", 1.0))
    if status == "rolling":
        return float(contract_cfg.get("rolling_contract_addressability_multiplier", 0.70))
    if status == "at_risk":
        return float(contract_cfg.get("at_risk_contract_addressability_multiplier", 0.60))

    if status == "in_contract" and line.contract_expiry_date is not None:
        today = date.today()
        months_remaining = (
            (line.contract_expiry_date.year - today.year) * 12
            + (line.contract_expiry_date.month - today.month)
        )
        if months_remaining > 18:
            return float(contract_cfg.get("in_contract_gt_18m_addressability_multiplier", 0.15))
        elif months_remaining >= 6:
            return float(contract_cfg.get("in_contract_6_to_18m_addressability_multiplier", 0.40))
        else:
            return float(contract_cfg.get("in_contract_lt_6m_addressability_multiplier", 0.80))

    return float(contract_cfg.get("in_contract_gt_18m_addressability_multiplier", 0.15))


def _regulatory_addressability_override(category_id: str, description: str) -> Optional[float]:
    """Return a hard addressability override if this spend is statutory/regulatory."""
    exclusions = _get_regulatory_exclusions()

    for excl in exclusions.get("non_addressable_categories", []):
        if excl.get("category_id") == category_id:
            return float(excl.get("addressability_override", 0.0))

    lower = description.lower()
    for rule in exclusions.get("keyword_based_exclusions", []):
        if any(kw in lower for kw in rule.get("keywords", [])):
            return float(rule.get("addressability_override", 0.0))

    return None


def _switching_cost_offset(category_id: str, addressable_spend: float) -> float:
    """Return the switching cost that should be netted against gross addressable spend."""
    sc = _get_switching_costs()
    rate = float(sc.get("switching_cost_rate_by_category", {}).get(category_id, 0.03))
    return addressable_spend * rate


# ---------------------------------------------------------------------------
# Classify helpers
# ---------------------------------------------------------------------------

def _classify_line(text: str) -> Tuple[str, bool]:
    """Return (cost_behaviour, is_discretionary) from a pre-built lower-case text string."""
    rules = _get_classification_rules()
    cb = rules.get("cost_behaviour", {})
    fixed_kw = cb.get("fixed_keywords", [])
    semi_kw = cb.get("semi_variable_keywords", [])
    disc = rules.get("discretionary", {})
    include_kw = disc.get("include_keywords", [])
    exclude_kw = disc.get("exclude_keywords", [])
    default_non_disc = disc.get("default_non_discretionary_if_contains", [])

    if any(k in text for k in fixed_kw):
        behaviour = "fixed"
    elif any(k in text for k in semi_kw):
        behaviour = "semi_variable"
    else:
        behaviour = "variable"

    if any(k in text for k in include_kw):
        discretionary = True
    elif any(k in text for k in exclude_kw):
        discretionary = False
    else:
        discretionary = not any(k in text for k in default_non_disc)

    return behaviour, discretionary


def classify_cost_behaviour(line: NormalizedSpendLine) -> str:
    text = f"{line.category_name} {line.description}".lower()
    behaviour, _ = _classify_line(text)
    return behaviour


def _classify_spend_quadrant(text: str) -> str:
    """Return Essential / Strategic / Supportive / Discretionary for a pre-lowercased text string.
    Priority: essential > discretionary > strategic > supportive (default)."""
    quadrant_rules = _get_classification_rules().get("spend_quadrant", {})
    if any(k in text for k in quadrant_rules.get("essential", {}).get("keywords", [])):
        return "essential"
    if any(k in text for k in quadrant_rules.get("discretionary", {}).get("keywords", [])):
        return "discretionary"
    if any(k in text for k in quadrant_rules.get("strategic", {}).get("keywords", [])):
        return "strategic"
    return "supportive"


def classify_discretionary(line: NormalizedSpendLine) -> bool:
    text = f"{line.category_name} {line.description}".lower()
    _, discretionary = _classify_line(text)
    return discretionary


# ---------------------------------------------------------------------------
# Industry inference
# ---------------------------------------------------------------------------

def infer_industry_from_spend(lines: List[NormalizedSpendLine], total_spend: float) -> str:
    """Infer sector pack ID from spend patterns when industry is not user-supplied."""
    if not lines or total_spend <= 0:
        return ""
    by_cat: Dict[str, float] = defaultdict(float)
    keyword_hits: Dict[str, int] = defaultdict(int)
    for line in lines:
        by_cat[line.category_id] += line.reporting_amount
        desc = (line.description or "").lower()
        if any(k in desc for k in ("npa", "core banking", "cbs", "casa", "nbfc", "rbi circular")):
            keyword_hits["bfsi_banks"] += 1
        if any(k in desc for k in ("clinical trial", "api batch", "cro", "pharmacovigilance", "dossier")):
            keyword_hits["pharma_lifesciences"] += 1
        if any(k in desc for k in ("claims", "underwriting", "reinsurance", "loss ratio", "irdai")):
            keyword_hits["insurance_general"] += 1
        if any(k in desc for k in ("tower", "bts", "ran", "bss", "oss", "spectrum", "roaming")):
            keyword_hits["telecom_infra"] += 1
        if any(
            k in desc
            for k in (
                "gcc", "captive center", "shared service", "ssc", "center of excellence",
                "coe", "offshore delivery", "global in-house", "captive unit",
            )
        ):
            keyword_hits["gcc_capability_centers"] += 1

    if keyword_hits:
        return max(keyword_hits, key=keyword_hits.__getitem__)

    it_pct = (by_cat.get("IT", 0) + by_cat.get("CONTINGENT", 0) + by_cat.get("OUTSOURCED", 0)) / total_spend
    pm_pct = by_cat.get("PLANT_MAINTENANCE", 0) / total_spend
    rnd_pct = by_cat.get("RND", 0) / total_spend
    log_pct = (by_cat.get("LOGISTICS", 0) + by_cat.get("LOGISTICS_INDIA", 0)) / total_spend
    pkg_pct = by_cat.get("PACKAGING", 0) / total_spend
    pwr_pct = by_cat.get("POWER_ENERGY", 0) / total_spend
    tel_pct = by_cat.get("TELECOM", 0) / total_spend

    hr_pct = by_cat.get("HR", 0) / total_spend
    if it_pct > 0.25 and hr_pct > 0.12:
        return "gcc_capability_centers"
    if it_pct > 0.40:
        return "it_ites"
    if pm_pct > 0.08 and rnd_pct < 0.02:
        return "manufacturing_diversified"
    if pm_pct > 0.03 and rnd_pct > 0.05:
        return "pharma_lifesciences"
    if (log_pct + pkg_pct) > 0.15:
        return "fmcg_consumer"
    if pwr_pct > 0.10:
        return "energy_utilities"
    if tel_pct > 0.05:
        return "telecom_infra"

    return ""


# ---------------------------------------------------------------------------
# Lever resolution helpers
# ---------------------------------------------------------------------------

def _evaluate_lever_signals(
    lever_def: Dict[str, Any],
    categories_present: set,
    cat_spend: Dict[str, float],
    total_spend: float,
    headcount: float,
    annual_revenue: float,
) -> List[str]:
    """Evaluate applicable_if rules for a sector-specific lever."""
    rules = lever_def.get("applicable_if", [])
    if not rules:
        return ["no_restriction"]

    signals = []
    for rule in rules:
        rule_lower = rule.lower()
        if rule_lower.startswith("category:"):
            cat_id = rule.split(":")[1].split()[0].strip()
            if cat_id in categories_present:
                signals.append(f"category:{cat_id}_present")
        elif "headcount >" in rule_lower:
            try:
                threshold = float(rule_lower.split(">")[1].strip())
                if headcount and headcount > threshold:
                    signals.append(f"headcount>{threshold:.0f}")
            except (ValueError, IndexError):
                pass
        elif "annual_revenue >" in rule_lower:
            try:
                threshold = float(rule_lower.split(">")[1].strip().replace("m", "e6").replace("b", "e9"))
                if annual_revenue and annual_revenue > threshold:
                    signals.append(f"revenue>{threshold:.0f}")
            except (ValueError, IndexError):
                pass
        elif "_gt_" in rule_lower and "pct" in rule_lower:
            signals.append(rule)
        elif "keywords detected" in rule_lower or "keywords" in rule_lower:
            signals.append(rule)
        elif "multi_bu_structure" in rule_lower:
            signals.append("multi_bu_inferred")

    return signals


def _build_lever_entry(
    lever_id: str,
    meta: Dict[str, Any],
    sustainability: Dict[str, float],
    phasing: Dict[str, List[float]],
    savings_types: Dict[str, str],
    trigger_signals: List[str],
    eligibility_score: float,
    root_cause_match: bool,
    savings_range_pct: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    sust = meta.get("sustainability_score") or sustainability.get(lever_id, 0.65)
    bounce = meta.get("bounce_back_risk", "medium" if sust < 0.50 else "low")
    conditions = meta.get("condition_precedents", [])
    return {
        "lever_id": lever_id,
        "lever_name": meta.get("lever_name", lever_id.replace("_", " ").title()),
        "lever_family": meta.get("lever_family", "supply"),
        "eligibility_score": round(eligibility_score, 3),
        "root_cause_match": root_cause_match,
        "trigger_signals": trigger_signals,
        "sustainability_score": round(float(sust), 2),
        "bounce_back_risk": bounce,
        "condition_precedents": conditions,
        "phasing_curve": meta.get("phasing_curve") or phasing.get(lever_id, [0.25, 0.50, 0.25]),
        "savings_type": meta.get("savings_type") or savings_types.get(lever_id, "run_rate"),
        "cta_rate": meta.get("cta_rate", 0.07),
        "complexity_tier": meta.get("complexity_tier", "medium"),
        "base_execution_probability": meta.get("base_execution_probability", 0.70),
        "savings_range_pct": savings_range_pct or {},
    }


def resolve_eligible_levers(
    industry: str,
    spend_profile: Dict[str, Any],
    headcount: float,
    annual_revenue: float,
    root_causes: List[Dict[str, Any]],
    sector_weights: Optional[Dict[str, float]] = None,
    engagement_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return ranked list of eligible levers for this company context."""
    params = _get_model_params()
    levers_meta = params.get("levers", {})
    sustainability = params.get("sustainability_score_by_lever", {})
    phasing = params.get("phasing_curves", {})
    savings_types = params.get("savings_type_by_lever", {})

    categories_present = {c["category_id"] for c in spend_profile.get("category_profile", [])}
    cat_spend = {c["category_id"]: c.get("spend", 0.0) for c in spend_profile.get("category_profile", [])}
    total_spend = sum(cat_spend.values()) or 1.0
    root_cause_levers = {rc.get("recommended_lever") for rca in root_causes for rc in rca.get("root_causes", [])}

    if sector_weights and len(sector_weights) > 1:
        total_w = sum(max(0.0, w) for w in sector_weights.values()) or 1.0
        normalised: Dict[str, float] = {pid: max(0.0, w) / total_w for pid, w in sector_weights.items()}
    else:
        primary_pack = _resolve_pack_id(industry)
        normalised = {primary_pack: 1.0} if primary_pack else {}

    eligible: List[Dict[str, Any]] = []
    seen_universal: set = set()

    for pack_id, weight in normalised.items():
        if not pack_id:
            continue
        sector_data = _get_sector_levers(pack_id)

        universal_ids = set(sector_data.get("universal_levers", list(levers_meta.keys())))
        for lever_id in universal_ids:
            if lever_id in seen_universal:
                continue
            seen_universal.add(lever_id)
            meta = levers_meta.get(lever_id, {})
            eligible.append(_build_lever_entry(
                lever_id=lever_id,
                meta=meta,
                sustainability=sustainability,
                phasing=phasing,
                savings_types=savings_types,
                trigger_signals=["universal_lever"],
                eligibility_score=0.70,
                root_cause_match=lever_id in root_cause_levers,
            ))

        for lever_def in sector_data.get("sector_specific_levers", []):
            lever_id = lever_def["lever_id"]
            signals = _evaluate_lever_signals(lever_def, categories_present, cat_spend, total_spend, headcount, annual_revenue)
            if not signals:
                continue
            base_score = min(0.95, 0.70 + 0.05 * len(signals))
            eligible.append(_build_lever_entry(
                lever_id=lever_id,
                meta=lever_def,
                sustainability=sustainability,
                phasing=phasing,
                savings_types=savings_types,
                trigger_signals=signals,
                eligibility_score=base_score * weight,
                root_cause_match=lever_id in root_cause_levers,
                savings_range_pct=lever_def.get("savings_range_pct"),
            ))

    # Kraljic-aware eligibility boost
    _KRALJIC_LEVER_BOOST: Dict[str, List[str]] = {
        "leverage":   ["contract_renegotiation", "supplier_consolidation", "should_cost_modeling"],
        "tail":       ["tail_spend_automation", "maverick_compliance"],
        "bottleneck": ["specification_optimization", "build_vs_buy_optimization"],
        "strategic":  ["insourcing", "outsourcing"],
    }
    category_quadrants: Dict[str, str] = {
        c.get("category_id", ""): c.get("kraljic_quadrant", "")
        for c in spend_profile.get("category_profile", [])
        if "kraljic_quadrant" in c
    }
    boosted_levers: set = set()
    for q, lever_ids in _KRALJIC_LEVER_BOOST.items():
        if any(quad == q for quad in category_quadrants.values()):
            boosted_levers.update(lever_ids)

    for entry in eligible:
        if entry["root_cause_match"]:
            entry["eligibility_score"] = min(1.0, entry["eligibility_score"] + 0.15)
        if entry["lever_id"] in boosted_levers:
            entry["eligibility_score"] = min(1.0, entry["eligibility_score"] + 0.05)

    seen: Dict[str, Dict[str, Any]] = {}
    for entry in eligible:
        lid = entry["lever_id"]
        if lid not in seen or entry["eligibility_score"] > seen[lid]["eligibility_score"]:
            seen[lid] = entry

    if normalised:
        try:
            from app.services.sector_packs import get_pack_override
            for pack_id in normalised:
                override = get_pack_override(pack_id, engagement_id)
                disabled = set(override.get("disabled_levers", []))
                lever_patches = override.get("lever_overrides", {})
                seen = {lid: e for lid, e in seen.items() if lid not in disabled}
                for lid, patch in lever_patches.items():
                    if lid in seen:
                        seen[lid].update(patch)
        except Exception:
            pass

    return sorted(seen.values(), key=lambda x: x["eligibility_score"], reverse=True)


# ---------------------------------------------------------------------------
# Spend profiler
# ---------------------------------------------------------------------------

def spend_profiler(lines: List[NormalizedSpendLine]) -> Dict[str, Any]:
    actual_lines = [x for x in lines if is_actual(x)]
    if not actual_lines:
        actual_lines = lines

    by_category: Dict[str, Dict[str, Any]] = {}
    total = sum(x.reporting_amount for x in actual_lines)
    period_totals: Dict[str, float] = {}
    category_period: Dict[str, Dict[str, float]] = {}
    currency_breakdown: Dict[str, float] = {}
    gl_breakdown: Dict[str, float] = {}
    quadrant_spend: Dict[str, float] = {"essential": 0.0, "strategic": 0.0, "supportive": 0.0, "discretionary": 0.0}
    suppliers_by_cat: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    supplier_terms_by_cat: Dict[str, Dict[str, Dict[str, float]]] = defaultdict(
        lambda: defaultdict(lambda: {"weighted_days": 0.0, "spend_with_terms": 0.0})
    )
    geos_by_cat: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    express_like_spend_by_cat: Dict[str, float] = defaultdict(float)

    for line in actual_lines:
        amt = line.reporting_amount
        text = f"{line.category_name} {line.description}".lower()
        behaviour, discretionary = _classify_line(text)
        addr_cfg = _get_classification_rules().get("cost_behaviour", {}).get("addressability_pct", {})
        base_addressability = float(addr_cfg.get(behaviour, 1.0))

        reg_override = _regulatory_addressability_override(line.category_id, text)
        if reg_override is not None:
            addressability = reg_override
        else:
            contract_mult = _contract_addressability_multiplier(line)
            addressability = base_addressability * contract_mult

        gross_addressable = amt * addressability
        switching_cost = _switching_cost_offset(line.category_id, gross_addressable)
        net_addressable = max(0.0, gross_addressable - switching_cost)

        entry = by_category.setdefault(
            line.category_id,
            {
                "category_id": line.category_id,
                "category_name": line.category_name,
                "spend": 0.0,
                "line_count": 0,
                "fixed_spend": 0.0,
                "variable_spend": 0.0,
                "semi_variable_spend": 0.0,
                "discretionary_spend": 0.0,
                "non_discretionary_spend": 0.0,
                "addressable_spend": 0.0,
            },
        )
        entry["spend"] += amt
        entry["line_count"] += 1
        if behaviour == "fixed":
            entry["fixed_spend"] += amt
        elif behaviour == "semi_variable":
            entry["semi_variable_spend"] += amt
        else:
            entry["variable_spend"] += amt
        if discretionary:
            entry["discretionary_spend"] += amt
        else:
            entry["non_discretionary_spend"] += amt
        entry["addressable_spend"] += net_addressable
        suppliers_by_cat[line.category_id][line.supplier] += amt
        if line.payment_terms_days is not None:
            supplier_terms_by_cat[line.category_id][line.supplier]["weighted_days"] += amt * float(line.payment_terms_days)
            supplier_terms_by_cat[line.category_id][line.supplier]["spend_with_terms"] += amt
        geo = line.geo or "Unknown"
        geos_by_cat[line.category_id][geo] += amt
        desc = (line.description or "").lower()
        if any(k in desc for k in ("express", "overnight", "air freight", "airfreight", "same day", "priority")):
            express_like_spend_by_cat[line.category_id] += amt

        period_key = line.fiscal_period or (str(line.spend_date)[:7] if line.spend_date else None)
        if period_key:
            period_totals[period_key] = period_totals.get(period_key, 0.0) + amt
            cat_periods = category_period.setdefault(line.category_id, {})
            cat_periods[period_key] = cat_periods.get(period_key, 0.0) + amt

        ccy = (line.currency or "USD").upper()
        # Use reporting_amount (not raw line.amount) so currency_breakdown is
        # denominated in the reporting currency and reconciles with total_spend.
        currency_breakdown[ccy] = currency_breakdown.get(ccy, 0.0) + amt

        if line.gl_code:
            gl_breakdown[line.gl_code] = gl_breakdown.get(line.gl_code, 0.0) + amt

        quadrant = _classify_spend_quadrant(text)
        quadrant_spend[quadrant] = quadrant_spend.get(quadrant, 0.0) + amt

    for entry in by_category.values():
        entry["share_of_total"] = (entry["spend"] / total) if total else 0.0
        entry["addressable_pct"] = (entry["addressable_spend"] / entry["spend"]) if entry["spend"] else 0.0
        cid = entry["category_id"]
        supplier_map = suppliers_by_cat.get(cid, {})
        top_suppliers = sorted(supplier_map.items(), key=lambda x: x[1], reverse=True)[:5]
        supplier_rows = []
        for supplier, supplier_spend in top_suppliers:
            terms_blob = supplier_terms_by_cat.get(cid, {}).get(supplier, {})
            spend_with_terms = float(terms_blob.get("spend_with_terms", 0.0) or 0.0)
            avg_terms = (
                round(float(terms_blob.get("weighted_days", 0.0) or 0.0) / spend_with_terms, 1)
                if spend_with_terms > 0
                else None
            )
            supplier_rows.append(
                {
                    "supplier": supplier,
                    "spend": supplier_spend,
                    "share_of_category": (supplier_spend / entry["spend"]) if entry["spend"] else 0.0,
                    "avg_payment_terms_days": avg_terms,
                }
            )
        entry["supplier_count"] = len(supplier_map)
        entry["top_suppliers"] = supplier_rows

        cat_total = entry["spend"]
        if cat_total > 0 and supplier_map:
            hhi = round(sum((s / cat_total) ** 2 for s in supplier_map.values()), 4)
        else:
            hhi = 0.0
        if hhi > 0.25:
            concentration_flag = "high"
        elif hhi > 0.15:
            concentration_flag = "moderate"
        else:
            concentration_flag = "competitive"
        entry["hhi"] = hhi
        entry["concentration_flag"] = concentration_flag

        share = entry.get("share_of_total", 0.0)
        entry["kraljic_quadrant"] = _assign_kraljic_quadrant(share, hhi)

        # Category maturity proxy: high HHI (few suppliers) → low maturity → full addressability
        # Low HHI (many suppliers, competitive) → higher maturity → harder to extract savings
        maturity_proxy = 1.0 if hhi > 0.25 else (0.75 if hhi > 0.15 else 0.50)
        entry["category_maturity_proxy"] = round(maturity_proxy, 2)
        entry["maturity_adjusted_addressable"] = round(entry["addressable_spend"] * maturity_proxy, 2)

        geo_map = geos_by_cat.get(cid, {})
        top_geos = sorted(geo_map.items(), key=lambda x: x[1], reverse=True)[:3]
        entry["top_geos"] = [
            {
                "geo": g,
                "spend": s,
                "share_of_category": (s / entry["spend"]) if entry["spend"] else 0.0,
            }
            for g, s in top_geos
        ]
        express_spend = float(express_like_spend_by_cat.get(cid, 0.0))
        entry["express_like_spend"] = express_spend
        entry["express_like_pct"] = (express_spend / entry["spend"]) if entry["spend"] else 0.0

    distinct_periods = sorted(period_totals.keys())
    trend_analysis: Dict[str, Any] | None = None
    if len(distinct_periods) >= 2:
        category_trends: Dict[str, Any] = {}
        for cat_id, period_map in category_period.items():
            sorted_ps = sorted(period_map.keys())
            pairs = [{"period": p, "spend": period_map[p]} for p in sorted_ps]
            mom_growth: float | None = None
            if len(sorted_ps) >= 2:
                prev = period_map[sorted_ps[-2]]
                curr = period_map[sorted_ps[-1]]
                mom_growth = round((curr - prev) / prev * 100, 1) if prev > 0 else None
            category_trends[cat_id] = {"periods": pairs, "mom_growth_pct": mom_growth}
        trend_analysis = {
            "period_totals": {p: period_totals[p] for p in distinct_periods},
            "distinct_periods": distinct_periods,
            "category_trends": category_trends,
        }

    total_q = sum(quadrant_spend.values()) or 1.0
    quadrant_breakdown = {
        q: {"spend": round(s, 2), "pct": round(s / total_q, 4)}
        for q, s in quadrant_spend.items()
    }

    result: Dict[str, Any] = {
        "total_spend": total,
        "category_profile": sorted(by_category.values(), key=lambda x: x["spend"], reverse=True),
        "multi_currency": len(currency_breakdown) > 1,
        "currency_breakdown": currency_breakdown,
        "quadrant_breakdown": quadrant_breakdown,
    }
    if gl_breakdown:
        result["gl_breakdown"] = dict(sorted(gl_breakdown.items(), key=lambda x: x[1], reverse=True))
    if trend_analysis is not None:
        result["trend_analysis"] = trend_analysis
    return result


# ---------------------------------------------------------------------------
# Chart builder
# ---------------------------------------------------------------------------

def _slim_profile_for_chart_llm(profile: Dict[str, Any]) -> Dict[str, Any]:
    categories = profile.get("category_profile", []) if isinstance(profile, dict) else []
    categories = sorted(categories, key=lambda x: float(x.get("spend", 0.0)), reverse=True)
    total_spend = float(profile.get("total_spend", 0.0) or 0.0)
    top3_spend = sum(float(c.get("spend", 0.0)) for c in categories[:3])
    top3_share = (top3_spend / total_spend) if total_spend > 0 else 0.0
    has_trend = bool(profile.get("trend_analysis", {}).get("distinct_periods", [])) if isinstance(profile, dict) else False
    return {
        "total_spend": total_spend,
        "top3_share": top3_share,
        "has_trend": has_trend,
        "top_categories": [
            {
                "name": c.get("category_name") or c.get("category_id") or "Category",
                "spend": float(c.get("spend", 0.0)),
                "addressable_spend": float(c.get("addressable_spend", 0.0)),
            }
            for c in categories[:5]
        ],
    }


def chart_builder(profile: Dict[str, Any], user_message: str | None = None) -> Dict[str, Any]:
    """Select chart patterns and commentary, driven by LLM when user_message is provided."""
    if user_message:
        try:
            from app.opar.claude_client import select_charts_claude
            llm_result = select_charts_claude(user_message, _slim_profile_for_chart_llm(profile))
            if llm_result and llm_result.get("selected_charts"):
                return llm_result
        except Exception:
            pass

    categories = profile.get("category_profile", []) if isinstance(profile, dict) else []
    categories = sorted(categories, key=lambda x: float(x.get("spend", 0.0)), reverse=True)
    total_spend = float(profile.get("total_spend", 0.0) or 0.0)
    top3_spend = sum(float(c.get("spend", 0.0)) for c in categories[:3])
    top3_share = (top3_spend / total_spend) if total_spend > 0 else 0.0
    has_trend = bool(profile.get("trend_analysis", {}).get("distinct_periods", [])) if isinstance(profile, dict) else False

    selected_charts: List[Dict[str, Any]] = []
    if top3_share >= 0.55:
        selected_charts.append(
            {
                "chart": "pareto_spend",
                "reason": f"Top-3 categories represent {top3_share:.1%} of spend; concentration view is decision-critical.",
            }
        )
    else:
        selected_charts.append(
            {
                "chart": "ranked_bar_spend",
                "reason": "Spend is more distributed; ranked bars best show relative category scale.",
            }
        )

    selected_charts.append(
        {
            "chart": "stacked_addressability",
            "reason": "FP&A needs immediate visibility into addressable vs non-addressable cost pools.",
        }
    )
    if has_trend:
        selected_charts.append(
            {
                "chart": "trend_line_total_spend",
                "reason": "Period trend is available; include trajectory for momentum assessment.",
            }
        )

    commentary_points: List[str] = []
    if categories and total_spend > 0:
        top = categories[0]
        top_name = top.get("category_name") or top.get("category_id") or "Top category"
        top_spend = float(top.get("spend", 0.0))
        commentary_points.append(
            f"Highest spend concentration is in {top_name} at {top_spend/total_spend:.1%} of total spend."
        )
    if top3_share > 0:
        commentary_points.append(
            f"Top-3 categories represent {top3_share:.1%} of spend, indicating where prioritization should start."
        )
    if categories:
        best_addr = max(categories, key=lambda x: float(x.get('addressable_spend', 0.0)))
        best_addr_name = best_addr.get("category_name") or best_addr.get("category_id") or "N/A"
        best_addr_amt = float(best_addr.get("addressable_spend", 0.0))
        commentary_points.append(
            f"Largest modeled addressable pool is {best_addr_name} at ${best_addr_amt:,.0f}."
        )
    if has_trend:
        trend = profile.get("trend_analysis", {})
        periods = trend.get("distinct_periods", [])
        if len(periods) >= 2:
            totals = trend.get("period_totals", {})
            prev = float(totals.get(periods[-2], 0.0))
            curr = float(totals.get(periods[-1], 0.0))
            if prev > 0:
                delta = (curr - prev) / prev * 100.0
                direction = "up" if delta >= 0 else "down"
                commentary_points.append(
                    f"Recent total spend trend is {direction} {abs(delta):.1f}% ({periods[-2]} to {periods[-1]})."
                )
    commentary_points.append("Use this chart view to prioritize categories with both high spend and high addressable potential.")

    return {
        "selected_charts": selected_charts,
        "commentary_points": commentary_points[:6],
    }


# ---------------------------------------------------------------------------
# Document contextualizer
# ---------------------------------------------------------------------------

def document_contextualizer(texts: List[str]) -> Dict[str, Any]:
    joined = "\n".join([t for t in texts if t.strip()])
    lowered = joined.lower()
    constraints = []
    if "contract" in lowered:
        constraints.append("Existing contract commitments detected")
    if "compliance" in lowered or "policy" in lowered:
        constraints.append("Policy/compliance constraints detected")
    if "hiring freeze" in lowered or "headcount freeze" in lowered:
        constraints.append("Headcount constraints may limit optimization options")

    industry_hit_counts: Dict[str, int] = {}
    for pack_id, keywords in _DOC_INDUSTRY_SIGNALS.items():
        hits = sum(1 for kw in keywords if kw in lowered)
        if hits > 0:
            industry_hit_counts[pack_id] = hits
    inferred_industry = ""
    if industry_hit_counts:
        inferred_industry = max(industry_hit_counts, key=lambda k: industry_hit_counts[k])

    return {
        "context_summary": joined[:2500],
        "constraints": constraints,
        "inferred_industry": inferred_industry,
        "industry_signals": industry_hit_counts,
    }
