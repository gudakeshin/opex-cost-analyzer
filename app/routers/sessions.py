from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import Response

from app.config import MAX_UPLOAD_MB, UPLOAD_DIR, logger
from app.routers._shared import (
    _memory,
    read_manifest,
    session_dir,
    session_lock,
    utc_now_iso,
    validate_session_id,
    write_manifest,
)
from app.schemas import AnalyzeRequest, SessionCreateRequest
from app.services.analysis import load_taxonomy, run_core_pipeline
from app.services.compliance import append_audit_event
from app.services.ingestion import infer_tabular_schema, parse_document, parse_spend_file
from app.skills.model_contextualizer import (
    build_workbook_manifest,
    compute_file_fingerprint,
    should_run_model_contextualizer,
)

router = APIRouter()


@router.get("/api/template/spend-csv")
@router.get("/api/v1/template/spend-csv")
def download_spend_template() -> Response:
    """Return a downloadable CSV template whose columns match NormalizedSpendLine."""
    headers_row = (
        "supplier,description,amount,currency,business_unit,cost_center_id,"
        "gl_code,country,category,spend_date,fiscal_year,fiscal_period,"
        "amount_type,payment_terms_days,contract_id,contract_expiry_date"
    )
    example_row = (
        "Infosys Ltd,Cloud infrastructure services,5000000,INR,Engineering,"
        "CC-101,5100,India,IT & Cloud,2024-01-31,FY2024,Q4,actual,30,"
        "C-2024-001,2025-12-31"
    )
    csv_content = f"{headers_row}\n{example_row}\n"
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=opex_spend_template.csv"},
    )


@router.post("/api/sessions")
@router.post("/api/v1/sessions")
def create_session(payload: SessionCreateRequest) -> Dict[str, Any]:
    session_id = str(uuid.uuid4())
    session_dir(session_id).mkdir(parents=True, exist_ok=True)
    manifest = {
        "session_id": session_id,
        "company_name": payload.company_name,
        "industry": payload.industry or "",
        "annual_revenue": payload.annual_revenue,
        "currency": payload.currency,
        "audience": payload.audience or "cfo",
        "headcount": payload.headcount,
        "wacc": payload.wacc,
        "effective_tax_rate": payload.effective_tax_rate,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "files": [],
    }
    write_manifest(session_id, manifest)
    append_audit_event(f"session_created session_id={session_id}")
    return manifest


@router.post("/api/upload/{session_id}")
@router.post("/api/v1/upload/{session_id}")
async def upload_file(session_id: str, request: Request, file: UploadFile = File(...)) -> Dict[str, Any]:
    validate_session_id(session_id)
    if not session_dir(session_id).exists():
        raise HTTPException(status_code=404, detail="Session not found")
    _max_bytes = MAX_UPLOAD_MB * 1024 * 1024
    cl = request.headers.get("content-length")
    if cl and int(cl) > _max_bytes:
        raise HTTPException(status_code=413, detail=f"File exceeds {MAX_UPLOAD_MB} MB limit")
    content = await file.read()
    if len(content) > _max_bytes:
        raise HTTPException(status_code=413, detail=f"File exceeds {MAX_UPLOAD_MB} MB limit")
    safe_filename = Path(file.filename or "upload").name
    out_path = session_dir(session_id) / safe_filename
    out_path.write_bytes(content)
    entry: Dict[str, Any] = {
        "name": safe_filename,
        "content_type": file.content_type or "application/octet-stream",
        "size_bytes": len(content),
        "path": str(out_path),
    }
    if out_path.suffix.lower() in (".csv", ".xlsx", ".xls"):
        entry["schema"] = await asyncio.to_thread(infer_tabular_schema, out_path)
    async with session_lock(session_id):
        manifest = read_manifest(session_id)
        manifest["files"].append(entry)
        write_manifest(session_id, manifest)
    append_audit_event(f"file_uploaded session_id={session_id} file={safe_filename}")
    return {"uploaded": safe_filename, "size_bytes": len(content)}


