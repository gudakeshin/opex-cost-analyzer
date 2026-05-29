from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from app.config import logger
from app.schemas import (
    ActualsCreateRequest,
    InitiativeCreateRequest,
    InitiativeRejectRequest,
    InitiativeStageRequest,
    MilestoneCreateRequest,
    RealisedSavingsIngestRequest,
)
from app.services.calibration import generate_calibration_report, ingest_realised_savings
from app.services.compliance import append_audit_event
from app.services.pipeline import (
    add_actual,
    add_milestone,
    at_risk_initiatives,
    create_initiative,
    get_milestones,
    list_initiatives,
    pipeline_summary,
    reject_initiative,
    update_initiative_stage,
)

router = APIRouter()


def _forward_actual_to_calibration(initiative_id: str, actual: Dict[str, Any]) -> None:
    """Best-effort: feed a recorded actual into the calibration loop.

    Never blocks actuals recording — calibration is an optional analytics
    downstream. Amounts are stored absolute; the calibration model expects Crore
    (₹), so we scale by 1e7. pack_id/lever may be empty on legacy initiatives,
    in which case realisation-rate tracking still works but pack version-bump
    proposals are skipped by the calibration engine.
    """
    try:
        match = next((i for i in list_initiatives() if i.get("initiative_id") == initiative_id), None)
        if not match:
            return
        engagement_id = match.get("engagement_id") or match.get("session_id") or match.get("analysis_id")
        if not engagement_id:
            return
        ingest_realised_savings(engagement_id, [{
            "engagement_id": engagement_id,
            "initiative_id": initiative_id,
            "lever_id": match.get("lever") or "",
            "pack_id": match.get("pack_id") or "",
            "planned_p50_cr": float(actual.get("committed_savings") or 0.0) / 1e7,
            "realised_cr": float(actual.get("actual_savings") or 0.0) / 1e7,
            "realised_date": actual.get("period") or actual.get("created_at") or "",
            "data_source": "self_reported",
        }])
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug('"calibration_forward_skipped initiative_id=%s error=%s"', initiative_id, exc)


@router.get("/api/v1/initiatives")
def get_initiatives(
    user_id: str | None = None,
    stage: str | None = None,
    category: str | None = None,
    lever: str | None = None,
) -> Dict[str, Any]:
    return {"initiatives": list_initiatives(user_id=user_id, stage=stage, category=category, lever=lever)}


@router.post("/api/v1/initiatives")
def create_pipeline_initiative(payload: InitiativeCreateRequest) -> Dict[str, Any]:
    initiative = create_initiative(payload.model_dump())
    append_audit_event(f"initiative_created id={initiative['initiative_id']}")
    return initiative


@router.put("/api/v1/initiatives/{initiative_id}/stage")
def set_initiative_stage(initiative_id: str, payload: InitiativeStageRequest) -> Dict[str, Any]:
    initiative = update_initiative_stage(initiative_id, payload.stage)
    if not initiative:
        raise HTTPException(status_code=404, detail="Initiative not found or invalid stage")
    append_audit_event(f"initiative_stage_updated id={initiative_id} stage={payload.stage}")
    return initiative


@router.put("/api/v1/initiatives/{initiative_id}/reject")
def reject_pipeline_initiative(initiative_id: str, payload: InitiativeRejectRequest) -> Dict[str, Any]:
    if not payload.reason.strip():
        raise HTTPException(status_code=400, detail="Rejection reason is required")
    initiative = reject_initiative(initiative_id, payload.reason.strip())
    if not initiative:
        raise HTTPException(status_code=404, detail="Initiative not found")
    append_audit_event(f"initiative_rejected id={initiative_id}")
    return initiative


@router.get("/api/v1/initiatives/{initiative_id}/milestones")
def list_initiative_milestones(initiative_id: str) -> Dict[str, Any]:
    return {"initiative_id": initiative_id, "milestones": get_milestones(initiative_id)}


@router.post("/api/v1/initiatives/{initiative_id}/milestones")
def create_initiative_milestone(initiative_id: str, payload: MilestoneCreateRequest) -> Dict[str, Any]:
    milestone = add_milestone(initiative_id, payload.model_dump())
    append_audit_event(f"initiative_milestone_created initiative_id={initiative_id}")
    return milestone


@router.post("/api/v1/initiatives/{initiative_id}/actuals")
def create_initiative_actuals(initiative_id: str, payload: ActualsCreateRequest) -> Dict[str, Any]:
    actual = add_actual(initiative_id, payload.model_dump())
    append_audit_event(f"initiative_actuals_created initiative_id={initiative_id}")
    _forward_actual_to_calibration(initiative_id, actual)
    return actual


@router.post("/api/v1/calibration/{engagement_id}/realised")
def ingest_calibration_realised(engagement_id: str, payload: RealisedSavingsIngestRequest) -> Dict[str, Any]:
    if "/" in engagement_id or "\\" in engagement_id or ".." in engagement_id:
        raise HTTPException(status_code=400, detail="Invalid engagement_id")
    result = ingest_realised_savings(engagement_id, payload.records)
    append_audit_event(f"calibration_realised_ingested engagement={engagement_id} records={result.get('records_ingested', 0)}")
    return result


@router.get("/api/v1/calibration/{engagement_id}/report")
def get_calibration_report(engagement_id: str) -> Dict[str, Any]:
    if "/" in engagement_id or "\\" in engagement_id or ".." in engagement_id:
        raise HTTPException(status_code=400, detail="Invalid engagement_id")
    return generate_calibration_report(engagement_id).to_dict()


@router.get("/api/v1/pipeline/summary")
def get_pipeline_summary(user_id: str | None = None) -> Dict[str, Any]:
    return pipeline_summary(user_id=user_id)


@router.get("/api/v1/pipeline/at-risk")
def get_pipeline_at_risk(user_id: str | None = None) -> Dict[str, Any]:
    return {"at_risk": at_risk_initiatives(user_id=user_id)}
