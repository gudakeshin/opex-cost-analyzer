"""Engagement-scoped document management API."""
# NOTE: no `from __future__ import annotations` here — slowapi's @limiter.limit
# wrapper cannot resolve postponed annotations (UploadFile etc.) because
# FastAPI evaluates them against the wrapper's __globals__, not this module's.
import hashlib
import uuid
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.config import MAX_UPLOAD_MB, logger
from app.ratelimit import RATE_LIMIT_UPLOAD, limiter
from app.routers._shared import (
    engagement_lock,
    utc_now_iso,
    validate_document_id,
    validate_engagement_id,
)
from app.schemas import EngagementCreateRequest, EngagementPatchRequest
from app.security.auth import check_owner, current_principal, visible_to_principal
from app.services.analysis import load_taxonomy
from app.services.compliance import append_audit_event
from app.services.document_pipeline import (
    _should_stream_csv,
    load_cached_ingestion_report,
    process_engagement_document,
    validate_upload_suffix,
)
from app.services.ingestion import MAPPABLE_FIELDS
from app.services.jobs import enqueue_job
from app.services.engagements_store import (
    SUPPORTED_EXTENSIONS,
    add_document_record,
    create_engagement_manifest,
    delete_document,
    delete_engagement,
    document_dir,
    engagement_dir,
    ensure_engagement_exists,
    get_document_record,
    list_engagements,
    repair_engagement_manifest,
    search_engagements,
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
        append_audit_event("document_parsed", engagement_id=engagement_id, data={"document_id": document_id})
        # Refresh the engagement's auto-detected company/industry recommendation
        # from everything parsed so far. Off the request path (background task);
        # the LLM contextualizer is cached by content hash inside detection.
        try:
            from app.services.engagement_detection import detect_engagement_profile
            from app.services.engagements_store import update_engagement_detection

            detection = detect_engagement_profile(engagement_id)
            update_engagement_detection(engagement_id, detection)
        except Exception as exc:
            logger.warning("engagement detection failed engagement_id=%s: %s", engagement_id, exc)
    except Exception as exc:
        logger.warning("background document pipeline failed: %s", exc)
        append_audit_event(
            "document_failed",
            engagement_id=engagement_id,
            data={"document_id": document_id, "error": str(exc)},
        )


@router.post("/api/v1/engagements")
def create_engagement(request: Request, payload: EngagementCreateRequest) -> Dict[str, Any]:
    manifest = create_engagement_manifest(
        company_name=payload.company_name,
        industry=payload.industry,
        annual_revenue=payload.annual_revenue,
        currency=payload.currency or "INR",
        headcount=payload.headcount,
        owner=current_principal(request),
    )
    append_audit_event("engagement_created", engagement_id=manifest["engagement_id"])
    return manifest


@router.get("/api/v1/engagements")
def get_engagements(request: Request, q: str | None = None) -> List[Dict[str, Any]]:
    rows = search_engagements(q) if q else list_engagements()
    return [m for m in rows if visible_to_principal(request, m.get("owner"))]


@router.get("/api/engagements")
def get_engagements_legacy(request: Request, q: str | None = None) -> List[Dict[str, Any]]:
    return get_engagements(request, q=q)


@router.get("/api/v1/engagements/{engagement_id}")
def get_engagement(engagement_id: str) -> Dict[str, Any]:
    validate_engagement_id(engagement_id)
    from app.services.engagement_detection import reconcile_detection_view

    manifest = ensure_engagement_exists(engagement_id)
    return reconcile_detection_view(manifest)


@router.patch("/api/v1/engagements/{engagement_id}")
def patch_engagement(engagement_id: str, payload: EngagementPatchRequest) -> Dict[str, Any]:
    validate_engagement_id(engagement_id)
    manifest = ensure_engagement_exists(engagement_id)
    if payload.company_name is not None:
        manifest["company_name"] = payload.company_name
    if payload.industry is not None:
        from app.services.sector_packs import normalize_industry_selection

        manifest["industry"] = normalize_industry_selection(payload.industry) or payload.industry
        manifest["industry_user_set"] = bool(manifest["industry"])
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


@router.delete("/api/v1/engagements/{engagement_id}")
def remove_engagement(request: Request, engagement_id: str) -> Dict[str, Any]:
    validate_engagement_id(engagement_id)
    manifest = ensure_engagement_exists(engagement_id)
    check_owner(request, manifest.get("owner"))
    delete_engagement(engagement_id)
    append_audit_event("engagement_deleted", engagement_id=engagement_id)
    return {"deleted": engagement_id, "status": "removed"}


@router.delete("/api/engagements/{engagement_id}")
def remove_engagement_legacy(request: Request, engagement_id: str) -> Dict[str, Any]:
    return remove_engagement(request, engagement_id)


@router.post("/api/v1/engagements/{engagement_id}/repair-manifest")
def repair_manifest(engagement_id: str) -> Dict[str, Any]:
    """Rebuild manifest.json from salvageable JSON and on-disk document folders."""
    validate_engagement_id(engagement_id)
    if not engagement_dir(engagement_id).exists():
        raise HTTPException(status_code=404, detail="Engagement not found")
    manifest = repair_engagement_manifest(engagement_id)
    append_audit_event("manifest_repaired", engagement_id=engagement_id)
    docs = manifest.get("documents") or []
    return {
        "repaired": True,
        "engagement_id": engagement_id,
        "document_count": len(docs),
        "manifest_status": "ok",
    }


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
@limiter.limit(RATE_LIMIT_UPLOAD)
async def upload_document(
    engagement_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    allow_duplicate: bool = False,
) -> Dict[str, Any]:
    validate_engagement_id(engagement_id)
    manifest = ensure_engagement_exists(engagement_id)
    currency = str(manifest.get("currency") or "INR")
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

    document_id = str(uuid.uuid4())
    ddir = document_dir(engagement_id, document_id)
    raw_path = ddir / f"raw{suffix}"

    # Spool the body to disk in chunks — a 500MB CSV must never be buffered
    # whole in memory. Size is enforced as bytes arrive.
    tmp_path = ddir.parent / f".upload-{document_id}{suffix}"
    tmp_path.parent.mkdir(parents=True, exist_ok=True)
    size_bytes = 0
    digest = hashlib.sha256()
    try:
        with tmp_path.open("wb") as spool:
            while chunk := await file.read(1 << 20):
                digest.update(chunk)
                size_bytes += len(chunk)
                if size_bytes > _max_bytes:
                    raise HTTPException(
                        status_code=413, detail=f"File exceeds {MAX_UPLOAD_MB} MB limit"
                    )
                spool.write(chunk)

        # Register manifest + sidecar meta before writing raw bytes so orphan-folder
        # repair cannot synthesize a duplicate upload.* row for the same document_id.
        content_sha256 = digest.hexdigest()
        async with engagement_lock(engagement_id):
            if not allow_duplicate:
                for existing in ensure_engagement_exists(engagement_id).get("documents") or []:
                    if existing.get("content_sha256") == content_sha256:
                        raise HTTPException(
                            status_code=409,
                            detail=(
                                f"This file was already uploaded as '{existing.get('filename')}'. "
                                "Uploading it again would double-count its spend."
                            ),
                        )
            record = add_document_record(
                engagement_id,
                document_id=document_id,
                filename=safe_filename,
                content_type=file.content_type or "application/octet-stream",
                size_bytes=size_bytes,
                raw_path=str(raw_path),
                _already_locked=True,
                content_sha256=content_sha256,
            )
            ddir.mkdir(parents=True, exist_ok=True)
            tmp_path.replace(raw_path)
    finally:
        tmp_path.unlink(missing_ok=True)

    append_audit_event(
        "document_uploaded",
        engagement_id=engagement_id,
        data={"document_id": document_id, "file": safe_filename},
    )
    use_job = (
        suffix.lower() == ".csv" and _should_stream_csv(raw_path)
    ) or size_bytes > 100 * 1024 * 1024
    if use_job:
        job_id = enqueue_job(
            "document_parse",
            {
                "engagement_id": engagement_id,
                "document_id": document_id,
                "currency": currency,
            },
        )
        return {"document": record, "status": "pending", "job_id": job_id}
    background_tasks.add_task(_run_document_pipeline, engagement_id, document_id, currency)
    return {"document": record, "status": "pending"}


@router.delete("/api/v1/engagements/{engagement_id}/documents/{document_id}")
def remove_document(engagement_id: str, document_id: str) -> Dict[str, Any]:
    validate_engagement_id(engagement_id)
    validate_document_id(document_id)
    delete_document(engagement_id, document_id)
    append_audit_event("document_deleted", engagement_id=engagement_id, data={"document_id": document_id})
    return {"deleted": document_id}


class ReprocessRequest(BaseModel):
    # field -> source column name ("" ignores the field). Omit to keep the current mapping;
    # send {} to clear manual overrides and return to automatic matching.
    column_overrides: Dict[str, str] | None = None


@router.get("/api/v1/engagements/{engagement_id}/documents/{document_id}/ingestion-report")
def get_document_ingestion_report(engagement_id: str, document_id: str) -> Dict[str, Any]:
    """Parse-time report for a spend document: rows dropped, warnings and the column mapping."""
    validate_engagement_id(engagement_id)
    validate_document_id(document_id)
    ensure_engagement_exists(engagement_id)
    record = get_document_record(engagement_id, document_id)
    return {
        "document_id": document_id,
        "filename": record.get("filename"),
        "report": load_cached_ingestion_report(engagement_id, document_id),
        "column_overrides": record.get("column_overrides") or {},
    }


@router.post("/api/v1/engagements/{engagement_id}/documents/{document_id}/reprocess")
@limiter.limit(RATE_LIMIT_UPLOAD)
async def reprocess_document(
    request: Request,
    engagement_id: str,
    document_id: str,
    background_tasks: BackgroundTasks,
    payload: ReprocessRequest | None = None,
) -> Dict[str, Any]:
    validate_engagement_id(engagement_id)
    validate_document_id(document_id)
    manifest = ensure_engagement_exists(engagement_id)
    get_document_record(engagement_id, document_id)
    patch: Dict[str, Any] = {"status": "pending", "error": None}
    if payload is not None and payload.column_overrides is not None:
        unknown = sorted(set(payload.column_overrides) - set(MAPPABLE_FIELDS))
        if unknown:
            raise HTTPException(status_code=422, detail=f"Unknown field(s) to map: {', '.join(unknown)}")
        patch["column_overrides"] = payload.column_overrides
    update_document_record(engagement_id, document_id, patch)
    currency = str(manifest.get("currency") or "INR")
    background_tasks.add_task(_run_document_pipeline, engagement_id, document_id, currency)
    return {"document_id": document_id, "status": "pending"}
