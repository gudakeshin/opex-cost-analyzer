from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from app.opar.models import ExecutionPlan, ObserveContext, SkillTask
from app.skills.registry import discover_skills

# ---------------------------------------------------------------------------
# Group 0 security skill definitions (always prepended when spend lines exist)
# ---------------------------------------------------------------------------

_GROUP0_SKILLS = [
    SkillTask(skill_name="pii-stripper",       inputs={}, depends_on=[],              parallel_group=0, estimated_tokens=200),
    SkillTask(skill_name="data-classifier",    inputs={}, depends_on=["pii-stripper"], parallel_group=1, estimated_tokens=200),
    SkillTask(skill_name="llm-context-builder",inputs={}, depends_on=["data-classifier"], parallel_group=2, estimated_tokens=150),
]

_GROUP0_NAMES = {t.skill_name for t in _GROUP0_SKILLS}


def _inject_group0(tasks: List[SkillTask], ctx: ObserveContext) -> List[SkillTask]:
    """Prepend Group 0 security skills when tabular spend is present.

    Re-numbers all existing tasks' parallel_group by +3 to make room for
    the three security stages (0 pii-stripper, 1 data-classifier, 2 llm-context-builder).
    Also rewires the first non-security task's depends_on to include
    llm-context-builder so analysis skills receive sanitised context.
    """
    if not ctx.has_tabular_spend:
        return tasks
    # Don't inject twice
    existing_names = {t.skill_name for t in tasks}
    if _GROUP0_NAMES.issubset(existing_names):
        return tasks

    # Shift existing groups up by 3
    shifted: List[SkillTask] = []
    for t in tasks:
        shifted.append(t.model_copy(update={"parallel_group": t.parallel_group + 3}))

    # The first shifted task (group 3) depends on llm-context-builder
    if shifted:
        first = shifted[0]
        new_deps = list(first.depends_on) + ["llm-context-builder"]
        shifted[0] = first.model_copy(update={"depends_on": new_deps})

    return list(_GROUP0_SKILLS) + shifted


def _add_task(tasks: list[SkillTask], task: SkillTask) -> None:
    if any(t.skill_name == task.skill_name for t in tasks):
        return
    tasks.append(task)


def _has_capability(ctx: ObserveContext, capability: str) -> bool:
    return capability in set(ctx.query_capabilities or [])


def _finalize_plan(tasks: list[SkillTask], user_summary: str, estimated_duration: str, requires_approval: bool) -> ExecutionPlan:
    parallel_groups = max((t.parallel_group for t in tasks), default=-1) + 1 if tasks else 0
    return ExecutionPlan(
        tasks=tasks,
        total_skills=len(tasks),
        parallel_groups=parallel_groups,
        user_summary=user_summary,
        estimated_duration=estimated_duration,
        requires_approval=requires_approval,
    )


