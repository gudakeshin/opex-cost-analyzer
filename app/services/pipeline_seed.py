"""Seed pipeline initiatives from analysis / business-case output."""
from __future__ import annotations

from typing import Any, Dict

from app.services.business_case import build_business_case
from app.services.pipeline import _positive_savings, create_initiative, list_initiatives


def _user_id_from_manifest(manifest: Dict[str, Any] | None) -> str:
    if not manifest:
        return "default"
    return (manifest.get("company_name") or "default").lower().replace(" ", "_").replace(".", "_")


def _resolve_engagement_id(session_id: str, analysis: Dict[str, Any]) -> str | None:
    eid = (analysis.get("engagement_id") or "").strip()
    if eid:
        return eid
    try:
        from app.memory import MemoryStore

        manifest = MemoryStore().get("session", session_id) or {}
        return (manifest.get("engagement_id") or "").strip() or None
    except Exception:
        return None


def _row_savings_fields(row: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize savings fields from business-case or value_matrix rows."""
    deduped = row.get("deduped_mid_savings")
    p50 = row.get("p50_savings")
    if p50 is None and deduped is not None:
        try:
            p50 = float(deduped)
        except (TypeError, ValueError):
            p50 = None
    gross_y1 = row.get("gross_savings_y1")
    if gross_y1 is None and p50 is not None:
        gross_y1 = p50
    net_npv = row.get("net_npv")
    return {
        "gross_savings_y1": gross_y1 if gross_y1 is not None else 0.0,
        "gross_savings_y2": row.get("gross_savings_y2", 0.0),
        "gross_savings_y3": row.get("gross_savings_y3", 0.0),
        "net_npv": net_npv if net_npv is not None else 0.0,
        "p50_savings": p50,
        "p10_savings": row.get("p10_savings"),
        "p90_savings": row.get("p90_savings"),
    }


def seed_initiatives_from_analysis(
    analysis: Dict[str, Any],
    session_id: str,
    *,
    user_id: str | None = None,
    template: str = "detailed_proposal",
    advisory: Any | None = None,
) -> int:
    """Create pipeline initiatives from business-case rows when not already present.

    ``advisory`` lets callers pass an already-computed ``AdvisorySections`` so the
    business case is not regenerated via a fresh LLM call (the chat path reuses
    the advisory built for the turn). When omitted, ``build_business_case`` runs
    its own LLM advisory synthesis as before.

    Returns the number of newly created initiatives.
    """
    bc = build_business_case(analysis, template=template, advisory=advisory)
    uid = user_id or _user_id_from_manifest(analysis)
    engagement_id = _resolve_engagement_id(session_id, analysis)
    existing = list_initiatives(session_id=session_id)
    existing_keys = {(i.get("category"), i.get("lever")) for i in existing}
    created = 0

    sections = bc.get("sections", {})
    initiative_details = sections.get("initiative_details")
    savings_opportunity = sections.get("savings_opportunity", [])
    if initiative_details:
        source_rows = initiative_details
    else:
        source_rows = savings_opportunity

    for row in source_rows:
        if not isinstance(row, dict):
            continue
        category = row.get("category_name") or row.get("category_id")
        lever = row.get("lever") or "optimization"
        if not category:
            continue
        savings = _row_savings_fields(row)
        candidate = {**savings, "category": category, "lever": lever}
        if not _positive_savings(candidate):
            continue
        key = (category, lever)
        if key in existing_keys:
            continue
        create_initiative({
            "analysis_id": session_id,
            "session_id": session_id,
            "engagement_id": engagement_id,
            "user_id": uid,
            "category": category,
            "lever": lever,
            "root_cause": row.get("root_cause"),
            "gross_savings_y1": savings["gross_savings_y1"],
            "gross_savings_y2": savings["gross_savings_y2"],
            "gross_savings_y3": savings["gross_savings_y3"],
            "cost_to_achieve": row.get("cost_to_achieve_3yr", 0.0),
            "net_npv": savings["net_npv"],
            "p10_savings": savings["p10_savings"],
            "p90_savings": savings["p90_savings"],
            "savings_type": row.get("savings_type", "run_rate"),
            "annualized_run_rate_savings": row.get("annualized_run_rate_savings", 0.0),
            "stage": "identified",
            "business_rationale": row.get("business_rationale"),
            "affected_vendors": row.get("affected_vendors", []),
            "contract_levers": row.get("contract_levers", []),
            "owner_role": row.get("owner_role"),
            "business_sponsor": row.get("business_sponsor"),
            "risks": row.get("risks", []),
            "kpis": row.get("kpis", []),
            "change_management": row.get("change_management", {}),
            "execution_playbook": row.get("execution_playbook", []),
            "phasing_narrative": row.get("phasing_narrative"),
            "evidence": row.get("evidence", []),
            "p50_savings": savings["p50_savings"],
            "ebitda_bps": row.get("ebitda_bps"),
            "payback_months": row.get("payback_months"),
            "irr_pct": row.get("irr_pct"),
        })
        existing_keys.add(key)
        created += 1
    return created
