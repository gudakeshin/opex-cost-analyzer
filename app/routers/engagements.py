"""Engagement-scoped document management API."""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from app.config import MAX_UPLOAD_MB, logger
from app.routers._shared import (
    engagement_lock,
    utc_now_iso,
    validate_document_id,
    validate_engagement_id,
)
from app.schemas import EngagementCreateRequest, EngagementPatchRequest
from app.services.analysis import load_taxonomy
from app.services.compliance import append_audit_event
from app.services.document_pipeline import (
    process_engagement_document,
    validate_upload_suffix,
)
from app.services.engagements_store import (
    SUPPORTED_EXTENSIONS,
    add_document_record,
    create_engagement_manifest,
    delete_document,
    document_dir,
    ensure_engagement_exists,
    get_document_record,
    list_engagements,
    read_engagement_manifest,
    update_document_record,
    write_engagement_manifest,
)

router = APIRouter()


def _run_document_pipeline(engagement_id: str, document_id: str, currency: str) -> None:
    try:
        process_engagement_document(
            engagement_id,
            document_id,
            taxonomy=load_taxonomy(),
            reporting_currency=currency,
        )
        append_audit_event(f"document_parsed engagement_id={engagement_id} document_id={document_id}")
    except Exception as exc:
        logger.warning("background document pipeline failed: %s", exc)
        append_audit_event(
            f"document_failed engagement_id={engagement_id} document_id={document_id} error={exc}"
        )


@router.post("/api/v1/engagements")
def create_engagement(payload: EngagementCreateRequest) -> Dict[str, Any]:
    manifest = create_engagement_manifest(
        company_name=payload.company_name,
        industry=payload.industry,
        annual_revenue=payload.annual_revenue,
        currency=payload.currency or "INR",
        headcount=payload.headcount,
    )
    append_audit_event(f"engagement_created engagement_id={manifest['engagement_id']}")
    return manifest


@router.get("/api/v1/engagements")
def get_engagements() -> List[Dict[str, Any]]:
    return list_engagements()


@router.get("/api/v1/engagements/{engagement_id}")
def get_engagement(engagement_id: str) -> Dict[str, Any]:
    validate_engagement_id(engagement_id)
    return ensure_engagement_exists(engagement_id)


@router.patch("/api/v1/engagements/{engagement_id}")
def patch_engagement(engagement_id: str, payload: EngagementPatchRequest) -> Dict[str, Any]:
    validate_engagement_id(engagement_id)
    manifest = ensure_engagement_exists(engagement_id)
    if payload.company_name is not None:
        manifest["company_name"] = payload.company_name
    if payload.industry is not None:
        manifest["industry"] = payload.industry
    if payload.annual_revenue is not None:
        manifest["annual_revenue"] = max(float(payload.annual_revenue), 0.0)
    if payload.currency is not None:
        manifest["currency"] = payload.currency
    if payload.headcount is not None:
        hc = float(payload.headcount)
        manifest["headcount"] = hc if hc > 0 else None
    manifest["updated_at"] = utc_now_iso()
    write_engagement_manifest(engagement_id, manifest)
    return manifest


@router.get("/api/v1/engagements/{engagement_id}/documents")
def list_documents(engagement_id: str) -> Dict[str, Any]:
    validate_engagement_id(engagement_id)
    manifest = ensure_engagement_exists(engagement_id)
    return {
        "engagement_id": engagement_id,
        "documents": manifest.get("documents") or [],
        "supported_extensions": sorted(SUPPORTED_EXTENSIONS),
        "llamaparse_configured": __import__(
            "app.services.llamaparse_client", fromlist=["is_llamaparse_available"]
        ).is_llamaparse_available(),
    }


@router.get("/api/v1/engagements/{engagement_id}/documents/{document_id}")
def get_document(engagement_id: str, document_id: str) -> Dict[str, Any]:
    validate_engagement_id(engagement_id)
    validate_document_id(document_id)
    doc = get_document_record(engagement_id, document_id)
    parsed_dir = document_dir(engagement_id, document_id) / "parsed"
    artifacts = []
    if parsed_dir.exists():
        for p in sorted(parsed_dir.iterdir()):
            if p.is_file():
                artifacts.append({"name": p.name, "size_bytes": p.stat().st_size})
    return {"document": doc, "artifacts": artifacts}


@router.get("/api/v1/engagements/{engagement_id}/documents/{document_id}/raw")
def download_raw_document(engagement_id: str, document_id: str) -> FileResponse:
    validate_engagement_id(engagement_id)
    validate_document_id(document_id)
    doc = get_document_record(engagement_id, document_id)
    raw_path = Path(doc.get("raw_path") or "")
    if not raw_path.is_file():
        raise HTTPException(status_code=404, detail="Raw file not found")
    return FileResponse(
        path=raw_path,
        filename=doc.get("filename") or raw_path.name,
        media_type=doc.get("content_type") or "application/octet-stream",
    )


@router.post("/api/v1/engagements/{engagement_id}/documents")
async def upload_document(
    engagement_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
) -> Dict[str, Any]:
    validate_engagement_id(engagement_id)
    manifest = ensure_engagement_exists(engagement_id)
    _max_bytes = MAX_UPLOAD_MB * 1024 * 1024
    cl = request.headers.get("content-length")
    if cl and int(cl) > _max_bytes:
        raise HTTPException(status_code=413, detail=f"File exceeds {MAX_UPLOAD_MB} MB limit")

    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename required")
    safe_filename = Path(file.filename).name
    try:
        suffix = validate_upload_suffix(safe_filename)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    content = await file.read()
    if len(content) > _max_bytes:
        raise HTTPException(status_code=413, detail=f"File exceeds {MAX_UPLOAD_MB} MB limit")

    document_id = str(uuid.uuid4())
    ddir = document_dir(engagement_id, document_id)
    ddir.mkdir(parents=True, exist_ok=True)
    raw_path = ddir / f"raw{suffix}"
    raw_path.write_bytes(content)

    async with engagement_lock(engagement_id):
        record = add_document_record(
            engagement_id,
            document_id=document_id,
            filename=safe_filename,
            content_type=file.content_type or "application/octet-stream",
            size_bytes=len(content),
            raw_path=str(raw_path),
        )

    append_audit_event(
        f"document_uploaded engagement_id={engagement_id} document_id={document_id} file={safe_filename}"
    )
    currency = str(manifest.get("currency") or "INR")
    background_tasks.add_task(_run_document_pipeline, engagement_id, document_id, currency)
    return {"document": record, "status": "pending"}


@router.delete("/api/v1/engagements/{engagement_id}/documents/{document_id}")
def remove_document(engagement_id: str, document_id: str) -> Dict[str, Any]:
    validate_engagement_id(engagement_id)
    validate_document_id(document_id)
    delete_document(engagement_id, document_id)
    append_audit_event(f"document_deleted engagement_id={engagement_id} document_id={document_id}")
    return {"deleted": document_id}


@router.post("/api/v1/engagements/{engagement_id}/documents/{document_id}/reprocess")
async def reprocess_document(
    engagement_id: str,
    document_id: str,
    background_tasks: BackgroundTasks,
) -> Dict[str, Any]:
    validate_engagement_id(engagement_id)
    validate_document_id(document_id)
    manifest = ensure_engagement_exists(engagement_id)
    get_document_record(engagement_id, document_id)
    update_document_record(engagement_id, document_id, {"status": "pending", "error": None})
    currency = str(manifest.get("currency") or "INR")
    background_tasks.add_task(_run_document_pipeline, engagement_id, document_id, currency)
    return {"document_id": document_id, "status": "pending"}
