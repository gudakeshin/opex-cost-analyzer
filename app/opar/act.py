from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List

PER_SKILL_TIMEOUT_SECONDS: float = float(os.environ.get("PER_SKILL_TIMEOUT_SECONDS", "30"))

from pydantic import ValidationError

from app.config import UPLOAD_DIR, logger
from app.metrics import skill_execution_duration_seconds
from app.models import NormalizedSpendLine
from app.opar.memory_adapter import get_memory_adapter
from app.opar.models import ActResult, EvalTrace, ExecutionPlan, ObserveContext, SkillTask, SkillTrace
from app.skills.contracts import AnalysisSynthesizerOutput, ExecutiveCommunicationOutput
from app.services.analysis import load_taxonomy
from app.services.ingestion import parse_document, parse_spend_file
from app.storage import read_json


def _build_transaction_examples(
    lines: list[NormalizedSpendLine],
    max_categories: int = 8,
    max_examples_per_category: int = 3,
) -> Dict[str, list[Dict[str, Any]]]:
    """Build concrete spend examples per category for narrative grounding."""
    grouped: Dict[str, list[NormalizedSpendLine]] = {}
    for line in lines:
        grouped.setdefault(line.category_id, []).append(line)

    out: Dict[str, list[Dict[str, Any]]] = {}
    for category_id, cat_lines in grouped.items():
        top = sorted(cat_lines, key=lambda x: float(x.amount or 0.0), reverse=True)[:max_examples_per_category]
        out[category_id] = [
            {
                "supplier": x.supplier,
                "description": x.description,
                "amount": float(x.amount or 0.0),
                "business_unit": x.business_unit,
                "geo": x.geo,
                "spend_date": x.spend_date,
            }
            for x in top
        ]
    # Keep payload compact for LLM prompts.
    limited = sorted(out.items(), key=lambda kv: sum(e["amount"] for e in kv[1]), reverse=True)[:max_categories]
    return dict(limited)


def _load_session_data(session_id: str) -> tuple[list[NormalizedSpendLine], list[str], dict]:
    manifest_path = UPLOAD_DIR / session_id / "manifest.json"
    manifest = read_json(manifest_path, {"files": [], "industry": "", "annual_revenue": 0.0})
    taxonomy = load_taxonomy()
    lines: list[NormalizedSpendLine] = []
    docs_text: list[str] = []
    model_manifest = manifest.get("model_manifest") if isinstance(manifest, dict) else None

    for f in manifest.get("files", []):
        path = Path(f.get("path", ""))
        if not path.exists():
            continue
        suffix = path.suffix.lower()
        if suffix in (".xlsx", ".xls", ".csv"):
            lines.extend(parse_spend_file(path, taxonomy, workbook_manifest=model_manifest))
        else:
            docs_text.append(parse_document(path))

    return lines, docs_text, manifest


def _invoke_skill(
    task_name: str,
    prior_results: Dict[str, Dict[str, Any]],
    lines: list[NormalizedSpendLine],
    docs_text: list[str],
    manifest: dict,
    user_message: str = "",
    headcount: float | None = None,
) -> tuple[Dict[str, Any], str | None]:
    """Dispatch *task_name* to its registered handler via the skill dispatch registry.

    T2-2: Replaces the 130-line if/elif switch statement with a 6-line lookup,
    following Fowler's *Replace Conditional with Polymorphism* (§12.6).
    Handlers live in app.skills.dispatch — add new skills there.
    """
    from app.skills.dispatch import SkillContext, invoke_skill  # lazy — avoids circular import

    ctx = SkillContext(
        lines=lines,
        docs_text=docs_text,
        manifest=manifest,
        prior_results=prior_results,
        user_message=user_message,
        headcount=headcount,
    )
    _t0 = time.time()
    try:
        result = invoke_skill(task_name, ctx)
        skill_execution_duration_seconds.labels(skill_name=task_name).observe(time.time() - _t0)
        return result
    except KeyError:
        skill_execution_duration_seconds.labels(skill_name=task_name).observe(time.time() - _t0)
        # Unknown skill — return empty dict (graceful degradation, not a hard crash)
        logger.warning('"unknown_skill skill=%s"', task_name)
        return {}, None


# T2-4: Pydantic contracts for LLM synthesis skill outputs.
# On ValidationError the output is replaced with a safe fallback so that
# downstream reflect/respond steps never crash on a missing key.
_LLM_OUTPUT_CONTRACTS: Dict[str, type] = {
    "analysis-synthesizer": AnalysisSynthesizerOutput,
    "executive-communication": ExecutiveCommunicationOutput,
}


