from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Form, HTTPException
from fastapi.responses import FileResponse

from app.config import OUTPUT_DIR
from app.routers._shared import _memory, read_manifest, session_dir, validate_session_id
from app.services.business_case import build_business_case, export_docx, export_pdf_like_text
from app.services.compliance import append_audit_event
from app.services.dashboard import build_dashboard_html
from app.services.pipeline import create_initiative, list_initiatives
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
    for row in bc.get("sections", {}).get("savings_opportunity", []):
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
            "gross_savings_y1": row.get("savings_y1", 0.0),
            "gross_savings_y2": row.get("savings_y2", 0.0),
            "gross_savings_y3": row.get("savings_y3", 0.0),
            "cost_to_achieve": row.get("cost_to_achieve_3yr", 0.0),
            "net_npv": row.get("net_npv", 0.0),
            "stage": "identified",
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
