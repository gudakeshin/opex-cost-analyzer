"""Ad-hoc SQL over the analytical spend store — the FDE bespoke-analysis surface.

POST /api/v1/query/{session_id}         run one SELECT against the session
                                        engagement's DuckDB catalog (views:
                                        spend, spend_raw, adjustments)
GET  /api/v1/query/{session_id}/schema  columns + sample dimension values for
                                        the editor and the agent tool
GET/POST/DELETE .../saved               saved queries per engagement

Safety lives in app/services/spend_store.py (single SELECT/WITH statement,
read-only connection with external access disabled, wrapped LIMIT, interrupt
timeout) — this router only adds ownership checks and the legacy backfill.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse

from app.config import OUTPUT_DIR
from app.memory import MemoryStore
from app.routers._shared import validate_session_id
from app.schemas import CustomSensitivityRequest, SavedQueryRequest, SpendQueryRequest
from app.security.auth import check_session_owner
from app.services.compliance import append_audit_event
from app.services.sensitivity import compute_sensitivity
from app.services.spend_schema import load_spend_schema
from app.services.spend_store import SpendQueryError, SpendStoreUnavailable, is_available

router = APIRouter()

_memory = MemoryStore()
_SAVED_SCOPE = "saved_query"


def _open_store(session_id: str):
    """Resolve the session's SpendStore, backfilling legacy sessions once."""
    if not is_available():
        raise HTTPException(
            status_code=501,
            detail="Ad-hoc queries need the duckdb/pyarrow spend store (pip install duckdb pyarrow)",
        )
    from app.services.spend_base import ensure_spend_store_synced

    store = ensure_spend_store_synced(session_id)
    if store is None:
        raise HTTPException(
            status_code=404,
            detail="No spend data indexed for this session — upload a spend file first",
        )
    return store


@router.post("/api/v1/query/{session_id}")
def run_spend_query(request: Request, session_id: str, payload: SpendQueryRequest) -> Dict[str, Any]:
    validate_session_id(session_id)
    check_session_owner(request, session_id)
    store = _open_store(session_id)
    try:
        result = store.run_sql(payload.sql, limit=payload.limit or 10_000)
    except SpendQueryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SpendStoreUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    append_audit_event(
        f"spend_query session_id={session_id} rows={result.row_count} ms={result.elapsed_ms:.0f}"
    )
    return {"session_id": session_id, **result.to_dict()}


@router.get("/api/v1/query/{session_id}/schema")
def get_spend_schema(request: Request, session_id: str) -> Dict[str, Any]:
    """Queryable views, their columns, and sample dimension values."""
    validate_session_id(session_id)
    check_session_owner(request, session_id)
    store = _open_store(session_id)
    payload = load_spend_schema(store)
    return {"session_id": session_id, **payload}


# ---------------------------------------------------------------------------
# Saved queries — one MemoryStore record per engagement (scope "saved_query").
# ---------------------------------------------------------------------------

def _saved_key(session_id: str) -> str:
    from app.services.spend_base import _session_engagement_id

    return _session_engagement_id(session_id) or session_id


@router.get("/api/v1/query/{session_id}/saved")
def list_saved_queries(request: Request, session_id: str) -> Dict[str, Any]:
    validate_session_id(session_id)
    check_session_owner(request, session_id)
    record = _memory.get(_SAVED_SCOPE, _saved_key(session_id)) or {}
    return {"queries": record.get("queries") or []}