def _validate_llm_output(skill_name: str, out: Dict[str, Any]) -> Dict[str, Any]:
    """Validate *out* against its Pydantic contract (T2-4).

    Returns *out* unchanged on success.
    On ``ValidationError``, logs a warning and returns a safe fallback dict
    with ``analysis_available: False`` so the rest of the pipeline can degrade
    gracefully rather than raising ``AttributeError`` / ``KeyError`` downstream.
    """
    contract = _LLM_OUTPUT_CONTRACTS.get(skill_name)
    if contract is None or not out:
        return out  # no contract defined — pass through
    try:
        contract.model_validate(out)
        return out
    except ValidationError as exc:
        logger.warning(
            '"llm_output_schema_violation skill=%s errors=%s"',
            skill_name,
            exc.error_count(),
        )
        return {
            "analysis_available": False,
            "validation_error": str(exc)[:300],
        }


def _invoke_skill_sync(
    task: SkillTask,
    prior_results: Dict[str, Dict[str, Any]],
    lines: list[NormalizedSpendLine],
    docs_text: list[str],
    manifest: dict,
    user_message: str = "",
    headcount: float | None = None,
) -> tuple[str, Dict[str, Any] | None, str | None, str | None]:
    """Run a single skill. Returns (skill_name, output, error, degraded_reason)."""
    deps_met = all(dep in prior_results for dep in task.depends_on)
    if not deps_met:
        missing = [d for d in task.depends_on if d not in prior_results]
        return task.skill_name, None, f"Missing dependencies: {missing}", None
    try:
        out, degraded_reason = _invoke_skill(
            task.skill_name, prior_results, lines, docs_text, manifest,
            user_message, headcount=headcount,
        )
        # T2-4: Validate LLM synthesis outputs against Pydantic contracts.
        out = _validate_llm_output(task.skill_name, out or {})
        if degraded_reason:
            logger.warning('"skill degraded skill=%s reason=%s"', task.skill_name, degraded_reason)
            return task.skill_name, out, None, degraded_reason
        return task.skill_name, out, None, None
    except Exception as e:
        logger.error('"skill error skill=%s error=%s"', task.skill_name, e, exc_info=True)
        return task.skill_name, None, str(e), None


