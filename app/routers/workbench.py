"""Analysis Workbench API — compose, validate, run, and manage à-la-carte runs.

Thin HTTP layer over app.services.workbench. Runs execute synchronously (like
/api/v1/chat) with live progress pollable via the shared progress store using the
run's ``run_id``.
"""
# NOTE: no `from __future__ import annotations` here — slowapi's @limiter.limit
# wrapper cannot resolve postponed annotations because FastAPI evaluates them
# against the wrapper's __globals__, not this module's.
import asyncio
import os
import uuid
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request

from app.config import logger
from app.ratelimit import RATE_LIMIT_LLM, limiter
from app.routers._shared import (
    progress_append,
    progress_complete,
    progress_get,
    progress_init,
    session_dir,
    validate_session_id,
)
from app.schemas import (
    WorkbenchBranchRequest,
    WorkbenchRunRequest,
    WorkbenchValidateRequest,
)
from app.security.auth import check_session_owner
from app.services.compliance import append_audit_event
from app.services.workbench import (
    branch_run,
    create_draft,
    delete_run,
    get_run,
    list_runs,
    promote_run_initiatives,
    run_workbench_run,
    validate_workbench_run,
    workbench_catalog,
)

router = APIRouter()

_WORKBENCH_TIMEOUT_S = int(os.getenv("WORKBENCH_TIMEOUT_SECONDS", "180"))


@router.get("/api/v1/workbench/catalog")
def get_workbench_catalog() -> Dict[str, Any]:
    return workbench_catalog()


@router.post("/api/v1/workbench/validate")
def post_workbench_validate(request: Request, payload: WorkbenchValidateRequest) -> Dict[str, Any]:
    validate_session_id(payload.session_id)
    check_session_owner(request, payload.session_id)
    return validate_workbench_run(payload.selected_skills, payload.session_id, payload.overrides)


@router.post("/api/v1/workbench/preview")
def post_workbench_preview(request: Request, payload: WorkbenchValidateRequest) -> Dict[str, Any]:
    validate_session_id(payload.session_id)
    check_session_owner(request, payload.session_id)
    validation = validate_workbench_run(payload.selected_skills, payload.session_id, payload.overrides)
    n = len(validation["resolved_skills"])
    return {
        **validation,
        "total_skills": n,
        "estimated_duration": f"~{max(10, n * 8)} seconds",
    }


@router.post("/api/v1/workbench/runs")
@limiter.limit(RATE_LIMIT_LLM)
async def post_workbench_run(request: Request, payload: WorkbenchRunRequest) -> Dict[str, Any]:
    validate_session_id(payload.session_id)
    check_session_owner(request, payload.session_id)
    if not session_dir(payload.session_id).exists():
        raise HTTPException(status_code=404, detail="Session not found")
    if not payload.selected_skills:
        raise HTTPException(status_code=400, detail="Select at least one analysis to run")

    run_id = payload.run_id or str(uuid.uuid4())
    progress_init(run_id, payload.session_id)

    draft = create_draft(
        session_id=payload.session_id,
        name=payload.name or "Workbench run",
        selected_skills=payload.selected_skills,
        overrides=payload.overrides,
        seed_from_run_id=payload.seed_from_run_id,
        parent_run_id=payload.parent_run_id,
        engagement_id=payload.engagement_id,
        user_id=payload.user_id,
    )
    draft["run_id"] = run_id

    try:
        result = await asyncio.wait_for(
            run_workbench_run(
                draft,
                progress_callback=lambda phase, msg: progress_append(run_id, phase, msg),
                include_quality_gates=payload.include_quality_gates,
                include_light_reflect=payload.include_light_reflect,
            ),
            timeout=float(_WORKBENCH_TIMEOUT_S),
        )
        progress_complete(run_id, failed=result.get("status") == "failed")
    except asyncio.TimeoutError:
        progress_complete(run_id, failed=True, error="timeout")
        raise HTTPException(status_code=408, detail={"error": "workbench_timeout"})
    except Exception as exc:
        progress_complete(run_id, failed=True, error=str(exc))
        logger.warning('"workbench_run_endpoint_failed run=%s err=%s"', run_id, exc)
        raise
    append_audit_event(f"workbench_run session_id={payload.session_id} run_id={run_id} status={result.get('status')}")
    return result


@router.get("/api/v1/workbench/runs")
def get_workbench_runs(
    request: Request,
    engagement_id: str | None = None,
    session_id: str | None = None,
) -> Dict[str, Any]:
    if session_id:
        validate_session_id(session_id)
        check_session_owner(request, session_id)
    runs = list_runs(engagement_id=engagement_id, session_id=session_id)
    return {"runs": runs}


@router.get("/api/v1/workbench/runs/{run_id}")
def get_workbench_run_detail(request: Request, run_id: str) -> Dict[str, Any]:
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    sid = run.get("session_id")
    if sid:
        check_session_owner(request, str(sid))
    return run


@router.delete("/api/v1/workbench/runs/{run_id}")
def delete_workbench_run(request: Request, run_id: str) -> Dict[str, Any]:
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    sid = run.get("session_id")
    if sid:
        check_session_owner(request, str(sid))
    if not delete_run(run_id):
        raise HTTPException(status_code=404, detail="Run not found")
    append_audit_event(f"workbench_run_deleted run_id={run_id}")
    return {"status": "deleted", "run_id": run_id}


@router.post("/api/v1/workbench/runs/{run_id}/branch")
def post_workbench_branch(run_id: str, payload: WorkbenchBranchRequest) -> Dict[str, Any]:
    draft = branch_run(run_id, name=payload.name)
    if not draft:
        raise HTTPException(status_code=404, detail="Run not found")
    append_audit_event(f"workbench_run_branched parent={run_id} child={draft['run_id']}")
    return draft


@router.get("/api/v1/workbench/progress/{run_id}")
def get_workbench_progress(run_id: str) -> Dict[str, Any]:
    entry = progress_get(run_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Run not found")
    return entry


@router.post("/api/v1/workbench/runs/{run_id}/promote")
def post_workbench_promote(request: Request, run_id: str) -> Dict[str, Any]:
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    check_session_owner(request, run.get("session_id") or "")
    try:
        result = promote_run_initiatives(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    append_audit_event(f"workbench_promoted run_id={run_id} count={result.get('count')}")
    return result
