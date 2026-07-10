"""Ad-hoc SQL over the analytical spend store — the FDE bespoke-analysis surface.

POST /api/v1/query/{session_id}         run one SELECT against the session
                                        engagement's DuckDB catalog (views:
                                        spend, spend_raw, adjustments)
GET  /api/v1/query/{session_id}/schema  columns + sample dimension values for
                                        the editor and the agent tool
GET/POST/DELETE .../saved               saved queries per engagement
GET/DELETE .../history                  execution history per engagement

Safety lives in app/services/spend_store.py (single SELECT/WITH statement,
read-only connection with external access disabled, wrapped LIMIT, interrupt
timeout) — this router only adds ownership checks and the legacy backfill.
"""
# NOTE: no `from __future__ import annotations` here — slowapi's @limiter.limit
# wrapper cannot resolve postponed annotations because FastAPI evaluates them
# against the wrapper's __globals__, not this module's.
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse

from app.config import OUTPUT_DIR
from app.memory import MemoryStore
from app.ratelimit import RATE_LIMIT_LLM, limiter
from app.routers._shared import validate_session_id
from app.schemas import (
    CustomSensitivityRequest,
    NlQueryRequest,
    SavedQueryRequest,
    SavedScenarioSetRequest,
    ScenarioParseRequest,
    SpendQueryRequest,
)
from app.security.auth import check_session_owner
from app.services.compliance import append_audit_event
from app.services.sensitivity import compute_sensitivity
from app.services.spend_schema import load_spend_schema
from app.services.spend_store import SpendQueryError, SpendStoreUnavailable, is_available

router = APIRouter()

_memory = MemoryStore()
_SAVED_SCOPE = "saved_query"
_HISTORY_SCOPE = "query_history"
_SCENARIO_SCOPE = "saved_scenario_set"
_HISTORY_CAP = 50


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


def _saved_key(session_id: str) -> str:
    from app.services.spend_base import _session_engagement_id

    return _session_engagement_id(session_id) or session_id


def _log_history(
    session_id: str,
    *,
    sql: str,
    row_count: int,
    elapsed_ms: float,
    source: str,
    question: Optional[str] = None,
) -> None:
    """Prepend an execution entry to the engagement's query history (cap 50)."""
    key = _saved_key(session_id)
    record = _memory.get(_HISTORY_SCOPE, key) or {}
    entries = list(record.get("entries") or [])
    entry: Dict[str, Any] = {
        "history_id": str(uuid.uuid4()),
        "sql": sql,
        "row_count": row_count,
        "elapsed_ms": round(float(elapsed_ms), 1),
        "source": source,
        "executed_at": datetime.now(timezone.utc).isoformat(),
    }
    if question:
        entry["question"] = question
    entries.insert(0, entry)
    _memory.put(_HISTORY_SCOPE, key, {"entries": entries[:_HISTORY_CAP]})


@router.post("/api/v1/query/{session_id}")
def run_spend_query(
    request: Request,
    session_id: str,
    payload: SpendQueryRequest,
    chart: bool = Query(False, description="Attach a ChartSpec inferred from the result"),
) -> Dict[str, Any]:
    validate_session_id(session_id)
    check_session_owner(request, session_id)
    store = _open_store(session_id)
    try:
        result = store.run_sql(payload.sql, limit=payload.limit or 10_000)
    except SpendQueryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SpendStoreUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _log_history(
        session_id,
        sql=payload.sql,
        row_count=result.row_count,
        elapsed_ms=result.elapsed_ms,
        source="manual",
    )
    append_audit_event(
        f"spend_query session_id={session_id} rows={result.row_count} ms={result.elapsed_ms:.0f}"
    )
    out: Dict[str, Any] = {"session_id": session_id, **result.to_dict()}
    if chart:
        from app.services.query_chart import chart_spec_for_result

        out["chart"] = chart_spec_for_result(result.columns, result.rows)
    return out


