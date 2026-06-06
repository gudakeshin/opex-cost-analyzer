from __future__ import annotations

from datetime import datetime, timezone
import time
from typing import Any, Callable, Dict

from app.config import UPLOAD_DIR, logger
from app.metrics import opar_cycle_duration_seconds
from app.memory import MemoryStore
from app.opar.category_resolver import tokenize
from app.storage import read_json
from app.utils.inr_format import format_money
from app.opar.act import act
from app.opar.hitl.checkpoint_store import checkpoint_store
from app.opar.hitl.clarification_tool import ClarificationAnswer
from app.opar.hitl.clarification_generator import generate_business_clarification
from app.opar.hitl.resume import apply_clarification_answer
from app.opar.models import ExecutionPlan, ObserveContext, ReflectOutput, SkillTask
from app.opar.observe import observe
from app.opar.plan import plan
from app.opar.chat_synthesis import synthesize_chat_response
from app.opar.qa_lookup import _FILE_FORMAT_MSG, _CAPABILITIES_MSG
from app.opar.reflect import reflect
from app.services.business_case import build_business_case, export_docx

_memory = MemoryStore()


def _session_currency(session_id: str) -> str:
    """Resolve the reporting currency for a session (session state → meta →
    upload manifest), defaulting to INR when unknown. Used to format chat money
    answers in the right currency (₹ Cr for INR engagements)."""
    analysis = _memory.get("session", session_id)
    if isinstance(analysis, dict) and analysis.get("reporting_currency"):
        return str(analysis["reporting_currency"])
    meta = _memory.get("session_meta", session_id)
    if isinstance(meta, dict) and meta.get("reporting_currency"):
        return str(meta["reporting_currency"])
    try:
        manifest = read_json(UPLOAD_DIR / session_id / "manifest.json", {})
        if manifest.get("currency"):
            return str(manifest["currency"])
    except Exception:
        pass
    return "INR"


# ---------------------------------------------------------------------------
# Canned responses for general_qa when no data is uploaded yet
# ---------------------------------------------------------------------------

_ONBOARDING_MSG = (
    "Hi! I'm your **OpEx Intelligence** assistant. Here's how to get started:\n\n"
    "**1. Set your context** — fill in Company, Industry, and Annual Revenue above the chat.\n"
    "**2. Upload your spend data** — click the 📎 button inside the chat box and attach an "
    "Excel or CSV file.\n"
    "**3. Run analysis** — once your file is uploaded, ask me to *benchmark my spend*, "
    "*calculate value-at-the-table*, or *generate a business case*.\n\n"
    "What would you like to do?"
)

_NO_DATA_NEXT_OPTS = [
    {"label": "File format guide", "message": "What columns does my spend file need?"},
    {"label": "What can you analyze?", "message": "What kinds of analysis can you run?"},
]


def _tokenize(text: str) -> list[str]:
    return tokenize(text)


def _is_spend_chart_request(msg: str) -> bool:
    lowered = (msg or "").lower()
    phrases = [
        "open spend chart",
        "open chart",
        "show spend chart",
        "show chart",
        "spend chart",
        "chart view",
        "visualize spend",
        "spend visualization",
    ]
    return any(p in lowered for p in phrases)


def _is_schema_request(msg: str) -> bool:
    lowered = (msg or "").lower()
    return any(
        token in lowered
        for token in [
            "schema",
            "columns",
            "header mapping",
            "semantic map",
            "field mapping",
            "file structure",
        ]
    )


_INTERACTIVE_QA_CAPABILITIES = frozenset({
    "value_modeling",
    "benchmarking",
    "root_cause",
    "executive_narrative",
})

_INTERACTIVE_QA_TOKENS = (
    "savings",
    "save money",
    "optimize",
    "optimise",
    "priorit",
    "opportunity",
    "opportunities",
    "value bridge",
    "value-at-the-table",
    "addressable",
    "business case",
    "npv",
    "payback",
    "benchmark",
    "peer",
    "compare",
    "root cause",
    "why ",
    "driver",
    "executive",
    "cfo",
    "board",
    "reduce cost",
    "cost reduction",
    "cost optimization",
    "cost optimisation",
)


def _should_use_agent_path(ctx: Any) -> bool:
    """True when the agentic tool loop should run instead of rule-based plan()."""
    from app.opar.agent_runtime import agent_loop_available

    if not agent_loop_available():
        return False
    if ctx.intent_class == "export_business_case":
        return False
    if not (ctx.has_tabular_spend or ctx.spend_profile_ready or ctx.has_document_files):
        return False
    return True


