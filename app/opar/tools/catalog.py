"""Agent tool catalog — thin wrappers over existing platform capabilities."""
from __future__ import annotations

from typing import Any, Dict, List

from app.opar.agent_runtime import ToolCall, ToolDefinition
from app.opar.tools.context import ToolSessionContext

SEARCH_DOCUMENTS_TOOL = ToolDefinition(
    name="search_documents",
    description=(
        "Semantic search over uploaded engagement documents (contracts, policies, "
        "presentations). Returns labelled excerpts with provenance."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Natural-language search query."},
            "top_k": {"type": "integer", "description": "Max chunks to return (default 8)."},
        },
        "required": ["query"],
    },
)

FIND_SKILLS_TOOL = ToolDefinition(
    name="find_skills",
    description=(
        "Discover analysis skills relevant to the user's question. "
        "Use before run_skill when unsure which capabilities apply."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Describe the analytical task."},
            "k": {"type": "integer", "description": "Number of skills to return (default 5)."},
        },
        "required": ["query"],
    },
)

RUN_SKILL_TOOL = ToolDefinition(
    name="run_skill",
    description=(
        "Execute a deterministic analysis skill. Prerequisites auto-run via the "
        "canonical dependency map. Returns compact JSON output."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Skill name, e.g. spend-profiler."},
            "args": {
                "type": "object",
                "description": "Optional skill-specific arguments (usually empty).",
            },
        },
        "required": ["name"],
    },
)

QUERY_SPEND_TOOL = ToolDefinition(
    name="query_spend",
    description=(
        "Run a read-only SQL SELECT against the session's spend store (DuckDB view `spend`). "
        "Columns include: supplier, category_id, category_name, amount, period, business_unit, "
        "gl_code, cost_center_id, currency, description. "
        "Views: spend (effective lines), spend_raw (as-ingested), adjustments. "
        "Use for bespoke cuts — top vendors by category, QoQ trends, BU rollups. "
        "Provide a full SELECT; omit sql only for a default top-categories summary."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "sql": {
                "type": "string",
                "description": "Single SELECT or WITH…SELECT against view `spend`.",
            },
            "limit": {
                "type": "integer",
                "description": "Max rows to return (default 500, cap 10000).",
            },
            "category": {
                "type": "string",
                "description": "Legacy filter — used only when SQL is omitted and store unavailable.",
            },
        },
    },
)

SAVE_QUERY_RESULT_TOOL = ToolDefinition(
    name="save_query_result",
    description=(
        "Execute a SELECT and save results as a downloadable CSV under /api/v1/exports/. "
        "Use after query_spend when the user wants an export artifact."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "sql": {"type": "string", "description": "SELECT to export."},
            "filename": {
                "type": "string",
                "description": "Base filename without extension (default: query_export).",
            },
        },
        "required": ["sql"],
    },
)

GET_BENCHMARKS_TOOL = ToolDefinition(
    name="get_benchmarks",
    description="Read peer/internal benchmark gaps. Runs benchmarker skills if needed.",
    input_schema={"type": "object", "properties": {}},
)

GET_EVIDENCE_TOOL = ToolDefinition(
    name="get_evidence",
    description="Read document evidence gathered for modeled savings initiatives.",
    input_schema={
        "type": "object",
        "properties": {
            "category": {"type": "string", "description": "Optional category filter."},
        },
    },
)

MODEL_SAVINGS_TOOL = ToolDefinition(
    name="model_savings",
    description=(
        "Run deterministic savings-modeler (NPV, payback, phasing). "
        "Numbers are audit-anchored; use assess_opportunities for judgment."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "category": {"type": "string", "description": "Optional category focus."},
        },
    },
)

ASSESS_OPPORTUNITIES_TOOL = ToolDefinition(
    name="assess_opportunities",
    description=(
        "Reason over benchmark gaps, root-cause signals, and document evidence to "
        "identify real vs noise opportunities. May adjust figures with provenance tags."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "focus_category": {"type": "string", "description": "Optional category to focus on."},
            "notes": {"type": "string", "description": "Analytical hypothesis or user context."},
        },
    },
)

ALL_TOOLS: List[ToolDefinition] = [
    SEARCH_DOCUMENTS_TOOL,
    FIND_SKILLS_TOOL,
    RUN_SKILL_TOOL,
    QUERY_SPEND_TOOL,
    SAVE_QUERY_RESULT_TOOL,
    GET_BENCHMARKS_TOOL,
    GET_EVIDENCE_TOOL,
    MODEL_SAVINGS_TOOL,
    ASSESS_OPPORTUNITIES_TOOL,
]

_TOOL_BY_NAME = {t.name: t for t in ALL_TOOLS}


def get_tool_catalog() -> List[ToolDefinition]:
    return list(ALL_TOOLS)