@router.post("/api/analyze/{session_id}")
@router.post("/api/v1/analyze/{session_id}")
async def analyze_session(session_id: str, payload: AnalyzeRequest) -> Dict[str, Any]:
    validate_session_id(session_id)
    if not session_dir(session_id).exists():
        raise HTTPException(status_code=404, detail="Session not found")
    manifest = read_manifest(session_id)
    if should_run_model_contextualizer(manifest.get("files", []), "run analysis"):
        model_manifest = manifest.get("model_manifest") if isinstance(manifest, dict) else None
        workbook_fingerprint = compute_file_fingerprint(manifest.get("files", []))
        if not model_manifest or str(model_manifest.get("workbook_fingerprint") or "") != workbook_fingerprint:
            for item in manifest.get("files", []):
                path = Path(item.get("path", ""))
                if path.suffix.lower() not in (".xlsx", ".xls") or not path.exists():
                    continue
                try:
                    parsed_manifest, meta = await asyncio.to_thread(
                        build_workbook_manifest,
                        path,
                        user_message="run analysis",
                        session_meta=manifest,
                    )
                    model_manifest = parsed_manifest.model_dump()
                    model_manifest["workbook_fingerprint"] = workbook_fingerprint
                    model_manifest["source_file"] = path.name
                    model_manifest["source"] = "llm" if meta.get("llm_used") else "heuristic"
                    manifest["model_manifest"] = model_manifest
                    write_manifest(session_id, manifest)
                    break
                except Exception:
                    logger.warning(
                        "workbook_manifest_build_failed session_id=%s file=%s",
                        session_id, path.name, exc_info=True,
                    )
                    manifest["workbook_manifest_degraded"] = True
                    continue
    taxonomy = load_taxonomy()
    spend_lines = []
    docs_text: List[str] = []
    model_manifest = manifest.get("model_manifest") if isinstance(manifest, dict) else None
    for item in manifest.get("files", []):
        path = Path(item["path"])
        if path.suffix.lower() in (".xlsx", ".xls", ".csv"):
            new_lines = await asyncio.to_thread(parse_spend_file, path, taxonomy, workbook_manifest=model_manifest)
            spend_lines.extend(new_lines)
        else:
            docs_text.append(await asyncio.to_thread(parse_document, path))
    if not spend_lines:
        raise HTTPException(status_code=400, detail="No spend file (.csv/.xlsx/.xls) uploaded")
    if payload.currency is not None:
        manifest["currency"] = payload.currency
    if payload.audience is not None:
        manifest["audience"] = payload.audience
    if payload.currency is not None or payload.audience is not None:
        write_manifest(session_id, manifest)
    analysis = await asyncio.to_thread(
        run_core_pipeline,
        session_id=session_id,
        lines=spend_lines,
        docs_text=docs_text,
        industry=payload.industry or manifest.get("industry") or "",
        annual_revenue=payload.annual_revenue or float(manifest.get("annual_revenue") or 0.0),
        company_name=payload.company_name or manifest.get("company_name"),
        wacc=float(manifest.get("wacc") or payload.wacc or 0.10),
        effective_tax_rate=float(manifest.get("effective_tax_rate") or payload.effective_tax_rate or 0.0),
        reporting_currency=str(payload.currency or manifest.get("currency") or "USD"),
    )
    manifest_changed = False
    if analysis.get("company_name") and manifest.get("company_name") != analysis["company_name"]:
        manifest["company_name"] = analysis["company_name"]
        manifest_changed = True
    if analysis.get("industry") and manifest.get("industry") != analysis["industry"]:
        manifest["industry"] = analysis["industry"]
        manifest_changed = True
    if analysis.get("annual_revenue") and not manifest.get("annual_revenue"):
        manifest["annual_revenue"] = analysis["annual_revenue"]
        manifest_changed = True
    if manifest_changed:
        manifest.setdefault("gate_label", "Gate 2: Portfolio sign-off")
        write_manifest(session_id, manifest)
    append_audit_event(f"analysis_completed session_id={session_id}")
    return analysis


