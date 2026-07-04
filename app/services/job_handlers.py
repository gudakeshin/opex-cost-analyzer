"""Registered handlers for the durable job queue."""
from __future__ import annotations

import logging
from typing import Any, Dict

from app.config import logger
from app.services.compliance import append_audit_event
from app.services.jobs import register_job_handler, update_job_progress

log = logging.getLogger(__name__)


def _handle_document_parse(payload: Dict[str, Any]) -> Dict[str, Any]:
    from app.services.analysis import load_taxonomy
    from app.services.document_pipeline import process_engagement_document
    from app.services.engagement_detection import detect_engagement_profile
    from app.services.engagements_store import update_engagement_detection

    job_id = payload.get("_job_id")
    engagement_id = payload["engagement_id"]
    document_id = payload["document_id"]
    currency = str(payload.get("currency") or "INR")

    if job_id:
        update_job_progress(job_id, 5, message="Starting document parse")
    result = process_engagement_document(
        engagement_id,
        document_id,
        taxonomy=load_taxonomy(),
        reporting_currency=currency,
    )
    if job_id:
        update_job_progress(job_id, 85, message="Updating engagement detection")
    try:
        detection = detect_engagement_profile(engagement_id)
        update_engagement_detection(engagement_id, detection)
    except Exception as exc:
        logger.warning("engagement detection failed engagement_id=%s: %s", engagement_id, exc)
    append_audit_event("document_parsed", engagement_id=engagement_id, data={"document_id": document_id})
    if job_id:
        update_job_progress(job_id, 100, message="Complete")
    return {"engagement_id": engagement_id, "document_id": document_id, **result}


def _handle_connector_ingest(payload: Dict[str, Any]) -> Dict[str, Any]:
    from app.services.connector_ingest import ingest_via_connector

    job_id = payload.get("_job_id")
    if job_id:
        update_job_progress(job_id, 5, message="Authenticating connector")
    result = ingest_via_connector(
        payload["session_id"],
        payload["connector_type"],
        source_file=payload["source_file"],
        source_system_id=payload.get("source_system_id"),
        credentials=payload.get("credentials") or {},
        fetch_kwargs=payload.get("fetch_kwargs") or {},
        run_analysis=bool(payload.get("run_analysis")),
        delta_sync=bool(payload.get("delta_sync")),
        job_id=job_id,
    )
    if job_id:
        update_job_progress(job_id, 100, message="Connector ingest complete")
    return result


def register_all_job_handlers() -> None:
    register_job_handler("document_parse", _handle_document_parse)
    register_job_handler("connector_ingest", _handle_connector_ingest)
