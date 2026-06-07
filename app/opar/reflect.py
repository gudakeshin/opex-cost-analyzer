"""Reflect phase — thin orchestrator over validation, synthesis, and persistence."""
from __future__ import annotations

from typing import Any, Dict, List

from app.config import UPLOAD_DIR
from app.memory import MemoryStore
from app.opar.chat_synthesis import synthesize_chat_response
from app.opar.visualization import build_chart_specs
from app.opar.models import (
    ActResult,
    AdvisorySections,
    ConfidenceScore,
    ExecutionPlan,
    ObserveContext,
    ReflectOutput,
)
from app.opar.reflect_persistence import (
    apply_memory_updates,
    build_next_options,
    persist_conflict_manifest,
    persist_session_analysis,
    record_advisory_provenance,
    _merge_with_session_cache,
)
from app.opar.reflect_synthesis import (
    advisory_quality_ok,
    build_response_text,
    compose_response_from_advisory,
    format_currency,
    generate_llm_advisory_sections,
    is_category_focused_request,
    is_qa_lookup,
    needs_llm_advisory,
    recommendation_rows,
    set_reflect_currency,
)
from app.opar.reflect_validation import (
    _build_value_bridge_matrix,
    _compute_dedup_factor,
    _compute_grounding_coverage,
    _compute_quality_signals,
    _determine_loop_control,
    _layer1_optional_synthesis_validation,
    _layer1_schema_validation,
    _layer2_coherence_checks,
    _layer3_domain_confidence,
    _run_gate2_check,
    _run_reg_watcher,
)
from app.storage import read_json

_memory = MemoryStore()

# Backward-compatible re-exports for tests and callers
_advisory_quality_ok = advisory_quality_ok
_compose_response_from_advisory = compose_response_from_advisory