def _build_input_snapshot(
    task: SkillTask,
    prior_results: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """Capture the resolved dependency outputs that will be fed into this skill."""
    return {dep: prior_results[dep] for dep in task.depends_on if dep in prior_results}


def _save_eval_trace(trace: EvalTrace, session_id: str) -> None:
    """Persist EvalTrace to UPLOAD_DIR/<session_id>/eval_trace.json."""
    try:
        out_dir = UPLOAD_DIR / session_id
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / "eval_trace.json"
        path.write_text(trace.model_dump_json(indent=2))
    except Exception as exc:
        logger.warning('"eval_trace write failed for %s: %s"', session_id, exc)


async def _act_async(
    plan: ExecutionPlan,
    ctx: ObserveContext,
    progress_callback: Callable[[str, str], None] | None = None,
    enable_tracing: bool = False,
) -> ActResult:
    """Execute the plan with parallel groups via asyncio.gather."""
    start = time.perf_counter()
    results: Dict[str, Dict[str, Any]] = {}
    errors: Dict[str, str] = {}
    degradation_reasons: Dict[str, str] = {}
    skill_traces: List[SkillTrace] = []
    adapter = get_memory_adapter()

    from app.skills.engine import infer_industry_from_spend  # lazy — avoids circular import

    lines, docs_text, manifest = _load_session_data(ctx.session_id)
    headcount = float(manifest.get("headcount") or 0) or None

    # Auto-detect industry from spend patterns when not explicitly supplied
    if not manifest.get("industry") and lines:
        total_spend = sum(x.reporting_amount for x in lines)
        inferred = infer_industry_from_spend(lines, total_spend)
        if inferred:
            manifest = dict(manifest)  # don't mutate original
            manifest["industry"] = inferred
            manifest["industry_inferred"] = True
            logger.info('"industry_auto_detected industry=%s"', inferred)

    groups = sorted(set(t.parallel_group for t in plan.tasks))
    for group_id in groups:
        group_tasks = [t for t in plan.tasks if t.parallel_group == group_id]
        if progress_callback:
            progress_callback("act", f"Starting parallel group {group_id + 1} with {len(group_tasks)} skill(s).")

        # Capture input snapshots before dispatching (for tracing)
        input_snapshots: Dict[str, Dict[str, Any]] = {}
        if enable_tracing:
            for task in group_tasks:
                input_snapshots[task.skill_name] = _build_input_snapshot(task, results)

        # Run all tasks in this group in parallel with per-skill timeout.
        coros = [
            asyncio.wait_for(
                asyncio.to_thread(
                    _invoke_skill_sync,
                    task,
                    dict(results),  # snapshot for read-only access
                    lines,
                    docs_text,
                    manifest,
                    ctx.user_message,
                    headcount,
                ),
                timeout=PER_SKILL_TIMEOUT_SECONDS,
            )
            for task in group_tasks
        ]

        t_group_start = time.perf_counter()
        group_results = await asyncio.gather(*coros, return_exceptions=True)

        for task, outcome in zip(group_tasks, group_results):
            skill_duration_ms = (time.perf_counter() - t_group_start) * 1000

            if isinstance(outcome, Exception):
                errors[task.skill_name] = str(outcome)
                if progress_callback:
                    progress_callback("act", f"Failed: {task.skill_name} ({errors[task.skill_name]})")
                if enable_tracing:
                    skill_traces.append(SkillTrace(
                        skill_name=task.skill_name,
                        parallel_group=group_id,
                        input_snapshot=input_snapshots.get(task.skill_name, {}),
                        output=None,
                        error=str(outcome),
                        duration_ms=skill_duration_ms,
                    ))
                continue

            skill_name, output, err, degraded_reason = outcome
            if degraded_reason:
                degradation_reasons[skill_name] = degraded_reason
            if err:
                errors[skill_name] = err
                if progress_callback:
                    progress_callback("act", f"Failed: {skill_name} ({err})")
                if enable_tracing:
                    skill_traces.append(SkillTrace(
                        skill_name=skill_name,
                        parallel_group=group_id,
                        input_snapshot=input_snapshots.get(skill_name, {}),
                        output=None,
                        error=err,
                        duration_ms=skill_duration_ms,
                    ))
                continue

            if output is not None:
                results[skill_name] = output
                adapter.add_session(
                    ctx.session_id,
                    {"skill": skill_name, "summary": str(output)[:500]},
                    {"skill": skill_name, "turn": ctx.turn_id},
                )
                if enable_tracing:
                    skill_traces.append(SkillTrace(
                        skill_name=skill_name,
                        parallel_group=group_id,
                        input_snapshot=input_snapshots.get(skill_name, {}),
                        output=output,
                        error=None,
                        duration_ms=skill_duration_ms,
                    ))

        if progress_callback:
            succeeded = sum(1 for t in group_tasks if t.skill_name in results and t.skill_name not in errors)
            failed_count = sum(1 for t in group_tasks if t.skill_name in errors)
            degraded_count = sum(1 for t in group_tasks if t.skill_name in degradation_reasons)
            msg = f"Group {group_id + 1} complete: {succeeded} succeeded, {failed_count} failed"
            if degraded_count:
                msg += f", {degraded_count} degraded"
            progress_callback("act", msg)

    duration_ms = (time.perf_counter() - start) * 1000

    eval_trace: EvalTrace | None = None
    if enable_tracing:
        eval_trace = EvalTrace(
            session_id=ctx.session_id,
            turn_id=ctx.turn_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            skill_traces=skill_traces,
            total_duration_ms=duration_ms,
        )
        _save_eval_trace(eval_trace, ctx.session_id)

    return ActResult(
        skill_outputs=results,
        errors=errors,
        degradation_reasons=degradation_reasons,
        duration_ms=duration_ms,
        eval_trace=eval_trace,
    )


async def act(
    plan: ExecutionPlan,
    ctx: ObserveContext,
    progress_callback: Callable[[str, str], None] | None = None,
    enable_tracing: bool = False,
) -> ActResult:
    """Execute the plan, dispatching skills in parallel within each group.

    Args:
        enable_tracing: When True, logs per-skill inputs/outputs/timing and persists
                        an EvalTrace to UPLOAD_DIR/<session_id>/eval_trace.json.
                        Defaults to False to keep production overhead minimal.
    """
    return await _act_async(plan, ctx, progress_callback=progress_callback, enable_tracing=enable_tracing)
