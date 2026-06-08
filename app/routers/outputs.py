from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Form, HTTPException
from fastapi.responses import FileResponse

from app.config import OUTPUT_DIR
from app.routers._shared import _memory, read_manifest, validate_session_id
from app.services.board_deck import build_board_deck, export_board_deck_pptx
from app.services.business_case import build_business_case, export_docx, export_pdf_like_text
from app.services.cfo_brief import build_cfo_brief, export_cfo_brief_docx
from app.services.compliance import append_audit_event
from app.services.dashboard import build_dashboard_html
from app.services.mor_pack import build_mor_pack, export_mor_docx
from app.services.pipeline import create_initiative, list_initiatives, pipeline_summary
from app.services.sensitivity import compute_sensitivity

router = APIRouter()


@router.post("/api/business-case/{session_id}")
@router.post("/api/v1/business-case/{session_id}")
def create_business_case(session_id: str, template: str = Form("detailed_proposal")) -> Dict[str, Any]:
    validate_session_id(session_id)
    analysis = _memory.get("session", session_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="No analysis for session")
    bc = build_business_case(analysis, template=template)
    docx_name = f"{session_id}_business_case.docx"
    pdf_name = f"{session_id}_business_case_report.txt"
    docx_path = export_docx(bc, docx_name)
    pdf_like_path = export_pdf_like_text(bc, pdf_name)
    manifest = read_manifest(session_id)
    user_id = (manifest.get("company_name") or "default").lower().replace(" ", "_").replace(".", "_")
    existing = list_initiatives(session_id=session_id)
    existing_keys = {(i.get("category"), i.get("lever")) for i in existing}
    created_initiatives = 0
    # Persist from the enriched per-initiative detail (carries business
    # perspective + financials + LLM sharpening); fall back to the thin
    # value-matrix when no modeled initiatives exist (raw-rows path).
    sections = bc.get("sections", {})
    source_rows = sections.get("initiative_details") or sections.get("savings_opportunity", [])
    for row in source_rows:
        if not isinstance(row, dict):
            continue
        category = row.get("category_name") or row.get("category_id")
        lever = row.get("lever") or "optimization"
        if not category:
            continue
        key = (category, lever)
        if key in existing_keys:
            continue
        create_initiative({
            "analysis_id": session_id,
            "session_id": session_id,
            "user_id": user_id,
            "category": category,
            "lever": lever,
            "root_cause": row.get("root_cause"),
            "gross_savings_y1": row.get("gross_savings_y1", 0.0),
            "gross_savings_y2": row.get("gross_savings_y2", 0.0),
            "gross_savings_y3": row.get("gross_savings_y3", 0.0),
            "cost_to_achieve": row.get("cost_to_achieve_3yr", 0.0),
            "net_npv": row.get("net_npv", 0.0),
            "savings_type": row.get("savings_type", "run_rate"),
            "annualized_run_rate_savings": row.get("annualized_run_rate_savings", 0.0),
            "stage": "identified",
            # Business-perspective detail (Layer A/B).
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
            "p50_savings": row.get("p50_savings"),
            "ebitda_bps": row.get("ebitda_bps"),
            "payback_months": row.get("payback_months"),
            "irr_pct": row.get("irr_pct"),
        })
        existing_keys.add(key)
        created_initiatives += 1
    append_audit_event(f"business_case_generated session_id={session_id}")
    return {
        "business_case": bc,
        "pipeline": {"initiatives_created": created_initiatives},
        "exports": {
            "docx": f"/api/exports/{docx_path.name}",
            "pdf_report_text": f"/api/exports/{pdf_like_path.name}",
        },
    }


@router.post("/api/dashboard/{session_id}")
@router.post("/api/v1/dashboard/{session_id}")
def create_dashboard(session_id: str) -> Dict[str, str]:
    validate_session_id(session_id)
    analysis = _memory.get("session", session_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="No analysis for session")
    path = build_dashboard_html(analysis, filename=f"{session_id}_dashboard.html")
    append_audit_event(f"dashboard_generated session_id={session_id}")
    return {"dashboard_url": f"/api/exports/{path.name}"}