def _should_use_cached_qa_fastpath(ctx: Any, msg: str) -> bool:
    """Return True only for simple spend lookups that can be answered from cache.

    Savings, optimization, benchmark, and executive questions must fall through
    to plan → act → reflect so the response is query-conditioned."""
    caps = set(getattr(ctx, "query_capabilities", None) or [])
    if caps & _INTERACTIVE_QA_CAPABILITIES:
        return False
    lowered = (msg or "").lower()
    if any(token in lowered for token in _INTERACTIVE_QA_TOKENS):
        return False
    return True


def _schema_summary_for_session(session_id: str) -> str | None:
    analysis = _memory.get("session", session_id)
    if not isinstance(analysis, dict):
        return None
    profile = analysis.get("skill_outputs", {}).get("spend-profiler", {})
    categories = profile.get("category_profile", []) if isinstance(profile, dict) else []
    if not categories:
        return None
    currency = str(analysis.get("reporting_currency") or "USD")
    top = sorted(categories, key=lambda c: float(c.get("spend", 0.0) or 0.0), reverse=True)[:5]
    lines = [
        f"I can see **{len(categories)} spend categories** in your uploaded data.",
        "Top categories by spend:",
    ]
    for i, row in enumerate(top, 1):
        lines.append(f"{i}. **{row.get('category_name', row.get('category_id', 'Category'))}** — {format_money(float(row.get('spend', 0.0) or 0.0), currency)}")
    return "\n".join(lines)


def _extract_chart_url_from_analysis(analysis: Dict[str, Any]) -> str | None:
    if not isinstance(analysis, dict):
        return None
    outputs = analysis.get("skill_outputs", {})
    if isinstance(outputs, dict):
        chart = outputs.get("chart-builder", {})
        if isinstance(chart, dict):
            url = chart.get("chart_url")
            if isinstance(url, str) and url.startswith("/api/exports/"):
                return url
    for artefact in analysis.get("response_artefacts", []) or []:
        if isinstance(artefact, str) and artefact.startswith("/api/exports/"):
            return artefact
    return None