@router.post("/api/v1/query/{session_id}/nl2sql")
@limiter.limit(RATE_LIMIT_LLM)
def generate_query_from_nl(
    request: Request, session_id: str, payload: NlQueryRequest
) -> Dict[str, Any]:
    """Translate a natural-language question into reviewed, read-only spend SQL.

    The generated SQL is returned for FDE review (source: rules|llm|unavailable);
    execute=true also runs it through the standard guardrails with the LLM
    repair loop. Provenance-tagged and WORM-audited like every other query.
    """
    validate_session_id(session_id)
    check_session_owner(request, session_id)
    store = _open_store(session_id)
    from app.config import ANTHROPIC_FAST_MODEL
    from app.opar.provenance import build_provenance_tag
    from app.opar.tools.nl_query import generate_sql_from_question
    from app.services.query_chart import chart_spec_for_result

    try:
        out = generate_sql_from_question(
            store,
            payload.question,
            execute=payload.execute,
            model=ANTHROPIC_FAST_MODEL,
        )
    except ValueError as exc:  # includes SpendQueryError (non-SELECT LLM output)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SpendStoreUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    result = out.get("result")
    if payload.execute and isinstance(result, dict) and out.get("sql"):
        _log_history(
            session_id,
            sql=str(out["sql"]),
            row_count=int(result.get("row_count") or 0),
            elapsed_ms=float(result.get("elapsed_ms") or 0),
            source=str(out.get("source") or "unavailable"),
            question=payload.question,
        )
    chart = None
    if isinstance(result, dict) and result.get("rows"):
        chart = chart_spec_for_result(
            result.get("columns") or [],
            result.get("rows") or [],
            payload.question,
            llm_polish=out.get("source") == "llm",
            model=ANTHROPIC_FAST_MODEL,
        )
    provenance = build_provenance_tag(
        ["nl2sql"],
        prompt_text=f"nl2sql:{payload.question}",
        model_version=ANTHROPIC_FAST_MODEL if out.get("source") == "llm" else "deterministic",
    )
    append_audit_event(
        f"nl2sql session_id={session_id} source={out.get('source')} "
        f"prompt_hash={provenance['prompt_hash']} "
        f"rows={(result or {}).get('row_count', 0) if isinstance(result, dict) else 0} "
        f"sql={str(out.get('sql') or '')[:200]!r}"
    )
    return {"session_id": session_id, **out, "chart": chart, "provenance": provenance}


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


# ---------------------------------------------------------------------------
# Query history — one MemoryStore record per engagement (scope "query_history").
# ---------------------------------------------------------------------------


@router.get("/api/v1/query/{session_id}/history")
def list_query_history(request: Request, session_id: str) -> Dict[str, Any]:
    validate_session_id(session_id)
    check_session_owner(request, session_id)
    record = _memory.get(_HISTORY_SCOPE, _saved_key(session_id)) or {}
    return {"entries": record.get("entries") or []}


@router.delete("/api/v1/query/{session_id}/history")
def clear_query_history(request: Request, session_id: str) -> Dict[str, Any]:
    validate_session_id(session_id)
    check_session_owner(request, session_id)
    _memory.put(_HISTORY_SCOPE, _saved_key(session_id), {"entries": []})
    return {"status": "cleared"}


@router.post("/api/v1/sensitivity/parse")
@limiter.limit(RATE_LIMIT_LLM)
def parse_sensitivity_question(
    request: Request, payload: ScenarioParseRequest
) -> Dict[str, Any]:
    """Parse a natural-language what-if question into reviewable scenario specs.

    Never runs anything — the FDE reviews the prefilled scenarios in the UI and
    triggers /sensitivity/custom explicitly (review gate). LLM-primary with the
    regex fast-path as offline fallback (parse_source reports which one fired).
    """
    validate_session_id(payload.session_id)
    check_session_owner(request, payload.session_id)
    from app.opar.models import ObserveContext
    from app.opar.tools.context import ToolSessionContext
    from app.opar.tools.scenario_parser import parse_what_if_request

    from app.services.spend_base import _session_engagement_id

    analysis = _memory.get("session", payload.session_id) or {}
    engagement_id = (
        (analysis.get("manifest") or {}).get("engagement_id")
        or analysis.get("engagement_id")
        or _session_engagement_id(payload.session_id)
        or ""
    )
    ctx = ObserveContext(
        user_message=payload.question,
        session_id=payload.session_id,
        engagement_id=engagement_id,
    )
    session = ToolSessionContext(ctx=ctx)
    session.skill_outputs = dict(analysis.get("skill_outputs") or {})
    session.manifest = dict(analysis.get("manifest") or {})

    out = parse_what_if_request(session, payload.question)
    append_audit_event(
        f"whatif_parse session_id={payload.session_id} source={out.get('parse_source')} "
        f"scenarios={len(out.get('scenarios') or [])} q={payload.question[:80]!r}"
    )
    return out


