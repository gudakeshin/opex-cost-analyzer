from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from app.config import MAX_UPLOAD_MB, logger
from app.opar.orchestrator import run_opar_loop, run_opar_plan_preview
from app.routers._shared import (
    session_lock,
    merge_context_into_manifest,
    progress_append,
    progress_complete,
    progress_get,
    progress_init,
    read_manifest,
    session_dir,
    validate_session_id,
    write_manifest,
)
from app.schemas import ChatRequest, V1ChatRequest
from app.services.compliance import append_audit_event
from app.services.ingestion import infer_tabular_schema, parse_document

router = APIRouter()

_OPAR_TIMEOUT_S = int(os.getenv("OPAR_TIMEOUT_SECONDS", "120"))


def _opar_response(result: Any, run_id: str, session_id: str | None = None) -> Dict[str, Any]:
    ingestion_summary = None
    if session_id:
        try:
            manifest = read_manifest(session_id)
            ingestion_summary = manifest.get("ingestion_summary")
        except Exception:
            pass
    return {
        "response_text": result.response_text,
        "artefacts": result.response_artefacts,
        "advisory_sections": getattr(result, "advisory_sections", None).model_dump()
        if getattr(result, "advisory_sections", None)
        else {},
        "quality_signals": getattr(result, "quality_signals", {}),
        "used_llm_synthesis": getattr(result, "used_llm_synthesis", False),
        "thinking": getattr(result, "thinking_text", None),
        "degraded_mode": getattr(result, "degraded_mode", False),
        "fallback_reasons": getattr(result, "fallback_reasons", {}),
        "loop_complete": result.loop_complete,
        "next_loop_trigger": result.next_loop_trigger,
        "progress_steps": getattr(result, "progress_steps", []),
        "next_options": getattr(result, "next_options", []),
        "ingestion_summary": ingestion_summary,
        "run_id": run_id,
    }


@router.post("/api/v1/chat/with-files")
async def chat_v1_with_files(
    message: str = Form(...),
    session_id: str = Form(...),
    user_id: str | None = Form(None),
    run_id: str | None = Form(None),
    company_name: str | None = Form(None),
    industry: str | None = Form(None),
    annual_revenue: float | None = Form(None),
    currency: str | None = Form(None),
    audience: str | None = Form(None),
    headcount: float | None = Form(None),
    files: List[UploadFile] = File(default=[]),
) -> Dict[str, Any]:
    validate_session_id(session_id)
    if not session_dir(session_id).exists():
        raise HTTPException(status_code=404, detail="Session not found")
    run_id = run_id or str(uuid.uuid4())
    progress_init(run_id, session_id)

    manifest = read_manifest(session_id)
    if merge_context_into_manifest(
        manifest,
        company_name=company_name,
        industry=industry,
        annual_revenue=annual_revenue,
        currency=currency,
        audience=audience,
        headcount=headcount,
    ):
        write_manifest(session_id, manifest)
    if not user_id:
        company = manifest.get("company_name") or "default"
        user_id = company.lower().replace(" ", "_").replace(".", "_")

    _max_bytes = MAX_UPLOAD_MB * 1024 * 1024
    uploaded_summaries: List[Dict[str, Any]] = []
    new_manifest_entries: List[Dict[str, Any]] = []
    for file in files:
        if not file.filename:
            continue
        content = await file.read()
        if len(content) > _max_bytes:
            raise HTTPException(status_code=413, detail=f"File '{file.filename}' exceeds {MAX_UPLOAD_MB} MB limit")
        safe_filename = Path(file.filename).name
        out_path = session_dir(session_id) / safe_filename
        out_path.write_bytes(content)
        entry: Dict[str, Any] = {
            "name": safe_filename,
            "content_type": file.content_type or "application/octet-stream",
            "size_bytes": len(content),
            "path": str(out_path),
        }
        schema: Dict[str, Any] = {}
        doc_stats: Dict[str, Any] = {}
        if out_path.suffix.lower() in (".csv", ".xlsx", ".xls", ".json"):
            if out_path.suffix.lower() == ".json":
                entry["schema"] = {"format": "json", "rows": 0}
            else:
                schema = await asyncio.to_thread(infer_tabular_schema, out_path)
                entry["schema"] = schema
        else:
            extracted = await asyncio.to_thread(parse_document, out_path)
            if extracted:
                lines = [ln for ln in extracted.splitlines() if ln.strip()]
                doc_stats = {
                    "text_chars": len(extracted),
                    "text_lines": len(lines),
                    "text_preview": extracted[:180],
                }
                entry["doc_stats"] = doc_stats
        new_manifest_entries.append(entry)
        append_audit_event(f"file_uploaded session_id={session_id} file={safe_filename}")

        sem = schema.get("semantic_map", {}) if schema else {}
        detected = {role: col for role, col in sem.items() if col}
        suffix = out_path.suffix.lower()
        if suffix in (".csv", ".xlsx", ".xls", ".json"):
            uploaded_summaries.append({
                "name": safe_filename,
                "file_kind": "tabular",
                "rows": schema.get("rows", 0),
                "detected_columns": detected,
                "total_columns": len(schema.get("columns", [])),
            })
        else:
            uploaded_summaries.append({
                "name": safe_filename,
                "file_kind": "document",
                "rows": None,
                "detected_columns": {},
                "total_columns": 0,
                "text_chars": doc_stats.get("text_chars", 0),
                "text_lines": doc_stats.get("text_lines", 0),
                "text_preview": doc_stats.get("text_preview", ""),
            })

    if new_manifest_entries:
        async with session_lock(session_id):
            manifest = read_manifest(session_id)
            manifest["files"].extend(new_manifest_entries)
            write_manifest(session_id, manifest)

    try:
        result = await asyncio.wait_for(
            run_opar_loop(
                message,
                session_id,
                user_id,
                None,
                lambda phase, msg: progress_append(run_id, phase, msg),
            ),
            timeout=float(_OPAR_TIMEOUT_S),
        )
        progress_complete(run_id)
    except asyncio.TimeoutError:
        progress_complete(run_id, failed=True, error="timeout")
        raise HTTPException(
            status_code=408,
            detail={
                "error": "analysis_timeout",
                "message": f"Analysis timed out after {_OPAR_TIMEOUT_S}s.",
            },
        )
    except Exception as e:
        progress_complete(run_id, failed=True, error=str(e))
        raise
    append_audit_event(f"opar_chat_with_files session_id={session_id} files={len(files)}")

    response = _opar_response(result, run_id, session_id=session_id)
    if uploaded_summaries:
        response["uploaded_files"] = uploaded_summaries
    return response


