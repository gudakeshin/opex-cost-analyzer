from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from app.schemas import (
    ActualsCreateRequest,
    InitiativeCreateRequest,
    InitiativeRejectRequest,
    InitiativeStageRequest,
    MilestoneCreateRequest,
)
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
    return actual


@router.get("/api/v1/pipeline/summary")
def get_pipeline_summary(user_id: str | None = None) -> Dict[str, Any]:
    return pipeline_summary(user_id=user_id)


@router.get("/api/v1/pipeline/at-risk")
def get_pipeline_at_risk(user_id: str | None = None) -> Dict[str, Any]:
    return {"at_risk": at_risk_initiatives(user_id=user_id)}