def _plan_rule_based(ctx: ObserveContext) -> ExecutionPlan:
    """Rule-based plan: map intent to skill DAG with parallel groups."""
    tasks: list[SkillTask] = []
    intent = ctx.intent_class
    ingestion_strategy = str((ctx.model_manifest or {}).get("ingestion_strategy") or "standard")

    # Conversational / question — no heavy skill pipeline.
    # If spend data is already loaded, run spend-profiler lightly to refresh
    # the profile so the response can quote current numbers.
    if intent == "general_qa":
        wants_deep_category_analysis = (
            _has_capability(ctx, "value_modeling")
            and (
                bool((ctx.explicit_category or "").strip())
                or _has_capability(ctx, "root_cause")
                or _has_capability(ctx, "working_capital")
            )
        )
        if (ctx.spend_profile_ready or ctx.has_tabular_spend) and ctx.data_quality_score > 0:
            tasks = [SkillTask(skill_name="spend-profiler", inputs={}, depends_on=[], parallel_group=0, estimated_tokens=500)]
            if wants_deep_category_analysis:
                _add_task(tasks, SkillTask(skill_name="peer-benchmarker", inputs={}, depends_on=["spend-profiler"], parallel_group=1, estimated_tokens=800))
                _add_task(tasks, SkillTask(skill_name="internal-benchmarker", inputs={}, depends_on=["spend-profiler"], parallel_group=1, estimated_tokens=600))
                _add_task(tasks, SkillTask(skill_name="payment-terms-optimizer", inputs={}, depends_on=["spend-profiler"], parallel_group=1, estimated_tokens=450))
                _add_task(tasks, SkillTask(skill_name="bva-analyzer", inputs={}, depends_on=["spend-profiler"], parallel_group=1, estimated_tokens=500))
                _add_task(tasks, SkillTask(skill_name="temporal-analyzer", inputs={}, depends_on=["spend-profiler"], parallel_group=1, estimated_tokens=500))
                if ctx.has_annual_revenue:
                    _add_task(tasks, SkillTask(skill_name="heuristic-analyzer", inputs={}, depends_on=["spend-profiler"], parallel_group=1, estimated_tokens=500))
                _add_task(tasks, SkillTask(skill_name="chart-builder", inputs={}, depends_on=["spend-profiler"], parallel_group=1, estimated_tokens=300))
                _add_task(tasks, SkillTask(skill_name="root-cause-analyzer", inputs={}, depends_on=["spend-profiler", "peer-benchmarker"], parallel_group=2, estimated_tokens=650))
                savings_deps = ["peer-benchmarker", "internal-benchmarker", "root-cause-analyzer"]
                if ctx.has_annual_revenue:
                    savings_deps.append("heuristic-analyzer")
                _add_task(tasks, SkillTask(skill_name="savings-modeler", inputs={}, depends_on=savings_deps, parallel_group=3, estimated_tokens=900))
                bridge_deps = ["peer-benchmarker", "internal-benchmarker", "savings-modeler"]
                if ctx.has_annual_revenue:
                    bridge_deps.append("heuristic-analyzer")
                _add_task(tasks, SkillTask(skill_name="value-bridge-calculator", inputs={}, depends_on=bridge_deps, parallel_group=4, estimated_tokens=700))
                _add_task(tasks, SkillTask(skill_name="data-validator", inputs={}, depends_on=["value-bridge-calculator"], parallel_group=5, estimated_tokens=200))
            elif ctx.wants_spend_visualization:
                tasks.append(
                    SkillTask(
                        skill_name="chart-builder",
                        inputs={},
                        depends_on=["spend-profiler"],
                        parallel_group=1,
                        estimated_tokens=300,
                    )
                )
            return ExecutionPlan(
                tasks=tasks,
                total_skills=len(tasks),
                parallel_groups=max((t.parallel_group for t in tasks), default=0) + 1,
                user_summary=(
                    "I'll run category-level diagnostics and value modeling to give a specific, evidence-backed answer."
                    if wants_deep_category_analysis
                    else "I'll review your spend data and answer your question."
                ),
                estimated_duration="~65 seconds" if wants_deep_category_analysis else "~10 seconds",
                requires_approval=False,
            )
        if ctx.uploaded_file_ids:
            return ExecutionPlan(
                tasks=[SkillTask(skill_name="document-contextualizer", inputs={}, depends_on=[], parallel_group=0, estimated_tokens=300)],
                total_skills=1,
                parallel_groups=1,
                user_summary="I'll review the uploaded documents and summarize key context.",
                estimated_duration="~10 seconds",
                requires_approval=False,
            )
        # No data yet — return empty plan; orchestrator will respond with guidance.
        return ExecutionPlan(
            tasks=[],
            total_skills=0,
            parallel_groups=0,
            user_summary="awaiting_data",
            estimated_duration="",
            requires_approval=False,
        )

    if intent == "upload_data":
        tasks = [SkillTask(skill_name="spend-profiler", inputs={}, depends_on=[], parallel_group=0, estimated_tokens=500)]
        if ingestion_strategy in {"timeseries_flatten", "scenario_pivot", "hybrid"}:
            _add_task(tasks, SkillTask(skill_name="bva-analyzer", inputs={}, depends_on=["spend-profiler"], parallel_group=1, estimated_tokens=500))
            _add_task(tasks, SkillTask(skill_name="temporal-analyzer", inputs={}, depends_on=["spend-profiler"], parallel_group=1, estimated_tokens=500))
        _add_task(tasks, SkillTask(skill_name="chart-builder", inputs={}, depends_on=["spend-profiler"], parallel_group=1, estimated_tokens=300))
        return ExecutionPlan(
            tasks=tasks,
            total_skills=len(tasks),
            parallel_groups=max((t.parallel_group for t in tasks), default=0) + 1,
            user_summary="I'll classify your spend model and run the right initial diagnostics based on its detected structure.",
            estimated_duration="~30 seconds",
            requires_approval=False,
        )

    if intent in {"benchmark", "value_bridge", "business_case"}:
        wants_value_modeling = _has_capability(ctx, "value_modeling")
        wants_variance = _has_capability(ctx, "variance_analysis")
        wants_temporal = _has_capability(ctx, "temporal_trend")
        wants_working_capital = _has_capability(ctx, "working_capital")
        wants_root_cause = _has_capability(ctx, "root_cause")
        wants_visual = _has_capability(ctx, "visualization")

        include_docs = ctx.has_document_files and (ctx.wants_document_context or intent in {"value_bridge", "business_case"})
        include_heuristic = ctx.has_annual_revenue
        include_value_modeling = intent in {"value_bridge", "business_case"} or wants_value_modeling
        include_business_case = intent == "business_case"
        include_exec_narrative = ctx.wants_executive_narrative or include_business_case or _has_capability(ctx, "executive_narrative")
        include_spend_chart = (
            ctx.wants_spend_visualization
            or wants_visual
            or intent in {"value_bridge", "business_case"}
            or bool((ctx.explicit_category or "").strip())
        )

        _add_task(tasks, SkillTask(skill_name="spend-profiler", inputs={}, depends_on=[], parallel_group=0, estimated_tokens=500))
        if include_docs:
            _add_task(tasks, SkillTask(skill_name="document-contextualizer", inputs={}, depends_on=[], parallel_group=0, estimated_tokens=300))

        _add_task(tasks, SkillTask(skill_name="peer-benchmarker", inputs={}, depends_on=["spend-profiler"], parallel_group=1, estimated_tokens=800))
        _add_task(tasks, SkillTask(skill_name="internal-benchmarker", inputs={}, depends_on=["spend-profiler"], parallel_group=1, estimated_tokens=600))
        if intent != "benchmark" or wants_working_capital or include_value_modeling:
            _add_task(tasks, SkillTask(skill_name="payment-terms-optimizer", inputs={}, depends_on=["spend-profiler"], parallel_group=1, estimated_tokens=450))
        if intent != "benchmark" or wants_variance or include_value_modeling:
            _add_task(tasks, SkillTask(skill_name="bva-analyzer", inputs={}, depends_on=["spend-profiler"], parallel_group=1, estimated_tokens=500))
        if intent != "benchmark" or wants_temporal or include_value_modeling:
            _add_task(tasks, SkillTask(skill_name="temporal-analyzer", inputs={}, depends_on=["spend-profiler"], parallel_group=1, estimated_tokens=500))
        if include_heuristic:
            _add_task(tasks, SkillTask(skill_name="heuristic-analyzer", inputs={}, depends_on=["spend-profiler"], parallel_group=1, estimated_tokens=500))
        if include_spend_chart:
            _add_task(tasks, SkillTask(skill_name="chart-builder", inputs={}, depends_on=["spend-profiler"], parallel_group=1, estimated_tokens=300))
        if ingestion_strategy in {"timeseries_flatten", "scenario_pivot", "hybrid"}:
            _add_task(tasks, SkillTask(skill_name="bva-analyzer", inputs={}, depends_on=["spend-profiler"], parallel_group=1, estimated_tokens=500))
            _add_task(tasks, SkillTask(skill_name="temporal-analyzer", inputs={}, depends_on=["spend-profiler"], parallel_group=1, estimated_tokens=500))

        if include_value_modeling:
            include_root_cause = wants_root_cause or intent in {"value_bridge", "business_case"}
            if include_root_cause:
                _add_task(tasks, SkillTask(skill_name="root-cause-analyzer", inputs={}, depends_on=["spend-profiler", "peer-benchmarker"], parallel_group=2, estimated_tokens=650))
            savings_deps = ["peer-benchmarker", "internal-benchmarker"]
            if include_root_cause:
                savings_deps.append("root-cause-analyzer")
            if include_heuristic:
                savings_deps.append("heuristic-analyzer")
            _add_task(tasks, SkillTask(skill_name="savings-modeler", inputs={}, depends_on=savings_deps, parallel_group=3, estimated_tokens=900))
            bridge_deps = ["peer-benchmarker", "internal-benchmarker", "savings-modeler"]
            if include_heuristic:
                bridge_deps.append("heuristic-analyzer")
            _add_task(tasks, SkillTask(skill_name="value-bridge-calculator", inputs={}, depends_on=bridge_deps, parallel_group=4, estimated_tokens=700))
            _add_task(tasks, SkillTask(skill_name="data-validator", inputs={}, depends_on=["value-bridge-calculator"], parallel_group=5, estimated_tokens=200))

            if include_business_case:
                _add_task(tasks, SkillTask(skill_name="business-case-builder", inputs={}, depends_on=["value-bridge-calculator"], parallel_group=5, estimated_tokens=1500))

            if include_exec_narrative:
                synth_deps = ["value-bridge-calculator", "data-validator"]
                if include_docs:
                    synth_deps.append("document-contextualizer")
                _add_task(
                    tasks,
                    SkillTask(
                        skill_name="analysis-synthesizer",
                        inputs={},
                        depends_on=synth_deps,
                        parallel_group=6,
                        estimated_tokens=1200,
                    ),
                )
                _add_task(
                    tasks,
                    SkillTask(
                        skill_name="executive-communication",
                        inputs={},
                        depends_on=["analysis-synthesizer"],
                        parallel_group=7,
                        estimated_tokens=900,
                    ),
                )

        if intent == "benchmark":
            summary = "I'll run spend profiling and targeted benchmark diagnostics, only adding optional skills when your context supports them."
            eta = "~35 seconds"
            requires_approval = False
        elif intent == "value_bridge":
            summary = "I'll run benchmark diagnostics, model value realization, and validate the value bridge with only the required downstream skills."
            eta = "~70 seconds"
            requires_approval = False
        else:
            summary = "I'll run full value modeling and produce a business case package with executive-ready outputs."
            eta = "~95 seconds"
            requires_approval = True
        return _finalize_plan(tasks, summary, eta, requires_approval)

    # -----------------------------------------------------------------------
    # Phase 3: Enterprise intent handlers
    # -----------------------------------------------------------------------

    if intent == "conflict_review":
        _add_task(tasks, SkillTask(
            skill_name="spend-profiler", inputs={}, depends_on=[], parallel_group=0, estimated_tokens=300,
        ))
        _add_task(tasks, SkillTask(
            skill_name="conflict-detector", inputs={}, depends_on=["spend-profiler"], parallel_group=1, estimated_tokens=600,
        ))
        return _finalize_plan(
            tasks,
            "I'll scan all uploaded data sources for TDS mismatches, GST discrepancies, vendor duplicates, "
            "intercompany inflation, and other conflicts — then surface resolution options.",
            "~25 seconds",
            False,
        )

    if intent == "consolidate":
        _add_task(tasks, SkillTask(
            skill_name="spend-profiler", inputs={}, depends_on=[], parallel_group=0, estimated_tokens=300,
        ))
        _add_task(tasks, SkillTask(
            skill_name="vendor-master-builder", inputs={}, depends_on=["spend-profiler"], parallel_group=1, estimated_tokens=400,
        ))
        _add_task(tasks, SkillTask(
            skill_name="conflict-detector", inputs={}, depends_on=["spend-profiler"], parallel_group=1, estimated_tokens=600,
        ))
        _add_task(tasks, SkillTask(
            skill_name="consolidation-analyzer", inputs={}, depends_on=["conflict-detector"], parallel_group=2, estimated_tokens=700,
        ))
        return _finalize_plan(
            tasks,
            "I'll roll up spend across all entities, eliminate intercompany transactions, "
            "and produce a consolidated group spend view with completeness check.",
            "~40 seconds",
            False,
        )

    if intent == "vendor_master":
        _add_task(tasks, SkillTask(
            skill_name="spend-profiler", inputs={}, depends_on=[], parallel_group=0, estimated_tokens=300,
        ))
        _add_task(tasks, SkillTask(
            skill_name="vendor-master-builder", inputs={}, depends_on=["spend-profiler"], parallel_group=1, estimated_tokens=500,
        ))
        _add_task(tasks, SkillTask(
            skill_name="msme-compliance-checker", inputs={}, depends_on=["vendor-master-builder"], parallel_group=2, estimated_tokens=350,
        ))
        return _finalize_plan(
            tasks,
            "I'll deduplicate vendors by GSTIN across all sources, build a canonical vendor master, "
            "and flag MSME compliance risks.",
            "~25 seconds",
            False,
        )

    if intent == "contract_review":
        _add_task(tasks, SkillTask(
            skill_name="spend-profiler", inputs={}, depends_on=[], parallel_group=0, estimated_tokens=300,
        ))
        _add_task(tasks, SkillTask(
            skill_name="contract-lifecycle-manager", inputs={}, depends_on=["spend-profiler"], parallel_group=1, estimated_tokens=500,
        ))
        _add_task(tasks, SkillTask(
            skill_name="msme-compliance-checker", inputs={}, depends_on=["spend-profiler"], parallel_group=1, estimated_tokens=350,
        ))
        return _finalize_plan(
            tasks,
            "I'll identify upcoming renewals, auto-renewal risks, exit penalty exposure, "
            "and spend blocked by current contract lock-ins.",
            "~20 seconds",
            False,
        )

    if intent == "gstr_reconcile":
        _add_task(tasks, SkillTask(
            skill_name="spend-profiler", inputs={}, depends_on=[], parallel_group=0, estimated_tokens=300,
        ))
        _add_task(tasks, SkillTask(
            skill_name="gstr-reconciler", inputs={}, depends_on=["spend-profiler"], parallel_group=1, estimated_tokens=600,
        ))
        return _finalize_plan(
            tasks,
            "I'll reconcile your AP books against GSTR-2A/2B data to identify ITC at risk "
            "and quantify the GST recovery opportunity.",
            "~25 seconds",
            False,
        )

    if intent == "zbb":
        _add_task(tasks, SkillTask(
            skill_name="spend-profiler", inputs={}, depends_on=[], parallel_group=0, estimated_tokens=300,
        ))
        _add_task(tasks, SkillTask(
            skill_name="zbb-modeler", inputs={}, depends_on=["spend-profiler"], parallel_group=1, estimated_tokens=700,
        ))
        if ctx.has_annual_revenue:
            _add_task(tasks, SkillTask(
                skill_name="heuristic-analyzer", inputs={}, depends_on=["spend-profiler"], parallel_group=1, estimated_tokens=500,
            ))
        return _finalize_plan(
            tasks,
            "I'll build a driver-based should-cost model from first principles and identify "
            "the gap between current spend and zero-based targets by category.",
            "~30 seconds",
            False,
        )

    if intent == "cost_to_serve":
        _add_task(tasks, SkillTask(skill_name="spend-profiler", inputs={}, depends_on=[], parallel_group=0, estimated_tokens=400))
        _add_task(tasks, SkillTask(skill_name="cost-to-serve-analyzer", inputs={}, depends_on=["spend-profiler"], parallel_group=1, estimated_tokens=600))
        _add_task(tasks, SkillTask(skill_name="root-cause-analyzer", inputs={}, depends_on=["spend-profiler"], parallel_group=1, estimated_tokens=700))
        return _finalize_plan(
            tasks,
            "I'll analyse cost-to-serve by segment, surface per-employee cost drivers, "
            "and identify unprofitable segments where OpEx exceeds segment revenue.",
            "~25 seconds",
            False,
        )

    return ExecutionPlan(
        tasks=[SkillTask(skill_name="spend-profiler", inputs={}, depends_on=[], parallel_group=0)],
        total_skills=1,
        parallel_groups=1,
        user_summary="I'll process your request.",
        estimated_duration="~20 seconds",
        requires_approval=False,
    )