@router.get("/api/sessions/{session_id}")
@router.get("/api/v1/sessions/{session_id}")
def get_session_analysis(session_id: str) -> Dict[str, Any]:
    from app.routers._shared import _memory
    validate_session_id(session_id)
    result = _memory.get("session", session_id)
    if not result:
        raise HTTPException(status_code=404, detail="No analysis for session")
    return result


@router.get("/api/sessions/{session_id}/manifest")
@router.get("/api/v1/sessions/{session_id}/manifest")
def get_session_manifest(session_id: str) -> Dict[str, Any]:
    validate_session_id(session_id)
    if not session_dir(session_id).exists():
        raise HTTPException(status_code=404, detail="Session not found")
    manifest = read_manifest(session_id)
    manifest.setdefault("session_id", session_id)
    return manifest


@router.get("/api/schema/{session_id}")
@router.get("/api/v1/schema/{session_id}")
def get_session_schema(session_id: str) -> Dict[str, Any]:
    validate_session_id(session_id)
    if not session_dir(session_id).exists():
        raise HTTPException(status_code=404, detail="Session not found")
    manifest = read_manifest(session_id)
    schemas = [f["schema"] for f in manifest.get("files", []) if f.get("schema")]
    return {"session_id": session_id, "schemas": schemas}


@router.get("/api/v1/sessions")
def list_sessions() -> List[Dict[str, Any]]:
    """Return a summary of all sessions, newest first. Used by the History page."""
    from app.storage import read_json as _read_json
    summaries: List[Dict[str, Any]] = []
    if not UPLOAD_DIR.exists():
        return summaries
    for session_path in UPLOAD_DIR.iterdir():
        if not session_path.is_dir():
            continue
        try:
            uuid.UUID(session_path.name, version=4)
        except ValueError:
            continue
        manifest_file = session_path / "manifest.json"
        if not manifest_file.exists():
            continue
        try:
            manifest = _read_json(manifest_file, {})
            analysis = _memory.get("session", session_path.name)
            top_savings = None
            if analysis and isinstance(analysis, dict):
                top_savings = analysis.get("total_savings_opportunity")
            summaries.append({
                "session_id": session_path.name,
                "company_name": manifest.get("company_name") or "Unknown",
                "industry": manifest.get("industry") or "",
                "currency": manifest.get("currency") or "USD",
                "annual_revenue": manifest.get("annual_revenue"),
                "created_at": manifest.get("created_at"),
                "file_count": len(manifest.get("files", [])),
                "has_analysis": analysis is not None,
                "top_savings_estimate": top_savings,
            })
        except Exception:
            continue
    summaries.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return summaries


@router.post("/api/v1/analyze/{session_id}/incremental")
async def incremental_analyze(session_id: str, files: List[UploadFile] = File(default=[])) -> Dict[str, Any]:
    """Upload additional spend files and merge into an existing session."""
    validate_session_id(session_id)
    if not session_dir(session_id).exists():
        raise HTTPException(status_code=404, detail="Session not found")
    manifest = read_manifest(session_id)
    taxonomy = load_taxonomy()
    new_lines = []
    for file in files:
        if not file.filename:
            continue
        content = await file.read()
        if len(content) > MAX_UPLOAD_MB * 1024 * 1024:
            raise HTTPException(status_code=413, detail=f"File '{file.filename}' exceeds {MAX_UPLOAD_MB} MB")
        safe_filename = Path(file.filename).name
        out_path = session_dir(session_id) / safe_filename
        out_path.write_bytes(content)
        if out_path.suffix.lower() in (".csv", ".xlsx", ".xls"):
            from app.services.ingestion import parse_spend_file as _psf
            try:
                parsed = await asyncio.to_thread(_psf, out_path, taxonomy)
                new_lines.extend(parsed)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc))
    if not new_lines:
        raise HTTPException(status_code=400, detail="No parseable spend files uploaded")
    from app.services.analysis import run_incremental_pipeline
    try:
        result = run_incremental_pipeline(session_id=session_id, new_lines=new_lines)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    append_audit_event(f"incremental_analysis session_id={session_id} lines_added={result.get('lines_added', 0)}")
    return result