@router.post("/api/v1/query/{session_id}/saved")
def save_query(request: Request, session_id: str, payload: SavedQueryRequest) -> Dict[str, Any]:
    validate_session_id(session_id)
    check_session_owner(request, session_id)
    from app.services.spend_store import validate_readonly_sql

    try:
        validate_readonly_sql(payload.sql)
    except SpendQueryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    key = _saved_key(session_id)
    record = _memory.get(_SAVED_SCOPE, key) or {}
    queries = [q for q in (record.get("queries") or []) if q.get("name") != payload.name]
    entry = {
        "query_id": str(uuid.uuid4()),
        "name": payload.name,
        "sql": payload.sql,
        "description": payload.description or "",
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    queries.append(entry)
    _memory.put(_SAVED_SCOPE, key, {"queries": queries})
    return entry


@router.delete("/api/v1/query/{session_id}/saved/{query_id}")
def delete_saved_query(request: Request, session_id: str, query_id: str) -> Dict[str, Any]:
    validate_session_id(session_id)
    check_session_owner(request, session_id)
    key = _saved_key(session_id)
    record = _memory.get(_SAVED_SCOPE, key) or {}
    queries = record.get("queries") or []
    remaining = [q for q in queries if q.get("query_id") != query_id]
    if len(remaining) == len(queries):
        raise HTTPException(status_code=404, detail="Saved query not found")
    _memory.put(_SAVED_SCOPE, key, {"queries": remaining})
    return {"status": "deleted", "query_id": query_id}


@router.post("/api/v1/sensitivity/custom")
def run_custom_sensitivity(request: Request, payload: CustomSensitivityRequest) -> Dict[str, Any]:
    """Run sensitivity with user-defined what-if scenarios."""
    validate_session_id(payload.session_id)
    check_session_owner(request, payload.session_id)
    analysis = _memory.get("session", payload.session_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="No analysis for session")
    bridge = analysis.get("skill_outputs", {}).get("value-bridge-calculator")
    if not bridge:
        raise HTTPException(status_code=422, detail="Run value-bridge-calculator first")
    savings_model = analysis.get("skill_outputs", {}).get("savings-modeler")
    manifest = analysis.get("manifest") or {}
    custom = [s.model_dump() for s in payload.scenarios]
    return compute_sensitivity(
        bridge,
        savings_model=savings_model,
        discount_rate=float(payload.discount_rate or manifest.get("wacc") or 0.10),
        effective_tax_rate=float(
            payload.effective_tax_rate or manifest.get("effective_tax_rate") or 0.0
        ),
        custom_scenarios=custom,
    )


@router.get("/api/v1/engagements/{engagement_id}/export")
def export_spend_data(
    request: Request,
    engagement_id: str,
    session_id: str = Query(..., description="Session that owns the spend store"),
    fmt: str = Query("csv", pattern="^(csv|parquet|xlsx)$"),
    sql: str | None = Query(None, description="SELECT to export; default exports all spend lines"),
    query_id: str | None = Query(None, description="Saved query id to export"),
    limit: int = Query(1_000_000, le=1_000_000),
) -> FileResponse:
    """Stream raw spend export via DuckDB materialization."""
    import uuid

    validate_session_id(session_id)
    check_session_owner(request, session_id)
    store = _open_store(session_id)
    export_sql = (sql or "").strip()
    if query_id:
        key = _saved_key(session_id)
        record = _memory.get(_SAVED_SCOPE, key) or {}
        match = next((q for q in (record.get("queries") or []) if q.get("query_id") == query_id), None)
        if not match:
            raise HTTPException(status_code=404, detail="Saved query not found")
        export_sql = match["sql"]
    if not export_sql:
        export_sql = "SELECT * FROM spend"
    ext = fmt if fmt != "xlsx" else "csv"
    filename = f"spend_export_{engagement_id[:8]}_{uuid.uuid4().hex[:8]}.{ext}"
    path = OUTPUT_DIR / filename
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        row_count = store.export_sql(export_sql, path, fmt=ext, limit=limit)
    except SpendQueryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if fmt == "xlsx" and row_count > 0:
        try:
            import pandas as pd

            xlsx_path = path.with_suffix(".xlsx")
            pd.read_csv(path).to_excel(xlsx_path, index=False)
            path.unlink(missing_ok=True)
            path = xlsx_path
            filename = xlsx_path.name
        except ImportError:
            pass
    append_audit_event(
        f"spend_export engagement_id={engagement_id} rows={row_count} fmt={fmt}"
    )
    media = {
        "csv": "text/csv",
        "parquet": "application/octet-stream",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }.get(fmt, "application/octet-stream")
    return FileResponse(path, filename=filename, media_type=media)