# ---------------------------------------------------------------------------
# DAG replanner — objective-function driven, called from reflect
# ---------------------------------------------------------------------------

def _opportunity_coverage(validated: Dict[str, Any]) -> float:
    """Fraction of analysis dimensions present in validated outputs (0.0–1.0)."""
    dimensions = [
        "spend-profiler", "peer-benchmarker", "internal-benchmarker",
        "value-bridge-calculator", "savings-modeler", "root-cause-analyzer",
    ]
    filled = sum(1 for d in dimensions if d in validated)
    return round(filled / len(dimensions), 4)


def _peer_evidence_score(validated: Dict[str, Any]) -> float:
    """Quality proxy for peer benchmark evidence (0.0–1.0)."""
    peer = validated.get("peer-benchmarker", {})
    if not isinstance(peer, dict):
        return 0.0
    comps = peer.get("comparisons", [])
    if not comps:
        return 0.0
    specificity = float(peer.get("benchmark_dataset", {}).get("specificity_score") or 0.5)
    return min(1.0, specificity * (min(len(comps), 10) / 10))


def _week_feasibility(engagement_week: int, remaining_skills: List[str]) -> float:
    """Rough feasibility score based on how many weeks remain (0.0–1.0)."""
    weeks_left = max(1, 12 - engagement_week)
    # Assume ~2 new skills can realistically be added per week
    capacity = weeks_left * 2
    needed = len(remaining_skills)
    return min(1.0, capacity / max(1, needed))