@router.post("/api/v1/chat")
async def chat_v1_opar(payload: V1ChatRequest) -> Dict[str, Any]:
    validate_session_id(payload.session_id)
    if not session_dir(payload.session_id).exists():
        raise HTTPException(status_code=404, detail="Session not found")
    run_id = payload.run_id or str(uuid.uuid4())
    progress_init(run_id, payload.session_id)
    manifest = read_manifest(payload.session_id)
    if merge_context_into_manifest(
        manifest,
        company_name=payload.company_name,
        industry=payload.industry,
        annual_revenue=payload.annual_revenue,
        currency=payload.currency,
        audience=payload.audience,
        headcount=payload.headcount,
    ):
        write_manifest(payload.session_id, manifest)
    user_id = payload.user_id
    if not user_id:
        company = manifest.get("company_name") or "default"
        user_id = company.lower().replace(" ", "_").replace(".", "_")
    thinking_enabled = (payload.thinking_mode == "extended")
    try:
        result = await asyncio.wait_for(
            run_opar_loop(
                payload.message,
                payload.session_id,
                user_id,
                None,
                lambda phase, msg: progress_append(run_id, phase, msg),
                thinking_enabled=thinking_enabled,
            ),
            timeout=float(_OPAR_TIMEOUT_S),
        )
        progress_complete(run_id)
    except asyncio.TimeoutError:
        progress_complete(run_id, failed=True, error="timeout")
        raise HTTPException(
            status_code=408,
            detail={"error": "analysis_timeout", "message": f"Timed out after {_OPAR_TIMEOUT_S}s"},
        )
    except Exception as e:
        progress_complete(run_id, failed=True, error=str(e))
        raise
    append_audit_event(f"opar_chat session_id={payload.session_id}")
    return _opar_response(result, run_id, session_id=payload.session_id)


@router.get("/api/v1/chat/progress/{run_id}")
def chat_v1_progress(run_id: str) -> Dict[str, Any]:
    entry = progress_get(run_id)
    if not entry:
        return {"run_id": run_id, "status": "not_found", "steps": []}
    return entry


@router.post("/api/v1/chat/plan")
def chat_v1_plan_preview(payload: V1ChatRequest) -> Dict[str, Any]:
    validate_session_id(payload.session_id)
    if not session_dir(payload.session_id).exists():
        raise HTTPException(status_code=404, detail="Session not found")
    manifest = read_manifest(payload.session_id)
    if merge_context_into_manifest(
        manifest,
        company_name=payload.company_name,
        industry=payload.industry,
        annual_revenue=payload.annual_revenue,
        currency=payload.currency,
        audience=payload.audience,
        headcount=payload.headcount,
    ):
        write_manifest(payload.session_id, manifest)
    user_id = payload.user_id
    if not user_id:
        company = manifest.get("company_name") or "default"
        user_id = company.lower().replace(" ", "_").replace(".", "_")
    return run_opar_plan_preview(payload.message, payload.session_id, user_id)


@router.post("/api/chat/{session_id}")
@router.post("/api/v1/chat/{session_id}")
async def chat_with_planner(session_id: str, payload: ChatRequest) -> Dict[str, Any]:
    validate_session_id(session_id)
    if not session_dir(session_id).exists():
        raise HTTPException(status_code=404, detail="Session not found")
    manifest = read_manifest(session_id)
    user_id = (manifest.get("company_name") or "default").lower().replace(" ", "_").replace(".", "_")
    try:
        result = await asyncio.wait_for(
            run_opar_loop(payload.message, session_id, user_id),
            timeout=float(_OPAR_TIMEOUT_S),
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=408,
            detail={"error": "analysis_timeout", "message": f"Timed out after {_OPAR_TIMEOUT_S}s"},
        )
    append_audit_event(f"chat_opar session_id={session_id}")
    return {
        "session_id": session_id,
        "assistant_message": result.response_text,
        "asked_question": bool(result.next_loop_trigger),
        "response_text": result.response_text,
        "advisory_sections": getattr(result, "advisory_sections", None).model_dump()
        if getattr(result, "advisory_sections", None)
        else {},
        "quality_signals": getattr(result, "quality_signals", {}),
        "used_llm_synthesis": getattr(result, "used_llm_synthesis", False),
        "degraded_mode": getattr(result, "degraded_mode", False),
        "fallback_reasons": getattr(result, "fallback_reasons", {}),
        "next_loop_trigger": result.next_loop_trigger,
        "loop_complete": result.loop_complete,
    }
