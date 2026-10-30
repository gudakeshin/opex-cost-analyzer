"""Job status API."""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request

from app.security.auth import check_session_owner
from app.services.jobs import get_job

router = APIRouter()


@router.get("/api/v1/jobs/{job_id}")
def get_job_status(request: Request, job_id: str) -> Dict[str, Any]:
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    payload = job.get("payload") or {}
    session_id = payload.get("session_id")
    if session_id:
        check_session_owner(request, session_id)
    return job