def _working_capital_ratio(validated: Dict[str, Any]) -> float:
    """Ratio of WC opportunity to opex total (for WC deep-dive branch trigger)."""
    payment = validated.get("payment-terms-optimizer", {})
    profiler = validated.get("spend-profiler", {})
    if not isinstance(payment, dict) or not isinstance(profiler, dict):
        return 0.0
    wc_total = sum(
        float(opp.get("working_capital_release", 0.0) or 0.0)
        for opp in payment.get("opportunities", [])
        if isinstance(opp, dict)
    )
    opex_total = float(profiler.get("total_spend", 0.0) or 0.0)
    if opex_total <= 0:
        return 0.0
    return wc_total / opex_total


def replan(
    ctx: ObserveContext,
    validated: Dict[str, Any],
    current_plan: ExecutionPlan,
) -> tuple[ExecutionPlan, List[Dict[str, Any]]]:
    """Objective-function replanner called at each Reflect gate.

    Computes three signals:
      opportunity_coverage  — fraction of analysis dimensions filled
      peer_evidence_score   — benchmark evidence quality
      week_feasibility      — capacity remaining in engagement

    Branch decisions (logged):
      1. WC ratio > 2× opex total → swap in payment-terms deep-dive cluster
      2. peer_evidence < 0.3 → drop peer-heavy skills; rely on internal only
      3. opportunity_coverage < 0.4 → add missing core skills

    Returns (new_plan, replanner_log).  If no replanning is needed, returns
    (current_plan, []).
    """
    log: List[Dict[str, Any]] = []
    existing_names = {t.skill_name for t in current_plan.tasks}
    tasks = list(current_plan.tasks)

    opp_cov = _opportunity_coverage(validated)
    peer_ev = _peer_evidence_score(validated)
    wc_ratio = _working_capital_ratio(validated)
    remaining = [s for s in ["savings-modeler", "value-bridge-calculator", "root-cause-analyzer"] if s not in existing_names]
    week_feas = _week_feasibility(ctx.engagement_week, remaining)

    # Branch 1: Working-capital deep-dive
    if wc_ratio > 2.0 and "payment-terms-optimizer" not in existing_names:
        tasks.append(
            SkillTask(
                skill_name="payment-terms-optimizer",
                inputs={},
                depends_on=["spend-profiler"],
                parallel_group=max((t.parallel_group for t in tasks), default=0),
                estimated_tokens=450,
            )
        )
        log.append({
            "decision": "wc_deep_dive",
            "reason": f"Working-capital ratio {wc_ratio:.2f} > 2.0× opex — added payment-terms-optimizer",
            "engagement_week": ctx.engagement_week,
        })

    # Branch 2: Low peer evidence → rely on internal benchmarks
    if peer_ev < 0.30:
        tasks = [t for t in tasks if t.skill_name not in ("peer-benchmarker", "heuristic-analyzer")]
        log.append({
            "decision": "internal_only",
            "reason": f"Peer evidence score {peer_ev:.2f} < 0.30 — removed peer/heuristic skills; internal-only mode",
            "engagement_week": ctx.engagement_week,
        })

    # Branch 3: Low opportunity coverage → add missing core skills
    if opp_cov < 0.40 and week_feas > 0.3:
        core = ["spend-profiler", "peer-benchmarker", "internal-benchmarker"]
        for skill in core:
            if skill not in existing_names:
                tasks.append(
                    SkillTask(
                        skill_name=skill,
                        inputs={},
                        depends_on=[],
                        parallel_group=max((t.parallel_group for t in tasks), default=0) + 1,
                        estimated_tokens=500,
                    )
                )
                log.append({
                    "decision": "add_core_skill",
                    "reason": f"Opportunity coverage {opp_cov:.2f} < 0.40 — added missing core skill {skill}",
                    "engagement_week": ctx.engagement_week,
                })

    if not log:
        return current_plan, []

    parallel_groups = max((t.parallel_group for t in tasks), default=-1) + 1
    new_plan = ExecutionPlan(
        tasks=tasks,
        total_skills=len(tasks),
        parallel_groups=parallel_groups,
        user_summary=current_plan.user_summary + " [replanned]",
        estimated_duration=current_plan.estimated_duration,
        requires_approval=current_plan.requires_approval,
    )
    return new_plan, log


def plan(ctx: ObserveContext) -> ExecutionPlan:
    """Generate ExecutionPlan using rule-based DAG selection with Group 0 injection."""
    exec_plan = _plan_rule_based(ctx)
    # Inject Group 0 security skills when spend lines are present
    if exec_plan.tasks:
        new_tasks = _inject_group0(exec_plan.tasks, ctx)
        if new_tasks is not exec_plan.tasks:
            parallel_groups = max((t.parallel_group for t in new_tasks), default=-1) + 1
            exec_plan = ExecutionPlan(
                tasks=new_tasks,
                total_skills=len(new_tasks),
                parallel_groups=parallel_groups,
                user_summary=exec_plan.user_summary,
                estimated_duration=exec_plan.estimated_duration,
                requires_approval=exec_plan.requires_approval,
            )
    return exec_plan
