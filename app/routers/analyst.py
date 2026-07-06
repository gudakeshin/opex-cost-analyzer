"""Analyst mode — multi-turn agent tool loop for bespoke workbench analysis.

POST /api/v1/analyst/{session_id}/run     one agent turn: the LLM investigates
                                          via the tool catalog (query_spend,
                                          run_skill, run_sensitivity, …) and
                                          answers with a provenance-tagged
                                          summary; progress streams through the
                                          same store the Compose tab polls
GET  /api/v1/analyst/{session_id}/history persisted turns per engagement

Bounds live in config (AGENT_MAX_TOOL_ITERATIONS, AGENT_TOOL_TIMEOUT_SECONDS,
ANALYST_TIMEOUT_SECONDS). When no LLM transport is available the endpoint
degrades to one deterministic natural-language query so the FDE still gets a
table (available=false + fallback reason).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.memory import MemoryStore
from app.routers._shared import (
    progress_append,
    progress_append_thinking,
    progress_complete,
    progress_init,
    validate_session_id,
)
from app.security.auth import check_session_owner
from app.services.compliance import append_audit_event

router = APIRouter()

_memory = MemoryStore()
_TURN_SCOPE = "analyst_turn"
_MAX_TURNS_KEPT = 50


class AnalystRunRequest(BaseModel):
    run_id: str
    question: str


def _turn_key(session_id: str) -> str:
    from app.services.spend_base import _session_engagement_id

    return _session_engagement_id(session_id) or session_id


def _build_context(session_id: str, question: str):
    """Full ObserveContext via the same observe() pipeline chat uses — this is
    what populates has_tabular_spend/spend_profile_ready/data_quality_score
    from the session's actual manifest and memory, so the agent doesn't
    wrongly conclude "no data uploaded" for a session that already has an
    indexed spend store."""
    from app.opar.observe import observe

    analysis = _memory.get("session", session_id) or {}
    ctx = observe(question, session_id, user_id="default")
    return ctx, analysis


def _deterministic_fallback(session_id: str, question: str, analysis: Dict[str, Any]) -> Dict[str, Any] | None:
    """LLM-free degradation: one rule-based NL query so the FDE still gets data."""
    from app.opar.tools.context import ToolSessionContext
    from app.opar.tools.nl_query import run_natural_language_query

    ctx, _ = _build_context(session_id, question)
    session = ToolSessionContext(ctx=ctx)
    session.skill_outputs = dict(analysis.get("skill_outputs") or {})
    session.manifest = dict(analysis.get("manifest") or {})
    try:
        return run_natural_language_query(session, question=question)
    except Exception:
        return None


def _run_agent_turn(session_id: str, run_id: str, question: str) -> Dict[str, Any]:
    from app.opar.agent_controller import run_agent_chat_controller
    from app.services.llm_selection import get_resolved_llm_provider, model_for_provider

    ctx, analysis = _build_context(session_id, question)
    engagement_id = ctx.engagement_id or session_id

    def audit_tool(call) -> None:
        append_audit_event(
            f"analyst_tool session_id={session_id} run_id={run_id} tool={call.name}"
        )

    result = run_agent_chat_controller(
        ctx,
        seed_skill_outputs=dict(analysis.get("skill_outputs") or {}),
        progress_callback=lambda phase, msg: progress_append(run_id, phase, msg),
        thinking_callback=lambda chunk: progress_append_thinking(run_id, chunk),
        tool_audit_callback=audit_tool,
    )

    if not result.success:
        fallback = _deterministic_fallback(session_id, question, analysis)
        append_audit_event(
            f"analyst_run session_id={session_id} run_id={run_id} available=false "
            f"reason={result.fallback_reason}"
        )
        return {
            "run_id": run_id,
            "available": False,
            "answer": "",
            "thinking": None,
            "agent_trace": result.agent_trace or [],
            "skills_run": [],
            "queries_run": [],
            "charts": [],
            "provenance": None,
            "fallback": {
                "reason": result.fallback_reason or "agent_unavailable",
                "nl_query_result": fallback,
            },
        }

    answer = (result.agent_summary or "").strip()
    trace = result.agent_trace or []
    skill_outputs = result.act_result.skill_outputs if result.act_result else {}
    skills_run = sorted(skill_outputs.keys())
    queries_run = [
        {"sql": str((t.get("arguments") or {}).get("sql") or "")}
        for t in trace
        if t.get("tool") == "query_spend" and (t.get("arguments") or {}).get("sql")
    ]

    charts: List[Dict[str, Any]] = []
    if skill_outputs:
        try:
            from app.opar.visualization import build_chart_specs

            charts = build_chart_specs(question, skill_outputs) or []
        except Exception:
            charts = []

    provenance = None
    if answer:
        from app.opar.provenance import record_llm_narrative

        model_version = model_for_provider(get_resolved_llm_provider())
        provenance = record_llm_narrative(
            answer,
            engagement_id=engagement_id,
            turn_id=run_id,
            skill_outputs_used=skills_run,
            prompt_text=f"analyst:{question}",
            model_version=model_version,
            metadata={"surface": "workbench_analyst", "session_id": session_id},
        )

    append_audit_event(
        f"analyst_run session_id={session_id} run_id={run_id} available=true "
        f"tools={len(trace)} skills={len(skills_run)}"
    )
    return {
        "run_id": run_id,
        "available": True,
        "answer": answer,
        "thinking": result.thinking_text,
        "agent_trace": trace,
        "skills_run": skills_run,
        "queries_run": queries_run,
        "charts": charts,
        "provenance": provenance,
        "fallback": None,
    }


def _persist_turn(session_id: str, question: str, outcome: Dict[str, Any]) -> None:
    key = _turn_key(session_id)
    record = _memory.get(_TURN_SCOPE, key) or {}
    turns = list(record.get("turns") or [])
    turns.append(
        {
            "run_id": outcome.get("run_id"),
            "question": question,
            "answer": outcome.get("answer") or "",
            "available": outcome.get("available", False),
            "agent_trace": outcome.get("agent_trace") or [],
            "charts": outcome.get("charts") or [],
            "provenance": outcome.get("provenance"),
            "ts": datetime.now(timezone.utc).isoformat(),
        }
    )
    _memory.put(_TURN_SCOPE, key, {"turns": turns[-_MAX_TURNS_KEPT:]})


@router.post("/api/v1/analyst/{session_id}/run")
async def run_analyst_turn(
    request: Request, session_id: str, payload: AnalystRunRequest
) -> Dict[str, Any]:
    validate_session_id(session_id)
    check_session_owner(request, session_id)
    question = (payload.question or "").strip()
    if not question:
        raise HTTPException(status_code=422, detail="question is required")

    from app.config import ANALYST_TIMEOUT_SECONDS

    progress_init(payload.run_id, session_id)
    progress_append(payload.run_id, "observe", "Analyst agent starting")
    try:
        outcome = await asyncio.wait_for(
            asyncio.to_thread(_run_agent_turn, session_id, payload.run_id, question),
            timeout=ANALYST_TIMEOUT_SECONDS,
        )
        progress_complete(payload.run_id, failed=not outcome.get("available", False))
    except asyncio.TimeoutError:
        progress_complete(payload.run_id, failed=True, error="timeout")
        raise HTTPException(
            status_code=408,
            detail=f"Analyst run exceeded {ANALYST_TIMEOUT_SECONDS}s — try a narrower question",
        )
    except Exception as exc:
        progress_complete(payload.run_id, failed=True, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    _persist_turn(session_id, question, outcome)
    return outcome


@router.get("/api/v1/analyst/{session_id}/history")
def get_analyst_history(request: Request, session_id: str) -> Dict[str, Any]:
    validate_session_id(session_id)
    check_session_owner(request, session_id)
    record = _memory.get(_TURN_SCOPE, _turn_key(session_id)) or {}
    return {"turns": record.get("turns") or []}
