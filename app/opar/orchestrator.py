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
from app.opar.models import ExecutionPlan, ReflectOutput, SkillTask
from app.opar.observe import observe
from app.opar.plan import plan
from app.opar.qa_lookup import answer_general_qa, _FILE_FORMAT_MSG, _CAPABILITIES_MSG
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
) -> Dict[str, Any]:
    """Run Observe + Plan only. Returns plan summary for user confirmation."""
    ctx = observe(msg, session_id, user_id, file_ids)
    if ctx.clarification_required and ctx.clarification_prompt:
        return {
            "clarification_required": True,
            "clarification_prompt": ctx.clarification_prompt,
            "user_summary": None,
            "plan": None,
        }
    exec_plan = plan(ctx)
    return {
        "clarification_required": False,
        "clarification_prompt": None,
        "user_summary": exec_plan.user_summary,
        "estimated_duration": exec_plan.estimated_duration,
        "requires_approval": exec_plan.requires_approval,
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
        )
    finally:
        opar_cycle_duration_seconds.observe(time.perf_counter() - _opar_start)


async def _run_opar_loop_inner(
    msg: str,
    session_id: str,
    user_id: str,
    file_ids: list[str] | None,
    progress_callback: Callable[[str, str], None] | None,
    progress: list[Dict[str, str]],
    thinking_enabled: bool = False,
    thinking_budget_tokens: int = 8000,
) -> ReflectOutput:

    _add_progress_step(progress, "observe", "Understanding your request...")
    if progress_callback:
        progress_callback("observe", "Understanding your request...")
    ctx = observe(msg, session_id, user_id, file_ids)
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
    if ctx.clarification_required and ctx.clarification_prompt:
        return ReflectOutput(
            response_text=ctx.clarification_prompt,
            loop_complete=False,
            next_loop_trigger=ctx.clarification_prompt,
            progress_steps=progress,
            next_options=[{"label": "Upload spend data", "message": "How do I upload my data?"}],
        )

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
            if not chart_request:
                validated = existing_analysis.get("skill_outputs", {})
                if not validated:
                    # Wrap entire analysis as if it were skill outputs
                    validated = {"spend-profiler": existing_analysis} if existing_analysis.get("category_profile") else {}
                answer = answer_general_qa(msg, validated, currency=str(existing_analysis.get("reporting_currency") or _session_currency(session_id)))
                next_opts = []
                if validated.get("spend-profiler"):
                    next_opts = [
                        {"label": "Benchmark my spend", "message": "Benchmark my spend against industry peers"},
                        {"label": "Value-at-the-table", "message": "Calculate the value-at-the-table matrix"},
                    ]
                return ReflectOutput(
                    response_text=answer,
                    loop_complete=True,
                    progress_steps=progress,
                    next_options=next_opts,
                )

        # No stored analysis — check if files are uploaded
        if ctx.uploaded_file_ids:
            # Files exist but no analysis yet — run profiler to give a first answer
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
    # Normal OPAR pipeline: Plan → Act → Reflect
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
    )

    result.progress_steps = progress
    logger.info('"opar_complete session_id=%s loop_complete=%s"', session_id, result.loop_complete)
    return result