@router.post("/api/v1/sensitivity/custom")
def run_custom_sensitivity(request: Request, payload: CustomSensitivityRequest) -> Dict[str, Any]:
    """Run sensitivity with user-defined what-if scenarios."""
    validate_session_id(payload.session_id)
    check_session_owner(request, payload.session_id)
    analysis = _memory.get("session", payload.session_id) or {}
    bridge = (analysis.get("skill_outputs") or {}).get("value-bridge-calculator")
    savings_model = (analysis.get("skill_outputs") or {}).get("savings-modeler")
    if not bridge:
        from app.services.workbench import latest_bridge_from_workbench

        wb_bridge, wb_savings = latest_bridge_from_workbench(payload.session_id)
        bridge = wb_bridge
        savings_model = savings_model or wb_savings
    if not bridge:
        raise HTTPException(status_code=422, detail="Run value-bridge-calculator first")
    for scen in payload.scenarios:
        target = (scen.target or "portfolio").strip().lower()
        if target not in ("portfolio", "category", "lever"):
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Unsupported scenario target '{scen.target}'. "
                    "Only 'portfolio', 'category', and 'lever' are supported."
                ),
            )
    manifest = analysis.get("manifest") or {}
    if not manifest:
        from app.routers._shared import read_manifest

        try:
            manifest = read_manifest(payload.session_id) or {}
        except Exception:
            manifest = {}
    custom = [s.model_dump() for s in payload.scenarios]
    result = compute_sensitivity(
        bridge,
        savings_model=savings_model,
        discount_rate=float(payload.discount_rate or manifest.get("wacc") or 0.10),
        effective_tax_rate=float(
            payload.effective_tax_rate or manifest.get("effective_tax_rate") or 0.0
        ),
        drivers=payload.drivers or None,
        custom_scenarios=custom,
    )
    from app.opar.sensitivity_narrative import synthesize_sensitivity_narrative

    currency = str(manifest.get("currency") or analysis.get("reporting_currency") or "INR")
    result["narrative"] = synthesize_sensitivity_narrative(
        result,
        currency=currency,
        scenario_labels=[s.name for s in payload.scenarios],
    )
    return result



# ---------------------------------------------------------------------------
# Saved scenario sets — MemoryStore scope "saved_scenario_set".
# ---------------------------------------------------------------------------


@router.get("/api/v1/sensitivity/{session_id}/saved")
def list_saved_scenario_sets(request: Request, session_id: str) -> Dict[str, Any]:
    validate_session_id(session_id)
    check_session_owner(request, session_id)
    record = _memory.get(_SCENARIO_SCOPE, _saved_key(session_id)) or {}
    return {"sets": record.get("sets") or []}


@router.post("/api/v1/sensitivity/{session_id}/saved")
def save_scenario_set(
    request: Request, session_id: str, payload: SavedScenarioSetRequest
) -> Dict[str, Any]:
    validate_session_id(session_id)
    check_session_owner(request, session_id)
    if not payload.scenarios:
        raise HTTPException(status_code=422, detail="At least one scenario is required")
    for scen in payload.scenarios:
        target = (scen.target or "portfolio").strip().lower()
        if target not in ("portfolio", "category", "lever"):
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Unsupported scenario target '{scen.target}'. "
                    "Only 'portfolio', 'category', and 'lever' are supported."
                ),
            )
    key = _saved_key(session_id)
    record = _memory.get(_SCENARIO_SCOPE, key) or {}
    sets = [s for s in (record.get("sets") or []) if s.get("name") != payload.name]
    entry = {
        "set_id": str(uuid.uuid4()),
        "name": payload.name,
        "description": payload.description or "",
        "scenarios": [s.model_dump() for s in payload.scenarios],
        "drivers": payload.drivers or {},
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    sets.append(entry)
    _memory.put(_SCENARIO_SCOPE, key, {"sets": sets})
    append_audit_event(
        f"scenario_set_saved session_id={session_id} name={payload.name!r} "
        f"scenarios={len(payload.scenarios)}"
    )
    return entry


@router.delete("/api/v1/sensitivity/{session_id}/saved/{set_id}")
def delete_saved_scenario_set(
    request: Request, session_id: str, set_id: str
) -> Dict[str, Any]:
    validate_session_id(session_id)
    check_session_owner(request, session_id)
    key = _saved_key(session_id)
    record = _memory.get(_SCENARIO_SCOPE, key) or {}
    sets = record.get("sets") or []
    remaining = [s for s in sets if s.get("set_id") != set_id]
    if len(remaining) == len(sets):
        raise HTTPException(status_code=404, detail="Saved scenario set not found")
    _memory.put(_SCENARIO_SCOPE, key, {"sets": remaining})
    append_audit_event(f"scenario_set_deleted session_id={session_id} set_id={set_id}")
    return {"status": "deleted", "set_id": set_id}


@router.get("/api/v1/engagements/{engagement_id}/export")
def export_spend_data(
    request: Request,
    engagement_id: str,
    session_id: str = Query(..., description="Session that owns the spend store"),
    fmt: str = Query("csv", pattern="^(csv|parquet|xlsx)$"),
    sql: Optional[str] = Query(None, description="SELECT to export; default exports all spend lines"),
    query_id: Optional[str] = Query(None, description="Saved query id to export"),
    limit: int = Query(1_000_000, le=1_000_000),
) -> FileResponse:
    """Stream raw spend export via DuckDB materialization."""
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
