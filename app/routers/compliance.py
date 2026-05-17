from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from app.routers._shared import _memory
from app.services.compliance import (
    append_audit_event,
    ensure_risk_register,
    privacy_controls_summary,
)

router = APIRouter()


@router.get("/api/compliance/risk-register")
@router.get("/api/v1/compliance/risk-register")
def get_risk_register() -> Dict[str, str]:
    path = ensure_risk_register()
    return {"path": str(path), "content": path.read_text(encoding="utf-8")}


@router.get("/api/compliance/privacy-controls")
@router.get("/api/v1/compliance/privacy-controls")
def get_privacy_controls() -> Dict[str, str]:
    return privacy_controls_summary()


@router.get("/api/compliance/audit-log/verify")
@router.get("/api/v1/compliance/audit-log/verify")
def verify_audit_log_integrity() -> Dict[str, Any]:
    from app.services.compliance import verify_audit_log
    return verify_audit_log()


@router.get("/api/compliance/audit-log")
@router.get("/api/v1/compliance/audit-log")
def list_compliance_audit_log(limit: int = 50) -> Dict[str, Any]:
    from app.services.compliance import list_audit_events, verify_audit_log
    capped = max(1, min(limit, 200))
    return {
        "entries": list_audit_events(limit=capped),
        "integrity": verify_audit_log(),
    }


@router.delete("/api/memory/{scope}/{key}")
@router.delete("/api/v1/memory/{scope}/{key}")
def delete_memory(scope: str, key: str) -> Dict[str, str]:
    if scope not in {"user", "session", "agent"}:
        raise HTTPException(status_code=400, detail="Invalid scope")
    if "/" in key or "\\" in key or ".." in key:
        raise HTTPException(status_code=400, detail="Invalid key")
    _memory.delete(scope, key)
    append_audit_event(f"memory_deleted scope={scope} key={key}")
    return {"status": "deleted", "scope": scope, "key": key}


@router.delete("/api/v1/engagement/{engagement_id}")
def teardown_engagement(engagement_id: str) -> Dict[str, Any]:
    if not engagement_id or "/" in engagement_id or ".." in engagement_id:
        raise HTTPException(status_code=400, detail="Invalid engagement_id")
    from app.opar.memory_adapter import get_memory_adapter
    adapter = get_memory_adapter()
    result = adapter.teardown_engagement(engagement_id)
    receipt: Dict[str, Any] = {
        "engagement_id": engagement_id,
        "status": "purged",
        "attested_at": datetime.now(timezone.utc).isoformat(),
        "deleted_scopes": result.get("deleted_scopes", []),
        "records_deleted": result.get("records_deleted", 0),
    }
    append_audit_event(
        f"engagement_teardown engagement_id={engagement_id} records_deleted={receipt['records_deleted']}",
        data=receipt,
    )
    return receipt