def _engagement_context(session_id: str, analysis: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve company / engagement-week / pack from analysis state + manifest."""
    manifest = read_manifest(session_id)
    return {
        "company_name": analysis.get("company_name") or manifest.get("company_name") or "Client",
        "engagement_week": int(manifest.get("engagement_week") or 1),
        "pack_id": manifest.get("pack_id"),
    }


@router.post("/api/board-deck/{session_id}")
@router.post("/api/v1/board-deck/{session_id}")
def create_board_deck(session_id: str) -> Dict[str, Any]:
    validate_session_id(session_id)
    analysis = _memory.get("session", session_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="No analysis for session")
    ctx = _engagement_context(session_id, analysis)
    deck = build_board_deck(
        analysis,
        company_name=ctx["company_name"],
        engagement_week=ctx["engagement_week"],
        pack_id=ctx["pack_id"],
    )
    path = export_board_deck_pptx(deck, f"{session_id}_board_deck.pptx")
    append_audit_event(f"board_deck_generated session_id={session_id}")
    return {"board_deck": deck, "export_url": f"/api/exports/{path.name}", "filename": path.name}


@router.post("/api/cfo-brief/{session_id}")
@router.post("/api/v1/cfo-brief/{session_id}")
def create_cfo_brief(session_id: str) -> Dict[str, Any]:
    validate_session_id(session_id)
    analysis = _memory.get("session", session_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="No analysis for session")
    ctx = _engagement_context(session_id, analysis)
    brief = build_cfo_brief(
        analysis,
        engagement_week=ctx["engagement_week"],
        pack_id=ctx["pack_id"],
        company_name=ctx["company_name"],
    )
    path = export_cfo_brief_docx(brief, f"{session_id}_cfo_brief.docx")
    append_audit_event(f"cfo_brief_generated session_id={session_id}")
    return {"cfo_brief": brief, "export_url": f"/api/exports/{path.name}", "filename": path.name}


@router.post("/api/mor-pack/{session_id}")
@router.post("/api/v1/mor-pack/{session_id}")
def create_mor_pack(session_id: str, user_id: str | None = None) -> Dict[str, Any]:
    validate_session_id(session_id)
    analysis = _memory.get("session", session_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="No analysis for session")
    ctx = _engagement_context(session_id, analysis)
    bva = analysis.get("skill_outputs", {}).get("bva-analyzer", {}) or {}
    summary = pipeline_summary(user_id=user_id)
    mor = build_mor_pack(
        summary,
        bva,
        company_name=ctx["company_name"],
        engagement_week=ctx["engagement_week"],
    )
    path = export_mor_docx(mor, f"{session_id}_mor_pack.docx")
    append_audit_event(f"mor_pack_generated session_id={session_id}")
    return {"mor_pack": mor, "export_url": f"/api/exports/{path.name}", "filename": path.name}


@router.get("/api/sensitivity/{session_id}")
@router.get("/api/v1/sensitivity/{session_id}")
def get_sensitivity(
    session_id: str,
    discount_rate: float = 0.10,
    effective_tax_rate: float = 0.0,
    execution_rate_pct: float | None = None,
    headcount_growth_pct: float = 0.0,
    revenue_growth_pct: float = 0.0,
) -> Dict[str, Any]:
    validate_session_id(session_id)
    analysis = _memory.get("session", session_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="No analysis for session")
    bridge = analysis.get("skill_outputs", {}).get("value-bridge-calculator", {})
    savings_model = analysis.get("skill_outputs", {}).get("savings-modeler", {})
    drivers: Dict[str, float] = {}
    if execution_rate_pct is not None:
        drivers["execution_rate_pct"] = execution_rate_pct
    if headcount_growth_pct:
        drivers["headcount_growth_pct"] = headcount_growth_pct
    if revenue_growth_pct:
        drivers["revenue_growth_pct"] = revenue_growth_pct
    return compute_sensitivity(
        bridge,
        savings_model=savings_model,
        discount_rate=discount_rate,
        effective_tax_rate=effective_tax_rate,
        drivers=drivers or None,
    )


@router.get("/api/v1/trends/{session_id}")
def get_trends(session_id: str) -> Dict[str, Any]:
    validate_session_id(session_id)
    analysis = _memory.get("session", session_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="No analysis for session")
    temporal = analysis.get("skill_outputs", {}).get("temporal-analyzer")
    if temporal is None:
        raise HTTPException(status_code=404, detail="Temporal analysis not available — run analysis first")
    return temporal


@router.get("/api/v1/bva/{session_id}")
def get_bva(session_id: str) -> Dict[str, Any]:
    validate_session_id(session_id)
    analysis = _memory.get("session", session_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="No analysis for session")
    bva = analysis.get("skill_outputs", {}).get("bva-analyzer")
    if bva is None:
        raise HTTPException(status_code=404, detail="BvA analysis not available — run analysis first")
    return bva


@router.get("/api/v1/payment-terms/{session_id}")
def get_payment_terms(session_id: str) -> Dict[str, Any]:
    validate_session_id(session_id)
    analysis = _memory.get("session", session_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="No analysis for session")
    pt = analysis.get("skill_outputs", {}).get("payment-terms-optimizer")
    if pt is None:
        raise HTTPException(status_code=404, detail="Payment terms analysis not available — run analysis first")
    return pt


@router.get("/api/exports/{filename}")
@router.get("/api/v1/exports/{filename}")
def get_export(filename: str) -> FileResponse:
    resolved = (OUTPUT_DIR / filename).resolve()
    if not str(resolved).startswith(str(OUTPUT_DIR.resolve())):
        raise HTTPException(status_code=400, detail="Invalid filename")
    if not resolved.exists():
        raise HTTPException(status_code=404, detail="Export not found")
    media_type = None
    if resolved.suffix.lower() in {".html", ".htm"} or resolved.name.endswith("_html"):
        media_type = "text/html; charset=utf-8"
    return FileResponse(resolved, media_type=media_type)
