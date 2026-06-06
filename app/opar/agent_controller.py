"""Agent controller — LLM tool-use loop replacing rule-based planner (M2/M3 primary path)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from app.config import LLM_PROVIDER, logger
from app.opar.agent_runtime import ToolCall, agent_loop_available, run_tool_loop
from app.opar.models import ActResult, ExecutionPlan, ObserveContext
from app.opar.tools.catalog import dispatch_tool_call, get_tool_catalog
from app.opar.tools.context import ToolSessionContext

_AGENT_SYSTEM = """You are a senior FP&A analyst embedded in an OpEx cost intelligence platform.

Your mandate: investigate before concluding. Never surface savings opportunities from thresholds alone.

Workflow:
1. Understand the user's question and what evidence is needed.
2. Use find_skills when unsure which analysis capabilities apply.
3. search_documents for contract/policy/supporting evidence from uploads.
4. run_skill (or query_spend / get_benchmarks / model_savings) for deterministic numbers.
5. get_evidence before claiming initiative readiness.
6. assess_opportunities to pressure-test which gaps are real vs noise.

Rules:
- Deterministic skill outputs are the numeric anchor; if you adjust figures, explain why.
- Prefer specific suppliers, categories, and mechanisms over generic advice.
- When data is missing, say so and suggest what upload would help.
- Finish with a concise analyst summary once you have sufficient evidence.
"""


@dataclass
class AgentRunResult:
    success: bool
    act_result: ActResult | None = None
    exec_plan: ExecutionPlan | None = None
    agent_summary: str = ""
    thinking_text: str | None = None
    agent_trace: List[Dict[str, Any]] | None = None
    fallback_reason: str | None = None


def _build_transport():
    if LLM_PROVIDER == "gemini":
        from app.config import GEMINI_ENABLED

        if GEMINI_ENABLED:
            from app.opar.gemini_client import GeminiToolTransport

            return GeminiToolTransport()
    from app.config import ANTHROPIC_ENABLED

    if ANTHROPIC_ENABLED:
        from app.opar.claude_client import ClaudeToolTransport

        return ClaudeToolTransport()
    return None


def _build_user_message(ctx: ObserveContext) -> str:
    payload = {
        "user_message": ctx.user_message,
        "intent_hint": ctx.intent_class,
        "intent_confidence": ctx.intent_confidence,
        "explicit_category": ctx.explicit_category,
        "query_capabilities": ctx.query_capabilities,
        "data_readiness": {
            "has_tabular_spend": ctx.has_tabular_spend,
            "spend_profile_ready": ctx.spend_profile_ready,
            "has_document_files": ctx.has_document_files,
            "has_annual_revenue": ctx.has_annual_revenue,
            "data_quality_score": ctx.data_quality_score,
        },
        "session_id": ctx.session_id,
        "engagement_id": ctx.engagement_id or ctx.session_id,
    }
    return json.dumps(payload, ensure_ascii=False)


def run_agent_controller(
    ctx: ObserveContext,
    *,
    progress_callback: Callable[[str, str], None] | None = None,
    transport: Any | None = None,
) -> AgentRunResult:
    """Execute the agent tool loop. Returns success=False when caller should fallback."""
    if not agent_loop_available():
        return AgentRunResult(success=False, fallback_reason="agent_loop_unavailable")

    active_transport = transport or _build_transport()
    if active_transport is None:
        return AgentRunResult(success=False, fallback_reason="no_llm_transport")

    session = ToolSessionContext(ctx=ctx)

    def dispatch(call: ToolCall) -> Any:
        if progress_callback:
            progress_callback("act", f"Agent tool: {call.name}")
        return dispatch_tool_call(session, call)

    try:
        loop_result = run_tool_loop(
            system=_AGENT_SYSTEM,
            messages=[{"role": "user", "content": _build_user_message(ctx)}],
            tools=get_tool_catalog(),
            dispatch=dispatch,
            transport=active_transport,
            thinking=True,
        )
    except Exception as exc:
        logger.warning('"agent_controller failed session=%s err=%s"', ctx.session_id, exc)
        return AgentRunResult(success=False, fallback_reason=str(exc)[:200])

    if not session.skill_outputs and not session.opportunity_assessment:
        return AgentRunResult(
            success=False,
            fallback_reason="agent_produced_no_skill_outputs",
            agent_summary=loop_result.final_text,
        )

    # Merge opportunity assessment into savings-modeler output when present
    if session.opportunity_assessment and "savings-modeler" in session.skill_outputs:
        session.skill_outputs["savings-modeler"]["agent_opportunity_assessment"] = session.opportunity_assessment
        opps = session.opportunity_assessment.get("opportunities")
        if opps:
            session.skill_outputs["savings-modeler"]["opportunities"] = opps

    act_result = session.to_act_result()
    exec_plan = session.to_execution_plan()

    return AgentRunResult(
        success=True,
        act_result=act_result,
        exec_plan=exec_plan,
        agent_summary=loop_result.final_text,
        thinking_text=loop_result.thinking_text,
        agent_trace=session.agent_trace,
    )


def try_agent_run(
    ctx: ObserveContext,
    *,
    progress_callback: Callable[[str, str], None] | None = None,
) -> Optional[AgentRunResult]:
    """Attempt agent path; returns None to signal deterministic fallback."""
    result = run_agent_controller(ctx, progress_callback=progress_callback)
    if result.success:
        return result
    logger.info(
        '"agent_fallback session=%s reason=%s"',
        ctx.session_id,
        result.fallback_reason,
    )
    return None