def reflect(
    act_result: ActResult,
    plan: ExecutionPlan,
    ctx: ObserveContext,
    thinking_enabled: bool = False,
    thinking_budget_tokens: int = 8000,
    chat_history: list[dict[str, str]] | None = None,
) -> ReflectOutput:
    """Validate outputs (3-layer), compose response, persist memory, return ReflectOutput."""
    validated: Dict[str, Dict[str, Any]] = {}
    failed: Dict[str, str] = {}
    confidence_scores: Dict[str, ConfidenceScore] = {}

    outputs = act_result.skill_outputs
    errors = act_result.errors
    degradation_reasons = getattr(act_result, "degradation_reasons", {}) or {}

    for task in plan.tasks:
        if task.skill_name in errors:
            failed[task.skill_name] = errors[task.skill_name]
            continue
        out = outputs.get(task.skill_name, {})
        if not out:
            continue
        validated[task.skill_name] = out
        confidence_scores[task.skill_name] = ConfidenceScore(
            level="mid",
            factor=0.75,
            rationale="Schema validated",
        )

    _layer1_schema_validation(validated, failed, plan)
    _layer1_optional_synthesis_validation(validated, failed)
    _layer2_coherence_checks(validated, failed, confidence_scores)
    _layer3_domain_confidence(validated, ctx, confidence_scores)

    composition_validated = _merge_with_session_cache(ctx.session_id, validated)

    sme_critique = composition_validated.get("sme-critique", {})
    sme_portfolio_probes: List[Dict[str, Any]] = (
        sme_critique.get("portfolio_probes", []) if isinstance(sme_critique, dict) else []
    )
    if not sme_portfolio_probes and isinstance(sme_critique, dict):
        sme_portfolio_probes = sme_critique.get("top_probes", []) or []

    dedup_factor = _compute_dedup_factor(validated)
    value_bridge_matrix = _build_value_bridge_matrix(validated, dedup_factor)

    user_updates, agent_updates = apply_memory_updates(ctx, validated)

    loop_complete, next_trigger = _determine_loop_control(validated, failed, ctx, plan)
    replanner_log: List[Dict[str, Any]] = []
    replannable_skills = {"peer-benchmarker", "root-cause-analyzer", "savings-modeler", "value-bridge-calculator"}
    replannable_intents = {"benchmark", "value_bridge", "business_case", "drill_down", "savings_plan", "sensitivity"}
    if ctx.intent_class in replannable_intents and any(t.skill_name in replannable_skills for t in plan.tasks):
        try:
            from app.opar.plan import replan

            _new_plan, replanner_log = replan(ctx, validated, plan)
            if replanner_log and not next_trigger:
                next_trigger = "Additional analysis steps are available based on reflect-gate quality checks."
        except Exception:
            replanner_log = []

    manifest_path = UPLOAD_DIR / ctx.session_id / "manifest.json"
    manifest = read_json(manifest_path, {}) if manifest_path.exists() else {}

    early_analysis = _memory.get("session", ctx.session_id)
    reporting_currency = str(
        (early_analysis or {}).get("reporting_currency")
        or manifest.get("currency")
        or "INR"
    )
    set_reflect_currency(reporting_currency)

    category_focused = is_category_focused_request(ctx, composition_validated)
    response_metadata: Dict[str, Any] = {}
    qa_used_llm = False
    advisory_sections: AdvisorySections | None = None
    thinking_text: str | None = None

    if is_qa_lookup(ctx, validated, composition_validated):
        synthesis = synthesize_chat_response(
            ctx,
            manifest,
            composition_validated,
            chat_history=chat_history,
            currency=reporting_currency,
            thinking_enabled=thinking_enabled,
        )
        response = synthesis.response_text
        response_metadata = synthesis.response_metadata
        qa_used_llm = synthesis.used_llm
        if synthesis.thinking_text:
            thinking_text = synthesis.thinking_text
    else:
        advisory_was_needed = needs_llm_advisory(ctx, composition_validated, category_focused=category_focused)
        if advisory_was_needed:
            advisory_sections, thinking_text = generate_llm_advisory_sections(
                ctx,
                manifest,
                composition_validated,
                thinking_enabled=thinking_enabled,
                thinking_budget_tokens=thinking_budget_tokens,
                category_focused=category_focused,
            )
        if advisory_sections is not None:
            response = compose_response_from_advisory(
                advisory_sections,
                composition_validated,
                include_executive_takeaway=bool(ctx.wants_executive_narrative),
                include_business_case_metrics=bool(ctx.intent_class == "business_case"),
                category_focused=category_focused,
            )
        elif advisory_was_needed and category_focused:
            # The question targets a specific category (e.g. "what drives spend
            # in HR & Recruitment?") and warranted an LLM narrative, but synthesis
            # failed or produced low-quality output. build_response_text composes
            # from whatever portfolio-wide skill outputs happen to be cached
            # (conflicts/spend-profile/benchmark/BvA) regardless of the category
            # asked about — answer the user's actual question via the query-aware
            # chat synthesis path instead. (Portfolio-wide asks like "calculate
            # value bridge" still get build_response_text's value-bridge summary,
            # which is the right composer for that broader request.)
            synthesis = synthesize_chat_response(
                ctx,
                manifest,
                composition_validated,
                chat_history=chat_history,
                currency=reporting_currency,
                thinking_enabled=thinking_enabled,
            )
            response = synthesis.response_text
            response_metadata = synthesis.response_metadata
            qa_used_llm = synthesis.used_llm
            if synthesis.thinking_text:
                thinking_text = synthesis.thinking_text
        else:
            response = build_response_text(composition_validated, failed, plan, ctx)

    quality_signals = _compute_quality_signals(validated, failed, ctx, degradation_reasons=degradation_reasons)
    grounding_coverage = _compute_grounding_coverage(response, validated)
    quality_signals["grounding_coverage"] = grounding_coverage
    if grounding_coverage < 0.2 and validated:
        recs = recommendation_rows(validated, max_items=2)
        if recs:
            evidence_lines = ["", "**Evidence anchors**"]
            for rec in recs:
                evidence_lines.append(
                    f"- {rec['category']}: {format_currency(rec['dedup_mid'])} modeled via {rec.get('lever_label', rec['lever'])}."
                )
            response = (response + "\n" + "\n".join(evidence_lines)).strip()

    persist_session_analysis(
        ctx=ctx,
        act_result=act_result,
        validated=validated,
        manifest=manifest,
        reporting_currency=reporting_currency,
        advisory_sections=advisory_sections,
    )
    persist_conflict_manifest(ctx.session_id, validated)

    gate2_blocked, gate2_narrative = _run_gate2_check(validated, ctx)
    forced_reg_decision, reg_events, _reg_prompt = _run_reg_watcher(validated, ctx)
    artefacts, next_options = build_next_options(
        ctx,
        validated,
        sme_portfolio_probes,
        gate2_blocked=gate2_blocked,
        forced_reg_decision=forced_reg_decision,
    )
    provenance_tag = record_advisory_provenance(ctx, validated, advisory_sections)

    # LLM suggests the most relevant chart(s); numbers come from skill outputs.
    chart_specs = build_chart_specs(ctx.user_message, composition_validated)

    return ReflectOutput(
        validated_outputs=validated,
        failed_validations=failed,
        confidence_scores=confidence_scores,
        value_bridge_matrix=value_bridge_matrix,
        dedup_factor=dedup_factor,
        user_memory_updates=user_updates,
        agent_memory_updates=agent_updates,
        loop_complete=loop_complete,
        next_loop_trigger=next_trigger,
        response_text=response,
        response_artefacts=artefacts,
        advisory_sections=(
            advisory_sections
            if (ctx.wants_executive_narrative or not advisory_sections)
            else advisory_sections.model_copy(update={"executive_takeaway": ""})
        ),
        quality_signals=quality_signals,
        used_llm_synthesis=bool(
            qa_used_llm
            or validated.get("analysis-synthesizer")
            or validated.get("executive-communication")
            or advisory_sections
        ),
        thinking_text=thinking_text,
        response_metadata=response_metadata,
        chart_specs=chart_specs,
        degraded_mode=bool(degradation_reasons),
        fallback_reasons=degradation_reasons,
        next_options=next_options,
        replanner_log=replanner_log,
        gate2_blocked=gate2_blocked,
        gate2_narrative=gate2_narrative,
        regulatory_events=reg_events,
        forced_regulatory_decision=forced_reg_decision,
        narrative_provenance_tag=provenance_tag,
    )