def dispatch_tool_call(session: ToolSessionContext, call: ToolCall) -> Any:
    """Route a tool call to its handler."""
    handlers = {
        "search_documents": _search_documents,
        "find_skills": _find_skills,
        "run_skill": _run_skill,
        "query_spend": _query_spend,
        "save_query_result": _save_query_result,
        "get_benchmarks": _get_benchmarks,
        "get_evidence": _get_evidence,
        "model_savings": _model_savings,
        "assess_opportunities": _assess_opportunities,
    }
    handler = handlers.get(call.name)
    if not handler:
        raise ValueError(f"Unknown tool: {call.name}")
    result = handler(session, call.arguments)
    session.agent_trace.append({"tool": call.name, "arguments": call.arguments, "ok": True})
    return result


def _search_documents(session: ToolSessionContext, args: Dict[str, Any]) -> Dict[str, Any]:
    from app.services.document_index import retrieve_context

    query = str(args.get("query") or "").strip()
    if not query:
        return {"blocks": [], "count": 0}
    blocks = retrieve_context(session.engagement_id, query, top_k=int(args.get("top_k") or 8))
    return {"blocks": blocks[:8], "count": len(blocks)}


def _find_skills(session: ToolSessionContext, args: Dict[str, Any]) -> Dict[str, Any]:
    from app.skills.discovery import discover_relevant_skills

    query = str(args.get("query") or session.user_message).strip()
    k = int(args.get("k") or 5)
    matches = discover_relevant_skills(query, k=k)
    return {"skills": matches}


def _run_skill(session: ToolSessionContext, args: Dict[str, Any]) -> Dict[str, Any]:
    name = str(args.get("name") or "").strip()
    if not name:
        raise ValueError("run_skill requires name")
    return session.invoke_skill(name)


def _open_agent_store(session: ToolSessionContext):
    from app.services.spend_base import ensure_spend_store_synced

    return ensure_spend_store_synced(session.session_id)


def _query_spend(session: ToolSessionContext, args: Dict[str, Any]) -> Dict[str, Any]:
    sql = (args.get("sql") or "").strip()
    limit = int(args.get("limit") or 500)
    store = _open_agent_store(session)
    if store is not None:
        if not sql:
            sql = (
                "SELECT category_name, SUM(amount) AS spend, COUNT(*) AS lines "
                "FROM spend GROUP BY category_name ORDER BY spend DESC"
            )
        from app.services.spend_store import SpendQueryError

        try:
            result = store.run_sql(sql, limit=limit)
            return {"sql": sql, **result.to_dict()}
        except SpendQueryError as exc:
            return {"sql": sql, "error": str(exc), "rows": []}
    # Fallback: spend-profiler path when store unavailable
    out = session.invoke_skill("spend-profiler")
    category = (args.get("category") or "").strip()
    if category and isinstance(out.get("top_categories"), list):
        filtered = [
            c
            for c in out["top_categories"]
            if category.lower() in str(c.get("category_name", "")).lower()
            or category.lower() in str(c.get("category_id", "")).lower()
        ]
        out["filtered_categories"] = filtered
    out["fallback"] = "spend-profiler"
    return out


def _save_query_result(session: ToolSessionContext, args: Dict[str, Any]) -> Dict[str, Any]:
    import re
    import uuid

    from app.config import OUTPUT_DIR

    sql = (args.get("sql") or "").strip()
    if not sql:
        raise ValueError("save_query_result requires sql")
    store = _open_agent_store(session)
    if store is None:
        raise RuntimeError("No spend store available for export")
    base = re.sub(r"[^\w\-]+", "_", (args.get("filename") or "query_export").strip())[:80]
    filename = f"{base}_{uuid.uuid4().hex[:8]}.csv"
    path = OUTPUT_DIR / filename
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    row_count = store.export_sql(sql, path, fmt="csv")
    return {
        "filename": filename,
        "download_url": f"/api/v1/exports/{filename}",
        "row_count": row_count,
        "format": "csv",
    }


def _get_benchmarks(session: ToolSessionContext, args: Dict[str, Any]) -> Dict[str, Any]:
    peer = session.invoke_skill("peer-benchmarker")
    internal = session.invoke_skill("internal-benchmarker")
    return {"peer": peer, "internal": internal}


def _get_evidence(session: ToolSessionContext, args: Dict[str, Any]) -> Dict[str, Any]:
    session.invoke_skill("savings-modeler")
    return session.invoke_skill("evidence-gatherer")


def _model_savings(session: ToolSessionContext, args: Dict[str, Any]) -> Dict[str, Any]:
    session.invoke_skill("peer-benchmarker")
    session.invoke_skill("internal-benchmarker")
    session.invoke_skill("root-cause-analyzer")
    return session.invoke_skill("savings-modeler")


def _assess_opportunities(session: ToolSessionContext, args: Dict[str, Any]) -> Dict[str, Any]:
    from app.opar.tools.opportunity_reasoning import assess_opportunities_with_llm

    _model_savings(session, args)
    session.invoke_skill("evidence-gatherer")
    assessment = assess_opportunities_with_llm(session, focus_category=args.get("focus_category"), notes=args.get("notes"))
    session.opportunity_assessment = assessment
    return assessment
