from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Form, HTTPException, Query
from fastapi.responses import FileResponse

from app.config import OUTPUT_DIR
from app.routers._shared import _memory, read_manifest, validate_session_id
from app.services.board_deck import build_board_deck, export_board_deck_pptx
from app.services.business_case import build_business_case, export_docx, export_pdf_like_text
from app.services.cfo_brief import build_cfo_brief, export_cfo_brief_docx
from app.services.compliance import append_audit_event
from app.services.dashboard import build_dashboard_html
from app.services.evidence_appendix import build_evidence_appendix, export_evidence_appendix_docx
from app.services.mor_pack import build_mor_pack, export_mor_docx
from app.services.pipeline import list_initiatives, pipeline_summary
from app.services.pipeline_seed import seed_initiatives_from_analysis
from app.services.pmo_export import build_pmo_data, export_pmo_xlsx
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
    created_initiatives = seed_initiatives_from_analysis(
        analysis, session_id, user_id=user_id, template=template,
    )
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


@router.post("/api/pmo-export/{session_id}")
@router.post("/api/v1/pmo-export/{session_id}")
def create_pmo_export(session_id: str) -> Dict[str, Any]:
    """Export the current initiative portfolio as an Excel PMO toolkit."""
    validate_session_id(session_id)
    analysis = _memory.get("session", session_id)
    manifest = read_manifest(session_id)
    initiatives = list_initiatives(session_id=session_id)
    if not initiatives and analysis:
        seed_initiatives_from_analysis(analysis, session_id)
        initiatives = list_initiatives(session_id=session_id)
    if not initiatives:
        raise HTTPException(status_code=404, detail="No initiatives to export — run analysis first")

    summary = pipeline_summary()
    pmo_rows = []
    for init in initiatives:
        p50 = float(init.get("p50_savings") or init.get("gross_savings_y1") or 0.0)
        pmo_rows.append({
            "initiative_id": init.get("initiative_id"),
            "category_name": init.get("category"),
            "category_id": init.get("category"),
            "owner": init.get("owner_name") or init.get("owner_role") or "TBD",
            "p50": p50,
            "committed_savings": float(init.get("committed_savings") or 0.0),
            "status": init.get("stage", "identified"),
            "forecast_to_complete": init.get("forecast_to_complete"),
        })

    company_name = (
        manifest.get("company_name")
        or (analysis.get("company_name") if analysis else None)
        or "Client"
    )
    pmo = build_pmo_data(
        summary,
        pmo_rows,
        company_name=company_name,
        engagement_weeks=int(manifest.get("engagement_weeks_total") or 12),
    )
    filename = f"{session_id}_cost_room_portfolio.xlsx"
    path = export_pmo_xlsx(pmo, filename)
    append_audit_event(f"pmo_export_generated session_id={session_id}")
    return {
        "export_url": f"/api/exports/{path.name}",
        "filename": path.name,
        "initiative_count": len(initiatives),
    }


@router.post("/api/evidence-appendix/{session_id}")
@router.post("/api/v1/evidence-appendix/{session_id}")
def create_evidence_appendix(session_id: str) -> Dict[str, Any]:
    validate_session_id(session_id)
    analysis = _memory.get("session", session_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="No analysis for session")
    ctx = _engagement_context(session_id, analysis)
    appendix = build_evidence_appendix(
        analysis,
        company_name=ctx["company_name"],
    )
    path = export_evidence_appendix_docx(appendix, f"{session_id}_evidence_appendix.docx")
    append_audit_event(f"evidence_appendix_generated session_id={session_id}")
    return {"evidence_appendix": appendix, "export_url": f"/api/exports/{path.name}", "filename": path.name}


@router.get("/api/sensitivity/{session_id}")
@router.get("/api/v1/sensitivity/{session_id}")
def get_sensitivity(
    session_id: str,
    discount_rate: float = Query(0.10, ge=0.01, le=0.50),
    effective_tax_rate: float = Query(0.0, ge=0.0, le=0.60),
    execution_rate_pct: float | None = Query(None, ge=0.0, le=1.0),
    headcount_growth_pct: float = Query(0.0, ge=-0.5, le=1.0),
    revenue_growth_pct: float = Query(0.0, ge=-0.5, le=1.0),
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


def _skill_or_unavailable(
    analysis: Dict[str, Any],
    skill_key: str,
    flag_key: str,
    empty_list_keys: tuple[str, ...],
) -> Dict[str, Any]:
    """Return the skill output, or the same `{*_available: False, reason}` shape
    the skills emit on insufficient data when the skill has not run yet."""
    output = analysis.get("skill_outputs", {}).get(skill_key)
    if output is not None:
        return output
    unavailable: Dict[str, Any] = {
        flag_key: False,
        "reason": "Analysis has not been run for this session — run analysis first.",
    }
    for key in empty_list_keys:
        unavailable[key] = []
    return unavailable


@router.get("/api/v1/trends/{session_id}")
def get_trends(session_id: str) -> Dict[str, Any]:
    validate_session_id(session_id)
    analysis = _memory.get("session", session_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="No analysis for session")
    return _skill_or_unavailable(
        analysis, "temporal-analyzer", "temporal_available", ("period_trends", "category_trends"),
    )


@router.get("/api/v1/bva/{session_id}")
def get_bva(session_id: str) -> Dict[str, Any]:
    validate_session_id(session_id)
    analysis = _memory.get("session", session_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="No analysis for session")
    return _skill_or_unavailable(analysis, "bva-analyzer", "bva_available", ("variances",))


@router.get("/api/v1/payment-terms/{session_id}")
def get_payment_terms(session_id: str) -> Dict[str, Any]:
    validate_session_id(session_id)
    analysis = _memory.get("session", session_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="No analysis for session")
    return _skill_or_unavailable(
        analysis, "payment-terms-optimizer", "payment_terms_available", ("opportunities",),
    )


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
