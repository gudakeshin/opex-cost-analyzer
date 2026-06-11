"""Deterministic per-initiative business-perspective enrichment (Layer A).

Attaches owner / accountability, affected vendors & contract levers, a risk
register, KPIs, change-management notes, a phasing narrative and a baseline
business rationale to every modeled initiative — from data already produced by
``spend-profiler`` and ``savings-modeler`` plus a reference template file. Runs
after both skills so it can join supplier intelligence to each initiative by
category.

This is the offline-safe floor of the hybrid design: the LLM advisory layer
(``app/opar/reflect_advisory.py``) sharpens the narrative when enabled, but every
field here is populated without an LLM call so the business case is never hollow.
"""
from __future__ import annotations

from typing import Any, Dict, List

from ._loaders import _get_business_detail_templates

# Marker so the pass is idempotent — partial profiles and re-runs are safe.
_ENRICHED_MARKER = "business_detail_enriched"


def _family(initiative: Dict[str, Any]) -> str:
    fam = str(initiative.get("lever_family") or "").strip().lower()
    return fam or "_default"


def _pick(mapping: Dict[str, Any], family: str) -> Any:
    """Return the family entry, falling back to ``_default``."""
    if not isinstance(mapping, dict):
        return {}
    return mapping.get(family, mapping.get("_default", {}))


def _build_affected_vendors(profile_entry: Dict[str, Any], max_n: int = 4) -> List[Dict[str, Any]]:
    """Top suppliers in the initiative's category (from spend-profiler)."""
    rows: List[Dict[str, Any]] = []
    for sup in (profile_entry.get("top_suppliers") or [])[:max_n]:
        if not isinstance(sup, dict):
            continue
        name = sup.get("supplier")
        if not name:
            continue
        rows.append(
            {
                "supplier": name,
                "spend": round(float(sup.get("spend", 0.0) or 0.0), 2),
                "share_of_category_pct": round(float(sup.get("share_of_category", 0.0) or 0.0) * 100, 1),
                "avg_payment_terms_days": sup.get("avg_payment_terms_days"),
            }
        )
    return rows


def _build_contract_levers(initiative: Dict[str, Any], family: str, templates: Dict[str, Any]) -> List[str]:
    """Family-level contract actions, prefixed with a renewal-window signal if flagged."""
    base = list(_pick(templates.get("contract_levers_by_family", {}), family) or [])
    for sig in initiative.get("diagnostic_signals") or []:
        text = (sig.get("signal") if isinstance(sig, dict) else str(sig)) or ""
        if any(t in text.lower() for t in ("expir", "renewal", "renew", "window")):
            base.insert(0, f"Act within the open contract window — {text}")
            break
    return base


def _build_risks(
    initiative: Dict[str, Any],
    profile_entry: Dict[str, Any],
    templates: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Structured risk register from the initiative's risk labels + supplier concentration."""
    lib = templates.get("risk_library", {}) if isinstance(templates, dict) else {}
    picked: List[Dict[str, Any]] = []

    bb = str(initiative.get("bounce_back_risk") or "").lower()
    if bb == "high":
        picked.append(lib.get("bounce_back_high"))
    elif bb == "medium":
        picked.append(lib.get("bounce_back_medium"))

    oc = str(initiative.get("org_change_risk") or "").lower()
    if oc == "high":
        picked.append(lib.get("org_change_high"))
    elif oc == "medium":
        picked.append(lib.get("org_change_medium"))

    if str(initiative.get("confidence") or "").lower() == "low":
        picked.append(lib.get("low_confidence"))

    if str((profile_entry or {}).get("concentration_flag") or "").lower() == "high":
        picked.append(lib.get("supplier_concentration"))

    risks = [dict(r) for r in picked if isinstance(r, dict)]
    if not risks and isinstance(lib.get("_default"), dict):
        risks.append(dict(lib["_default"]))
    return risks


def _build_phasing_narrative(initiative: Dict[str, Any]) -> str:
    gross = initiative.get("gross_savings") or {}
    total = float(gross.get("total_3yr") or 0.0)
    horizon = str(initiative.get("horizon") or "structural")
    payback = initiative.get("payback_months")
    pb = f" Payback ~{payback} months." if payback else ""
    if total <= 0:
        return f"{horizon.title()} initiative phased across three years.{pb}"
    p1 = round(float(gross.get("y1") or 0.0) / total * 100)
    p2 = round(float(gross.get("y2") or 0.0) / total * 100)
    p3 = round(float(gross.get("y3") or 0.0) / total * 100)
    return (
        f"{horizon.title()} initiative phased {p1}% / {p2}% / {p3}% of gross savings "
        f"across Years 1–3.{pb}"
    )


def _build_business_rationale(initiative: Dict[str, Any]) -> str:
    """Deterministic root-cause → action → outcome sentence (LLM may override later)."""
    lever_name = initiative.get("lever_name") or initiative.get("lever") or "This initiative"
    category = initiative.get("category_name") or initiative.get("category_id") or "the category"
    root = initiative.get("root_cause") or "a benchmark gap"
    root_text = root.lower() if isinstance(root, str) else str(root)
    run_rate = float(initiative.get("annualized_run_rate_savings") or 0.0)
    bps = (initiative.get("ebitda_impact") or {}).get("ebitda_bps")
    impact = ""
    if run_rate > 0:
        impact = f", unlocking ~{run_rate:,.0f} in annualized run-rate savings"
        if bps:
            impact += f" (~{bps} bps of EBITDA)"
    return f"{lever_name} addresses {root_text} in {category}{impact}."


def enrich_initiatives_business_detail(skill_outputs: Dict[str, Any]) -> None:
    """Mutate ``skill_outputs['savings-modeler']['initiatives']`` in place.

    Idempotent and additive: returns silently when savings-modeler produced no
    initiatives, and skips initiatives already enriched. When spend-profiler is
    absent the supplier-derived fields degrade to empty lists but every other
    field is still populated.
    """
    if not isinstance(skill_outputs, dict):
        return
    savings = skill_outputs.get("savings-modeler")
    if not isinstance(savings, dict):
        return
    initiatives = savings.get("initiatives")
    if not isinstance(initiatives, list) or not initiatives:
        return

    templates = _get_business_detail_templates()
    profile = skill_outputs.get("spend-profiler") or {}
    cat_index = {
        str(c.get("category_id")): c
        for c in profile.get("category_profile", [])
        if isinstance(c, dict) and c.get("category_id")
    }

    for init in initiatives:
        if not isinstance(init, dict) or init.get(_ENRICHED_MARKER):
            continue
        family = _family(init)
        profile_entry = cat_index.get(str(init.get("category_id")), {})

        owner = _pick(templates.get("owner_by_family", {}), family) or {}
        init["owner"] = {
            "owner_role": owner.get("owner_role"),
            "business_sponsor": owner.get("business_sponsor"),
            "raci": owner.get("raci", {}),
        }
        # Flattened for the pipeline record / frontend table.
        init["owner_role"] = owner.get("owner_role")
        init["business_sponsor"] = owner.get("business_sponsor")

        init["affected_vendors"] = _build_affected_vendors(profile_entry)
        init["contract_levers"] = _build_contract_levers(init, family, templates)
        init["kpis"] = [dict(k) for k in (_pick(templates.get("kpis_by_family", {}), family) or [])]
        init["change_management"] = dict(_pick(templates.get("change_management_by_family", {}), family) or {})
        init["risks"] = _build_risks(init, profile_entry, templates)
        init["phasing_narrative"] = _build_phasing_narrative(init)
        init["business_rationale"] = _build_business_rationale(init)
        init[_ENRICHED_MARKER] = True
