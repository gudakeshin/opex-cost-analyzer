"""Source-system connector ingest endpoints."""
from __future__ import annotations

import asyncio
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request

from app.routers._shared import validate_engagement_id
from app.schemas import ConnectorIngestRequest
from app.services.compliance import append_audit_event
from app.services.connector_ingest import ingest_via_connector
from app.services.connector_registry import list_connectors
from app.services.connector_sync import list_watermarks
from app.services.jobs import enqueue_job

router = APIRouter()


@router.get("/api/connectors")
@router.get("/api/v1/connectors")
def get_connectors() -> Dict[str, Any]:
    return {"connectors": list_connectors()}


@router.get("/api/v1/engagements/{engagement_id}/connector-watermarks")
def get_connector_watermarks(engagement_id: str) -> Dict[str, Any]:
    validate_engagement_id(engagement_id)
    return {"engagement_id": engagement_id, "watermarks": list_watermarks(engagement_id)}


@router.post("/api/connectors/{connector_type}/ingest")
@router.post("/api/v1/connectors/{connector_type}/ingest")
async def ingest_connector(
    connector_type: str,
    payload: ConnectorIngestRequest,
    request: Request,
) -> Dict[str, Any]:
    _ = request
    job_payload = {
        "session_id": payload.session_id,
        "connector_type": connector_type,
        "source_file": payload.source_file,
        "source_system_id": payload.source_system_id,
        "credentials": payload.credentials,
        "fetch_kwargs": payload.fetch_kwargs,
        "run_analysis": payload.run_analysis,
        "delta_sync": payload.delta_sync,
    }

    if payload.async_mode or payload.delta_sync:
        job_id = enqueue_job("connector_ingest", job_payload)
        append_audit_event(
            "connector_ingest_queued",
            session_id=payload.session_id,
            data={"connector_type": connector_type, "job_id": job_id, "delta_sync": payload.delta_sync},
        )
        return {
            "status": "queued",
            "job_id": job_id,
            "connector_type": connector_type,
            "session_id": payload.session_id,
            "delta_sync": payload.delta_sync,
        }

    try:
        result = await asyncio.to_thread(
            ingest_via_connector,
            payload.session_id,
            connector_type,
            source_file=payload.source_file,
            source_system_id=payload.source_system_id,
            credentials=payload.credentials,
            fetch_kwargs=payload.fetch_kwargs,
            run_analysis=payload.run_analysis,
            delta_sync=payload.delta_sync,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    append_audit_event(
        "connector_ingest",
        session_id=payload.session_id,
        data={"connector_type": connector_type, "row_count": result.get("row_count", 0)},
    )
    return result
