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
    description="Read spend-profiler output: totals, categories, suppliers. Runs profiler if needed.",
    input_schema={
        "type": "object",
        "properties": {
            "category": {"type": "string", "description": "Optional category filter."},
        },
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


def _query_spend(session: ToolSessionContext, args: Dict[str, Any]) -> Dict[str, Any]:
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
    return out


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