def _add_progress_step(progress: list[Dict[str, str]], phase: str, message: str) -> None:
    progress.append(
        {
            "phase": phase,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )


def _skipped_skill_reasons(ctx: Any, selected_skills: set[str]) -> list[str]:
    reasons: list[str] = []
    if "document-contextualizer" not in selected_skills and not getattr(ctx, "has_document_files", False):
        reasons.append("Skipped document-contextualizer: no uploaded document files detected.")
    if "chart-builder" not in selected_skills and not getattr(ctx, "wants_spend_visualization", False):
        reasons.append("Skipped chart-builder: spend visualization was not explicitly requested.")
    if "heuristic-analyzer" not in selected_skills and not getattr(ctx, "has_annual_revenue", False):
        reasons.append("Skipped heuristic-analyzer: annual revenue is missing or zero.")
    if "business-case-builder" not in selected_skills and getattr(ctx, "intent_class", "") != "business_case":
        reasons.append("Skipped business-case-builder: this request did not ask for a business case.")
    if "analysis-synthesizer" not in selected_skills and not getattr(ctx, "wants_executive_narrative", False):
        reasons.append("Skipped analysis-synthesizer: executive narrative was not requested.")
    if "executive-communication" not in selected_skills and not getattr(ctx, "wants_executive_narrative", False):
        reasons.append("Skipped executive-communication: executive-ready messaging was not requested.")
    if getattr(ctx, "intent_class", "") == "benchmark" and "value-bridge-calculator" not in selected_skills:
        reasons.append("Skipped value-bridge modeling chain: benchmark intent only requires diagnostic benchmarking.")
    return reasons[:5]


class CheckpointNotFoundError(Exception):
    """Raised when a HITL checkpoint is missing or expired."""


class CheckpointAlreadyResumedError(Exception):
    """Raised when a checkpoint was already consumed without a cached result."""


class ClarificationDeferralError(Exception):
    """Raised when the user selected a deferral option that requires data upload first."""


def _session_manifest(session_id: str) -> Dict[str, Any]:
    return read_json(UPLOAD_DIR / session_id / "manifest.json", {"files": [], "industry": "", "annual_revenue": 0.0})


def _create_hitl_checkpoint(
    ctx: ObserveContext,
    msg: str,
    session_id: str,
    user_id: str,
    file_ids: list[str] | None,
) -> tuple[str, Any]:
    manifest = _session_manifest(session_id)
    clarification = generate_business_clarification(
        ctx,
        company_name=str(manifest.get("company_name") or ""),
        industry=str(manifest.get("industry") or ""),
    )
    checkpoint_id = checkpoint_store.save(
        session_id=session_id,
        user_id=user_id,
        original_message=msg,
        observe_context=ctx.model_dump(mode="json"),
        clarification=clarification,
        file_ids=file_ids,
    )
    return checkpoint_id, clarification


def _hitl_reflect_output(
    clarification: Any,
    checkpoint_id: str,
    progress: list[Dict[str, str]],
) -> ReflectOutput:
    return ReflectOutput(
        response_text=clarification.question,
        loop_complete=False,
        next_loop_trigger=clarification.question,
        progress_steps=progress,
        next_options=[{"label": opt, "message": opt} for opt in clarification.options[:4]],
        hitl_required=True,
        checkpoint_id=checkpoint_id,
        clarification=clarification,
    )


def _handle_no_data_qa(msg: str) -> ReflectOutput:
    """Return a helpful guidance response when no spend data is available."""
    lowered = msg.lower()

    if any(w in lowered for w in ["column", "format", "template", "header", "field", "file"]):
        return ReflectOutput(
            response_text=_FILE_FORMAT_MSG,
            loop_complete=True,
            next_options=[{"label": "Got it, I'll upload now", "message": "Upload spend data"}],
        )

    if any(w in lowered for w in ["can you", "what can", "capabilities", "what do", "help", "analyze"]):
        return ReflectOutput(
            response_text=_CAPABILITIES_MSG,
            loop_complete=True,
            next_options=_NO_DATA_NEXT_OPTS,
        )

    return ReflectOutput(
        response_text=_ONBOARDING_MSG,
        loop_complete=True,
        next_options=_NO_DATA_NEXT_OPTS,
    )


def run_opar_plan_preview(
    msg: str,
    session_id: str,
    user_id: str,
    file_ids: list[str] | None = None,
    *,
    clarification_answer: ClarificationAnswer | None = None,
    clarification_resolved: bool = False,
    waive_spend_requirement: bool = False,
    business_override_note: str | None = None,
) -> Dict[str, Any]:
    """Run Observe + Plan only. Returns plan summary for user confirmation."""
    ctx = observe(
        msg,
        session_id,
        user_id,
        file_ids,
        clarification_answer=clarification_answer,
        clarification_resolved=clarification_resolved,
        waive_spend_requirement=waive_spend_requirement,
        business_override_note=business_override_note,
    )
    if ctx.clarification_required and ctx.clarification_prompt and not ctx.clarification_resolved:
        checkpoint_id, clarification = _create_hitl_checkpoint(ctx, msg, session_id, user_id, file_ids)
        return {
            "hitl_required": True,
            "checkpoint_id": checkpoint_id,
            "clarification": clarification.model_dump(),
            "clarification_required": True,
            "clarification_prompt": clarification.question,
            "user_summary": None,
            "plan": None,
            "requires_confirmation": False,
        }
    exec_plan = plan(ctx)
    planned_skills = [t.skill_name for t in exec_plan.tasks]
    return {
        "hitl_required": False,
        "checkpoint_id": None,
        "clarification": None,
        "clarification_required": False,
        "clarification_prompt": None,
        "user_summary": exec_plan.user_summary,
        "estimated_duration": exec_plan.estimated_duration,
        "requires_approval": exec_plan.requires_approval,
        "requires_confirmation": exec_plan.requires_approval,
        "planned_skills": planned_skills,
        "plan": {
            "total_skills": exec_plan.total_skills,
            "parallel_groups": exec_plan.parallel_groups,
            "tasks": [{"skill_name": t.skill_name, "parallel_group": t.parallel_group} for t in exec_plan.tasks],
        },
    }


async def run_opar_loop(
    msg: str,
    session_id: str,
    user_id: str,
    file_ids: list[str] | None = None,
    progress_callback: Callable[[str, str], None] | None = None,
    thinking_enabled: bool = False,
    thinking_budget_tokens: int = 8000,
    chat_history: list[dict[str, str]] | None = None,
) -> ReflectOutput:
    """Run full Observe -> Plan -> Act -> Reflect cycle (async-native)."""
    _opar_start = time.perf_counter()
    progress: list[Dict[str, str]] = []
    logger.info('"opar_start session_id=%s thinking=%s"', session_id, thinking_enabled)
    try:
        return await _run_opar_loop_inner(
            msg, session_id, user_id, file_ids, progress_callback, progress,
            thinking_enabled=thinking_enabled,
            thinking_budget_tokens=thinking_budget_tokens,
            chat_history=chat_history,
        )
    finally:
        opar_cycle_duration_seconds.observe(time.perf_counter() - _opar_start)


async def resume_opar_loop(
    checkpoint_id: str,
    answer: ClarificationAnswer,
    progress_callback: Callable[[str, str], None] | None = None,
    thinking_enabled: bool = False,
    thinking_budget_tokens: int = 8000,
    chat_history: list[dict[str, str]] | None = None,
) -> ReflectOutput:
    """Resume a suspended OPAR run after the user answers a clarification probe."""
    cp = checkpoint_store.get(checkpoint_id)
    if not cp:
        raise CheckpointNotFoundError(checkpoint_id)
    if cp.status == "resumed":
        if cp.result_snapshot:
            return ReflectOutput.model_validate(cp.result_snapshot)
        raise CheckpointAlreadyResumedError(checkpoint_id)

    overrides = apply_clarification_answer(cp.session_id, answer)
    if overrides.get("defer_only"):
        raise ClarificationDeferralError(
            "Selected option requires providing data before analysis can continue."
        )

    clarification_answer = ClarificationAnswer.model_validate(overrides["clarification_answer"])
    progress: list[Dict[str, str]] = []
    result = await _run_opar_loop_inner(
        cp.original_message,
        cp.session_id,
        cp.user_id,
        cp.file_ids,
        progress_callback,
        progress,
        thinking_enabled=thinking_enabled,
        thinking_budget_tokens=thinking_budget_tokens,
        clarification_answer=clarification_answer,
        clarification_resolved=bool(overrides["clarification_resolved"]),
        waive_spend_requirement=bool(overrides["waive_spend_requirement"]),
        business_override_note=overrides.get("business_override_note"),
        chat_history=chat_history,
    )
    checkpoint_store.mark_resumed(checkpoint_id, result_snapshot=result.model_dump(mode="json"))
    return result


async def _run_opar_loop_inner(
    msg: str,
    session_id: str,
    user_id: str,
    file_ids: list[str] | None,
    progress_callback: Callable[[str, str], None] | None,
    progress: list[Dict[str, str]],
    thinking_enabled: bool = False,
    thinking_budget_tokens: int = 8000,
    clarification_answer: ClarificationAnswer | None = None,
    clarification_resolved: bool = False,
    waive_spend_requirement: bool = False,
    business_override_note: str | None = None,
    chat_history: list[dict[str, str]] | None = None,
) -> ReflectOutput:

    _add_progress_step(progress, "observe", "Understanding your request...")
    if progress_callback:
        progress_callback("observe", "Understanding your request...")
    ctx = observe(
        msg,
        session_id,
        user_id,
        file_ids,
        clarification_answer=clarification_answer,
        clarification_resolved=clarification_resolved,
        waive_spend_requirement=waive_spend_requirement,
        business_override_note=business_override_note,
    )
    _add_progress_step(
        progress,
        "observe",
        f"Intent: {ctx.intent_class} ({ctx.intent_source}, confidence {int(ctx.intent_confidence * 100)}%).",
    )
    if ctx.schema_confirmation_required and ctx.schema_confirmation_note:
        _add_progress_step(progress, "observe", ctx.schema_confirmation_note)
        if progress_callback:
            progress_callback("observe", ctx.schema_confirmation_note)

    # ------------------------------------------------------------------
    # Clarification gate: only fires for analysis intents missing data
    # ------------------------------------------------------------------
    if ctx.clarification_required and ctx.clarification_prompt and not ctx.clarification_resolved:
        checkpoint_id, clarification = _create_hitl_checkpoint(ctx, msg, session_id, user_id, file_ids)
        return _hitl_reflect_output(clarification, checkpoint_id, progress)

    # ------------------------------------------------------------------
    # general_qa: answer from existing context, no heavy pipeline
    # ------------------------------------------------------------------
    if ctx.intent_class == "general_qa":
        if _is_schema_request(msg):
            schema_fast = _schema_summary_for_session(session_id)
            if schema_fast:
                return ReflectOutput(
                    response_text=schema_fast,
                    loop_complete=True,
                    progress_steps=progress,
                )
        # Check if a previous analysis is stored
        existing_analysis = _memory.get("session", session_id)
        chart_request = _is_spend_chart_request(msg)
        if existing_analysis:
            if chart_request:
                chart_url = _extract_chart_url_from_analysis(existing_analysis)
                if chart_url:
                    return ReflectOutput(
                        response_text=f"**Spend Profile Chart View**\n[Open chart view]({chart_url})",
                        response_artefacts=[chart_url],
                        loop_complete=True,
                        progress_steps=progress,
                        next_options=[{"label": "Refresh spend chart", "message": "Show spend profile chart"}],
                    )
                if ctx.has_tabular_spend:
                    # No cached chart URL found; proceed with normal plan->act->reflect to regenerate it.
                    pass
                else:
                    return ReflectOutput(
                        response_text="I couldn't find chart-ready spend data yet. Upload a spend file and I can generate the chart.",
                        loop_complete=True,
                        progress_steps=progress,
                        next_options=[{"label": "File format guide", "message": "What columns does my spend file need?"}],
                    )
            if not chart_request and _should_use_cached_qa_fastpath(ctx, msg):
                validated = existing_analysis.get("skill_outputs", {})
                if not validated:
                    validated = {"spend-profiler": existing_analysis} if existing_analysis.get("category_profile") else {}
                try:
                    from app.opar.hitl.probe_answers import apply_probe_answers_to_skill_outputs

                    validated = apply_probe_answers_to_skill_outputs(validated, session_id)
                except Exception:
                    pass
                manifest = _session_manifest(session_id)
                currency = str(existing_analysis.get("reporting_currency") or _session_currency(session_id))
                synthesis = synthesize_chat_response(
                    ctx,
                    manifest,
                    validated,
                    chat_history=chat_history,
                    currency=currency,
                    thinking_enabled=thinking_enabled,
                )
                next_opts = []
                if validated.get("spend-profiler"):
                    next_opts = [
                        {"label": "Benchmark my spend", "message": "Benchmark my spend against industry peers"},
                        {"label": "Value-at-the-table", "message": "Calculate the value-at-the-table matrix"},
                    ]
                return ReflectOutput(
                    response_text=synthesis.response_text,
                    loop_complete=True,
                    progress_steps=progress,
                    next_options=next_opts,
                    used_llm_synthesis=synthesis.used_llm,
                    thinking_text=synthesis.thinking_text,
                    response_metadata=synthesis.response_metadata,
                )

        # No stored analysis — check if files are uploaded
        if ctx.uploaded_file_ids or ctx.has_tabular_spend:
            # Session files or engagement corpus spend — run profiler to answer
            pass  # fall through to normal OPAR pipeline (plan will set up profiler-only)
        else:
            # Truly no data — return onboarding guidance
            no_data = _handle_no_data_qa(msg)
            _add_progress_step(progress, "reflect", "Responding with data onboarding guidance.")
            no_data.progress_steps = progress
            return no_data

    # ------------------------------------------------------------------
    # export_business_case: create docx from stored session
    # ------------------------------------------------------------------
    if ctx.intent_class == "export_business_case":
        analysis = _memory.get("session", session_id)
        if not analysis:
            return ReflectOutput(
                response_text=(
                    "No analysis found. Please run a business case first "
                    "(e.g. 'Generate business case'), then I can export it as a document."
                ),
                progress_steps=progress,
                next_options=[{"label": "Generate business case", "message": "Generate business case"}],
            )
        bc = build_business_case(analysis)
        path = export_docx(bc, f"{session_id}_business_case.docx")
        return ReflectOutput(
            response_text=f"Business case exported as document. [Download](/api/exports/{path.name})",
            response_artefacts=[f"/api/exports/{path.name}"],
            progress_steps=progress,
            next_options=[],
        )

    # ------------------------------------------------------------------
    # Agent controller (M2/M3): tool-use investigation before reflect
    # ------------------------------------------------------------------
    if _should_use_agent_path(ctx):
        from app.opar.agent_controller import try_agent_run

        _add_progress_step(progress, "plan", "Agent investigating with tools...")
        if progress_callback:
            progress_callback("plan", "Agent investigating with tools...")
        agent_result = try_agent_run(ctx, progress_callback=progress_callback)
        if agent_result and agent_result.act_result and agent_result.exec_plan:
            _add_progress_step(
                progress,
                "act",
                f"Agent ran {len(agent_result.exec_plan.tasks)} skill(s) via tools.",
            )
            _add_progress_step(progress, "reflect", "Validating and summarizing results...")
            if progress_callback:
                progress_callback("reflect", "Validating and summarizing results...")
            result = reflect(
                agent_result.act_result,
                agent_result.exec_plan,
                ctx,
                thinking_enabled=thinking_enabled,
                thinking_budget_tokens=thinking_budget_tokens,
                chat_history=chat_history,
            )
            meta = dict(result.response_metadata or {})
            meta["agent_trace"] = agent_result.agent_trace or []
            meta["agent_summary"] = agent_result.agent_summary
            meta["agent_path"] = True
            result.response_metadata = meta
            if agent_result.thinking_text:
                result.thinking_text = agent_result.thinking_text
            result.progress_steps = progress
            logger.info('"opar_agent_complete session_id=%s"', session_id)
            return result

    # ------------------------------------------------------------------
    # Deterministic fallback: Plan → Act → Reflect
    # ------------------------------------------------------------------
    _add_progress_step(progress, "plan", "Planning analysis steps...")
    if progress_callback:
        progress_callback("plan", "Planning analysis steps...")
    try:
        exec_plan = plan(ctx)
    except Exception as exc:
        logger.warning('"plan_failed session_id=%s error=%s; using_fallback"', session_id, exc)
        exec_plan = ExecutionPlan(
            tasks=[SkillTask(skill_name="spend-profiler", inputs={}, depends_on=[], parallel_group=0, estimated_tokens=500)],
            total_skills=1,
            parallel_groups=1,
            user_summary="Analysis plan unavailable — running spend profiling.",
            estimated_duration="~20 seconds",
            requires_approval=False,
        )
    if exec_plan.tasks:
        selected = ", ".join(t.skill_name for t in exec_plan.tasks)
        _add_progress_step(progress, "plan", f"Selected skills: {selected}")
        if progress_callback:
            progress_callback("plan", f"Selected skills: {selected}")
        selected_set = {t.skill_name for t in exec_plan.tasks}
        reasons = _skipped_skill_reasons(ctx, selected_set)
        if reasons:
            _add_progress_step(progress, "plan", f"Skipped skill summary: {' | '.join(reasons[:2])}")
            if progress_callback:
                progress_callback("plan", f"Skipped skill summary: {' | '.join(reasons[:2])}")

    # Empty plan (general_qa with no data falls through here after files check)
    if not exec_plan.tasks:
        no_data = _handle_no_data_qa(msg)
        _add_progress_step(progress, "reflect", "No executable skills found for this request.")
        no_data.progress_steps = progress
        return no_data

    _add_progress_step(progress, "act", f"Running {exec_plan.total_skills} analysis steps...")
    if progress_callback:
        progress_callback("act", f"Running {exec_plan.total_skills} analysis steps...")
    act_result = await act(exec_plan, ctx, progress_callback=progress_callback)
    succeeded = len([s for s in exec_plan.tasks if s.skill_name in act_result.skill_outputs and s.skill_name not in act_result.errors])
    failed_count = len(act_result.errors)
    degraded_count = len(getattr(act_result, "degradation_reasons", {}) or {})
    summary = f"Execution complete: {succeeded} succeeded, {failed_count} failed"
    if degraded_count:
        summary += f", {degraded_count} degraded"
    _add_progress_step(progress, "act", summary)

    _add_progress_step(progress, "reflect", "Validating and summarizing results...")
    if progress_callback:
        progress_callback("reflect", "Validating and summarizing results...")
    # reflect() owns response composition for general_qa as well — when only the
    # profiler/doc-contextualizer ran, reflect's QA_LOOKUP mode produces the
    # focused answer directly (see app/opar/reflect.py::_is_qa_lookup). The
    # orchestrator no longer post-processes / overwrites reflect output.
    result = reflect(
        act_result, exec_plan, ctx,
        thinking_enabled=thinking_enabled,
        thinking_budget_tokens=thinking_budget_tokens,
        chat_history=chat_history,
    )

    result.progress_steps = progress
    logger.info('"opar_complete session_id=%s loop_complete=%s"', session_id, result.loop_complete)
    return result
