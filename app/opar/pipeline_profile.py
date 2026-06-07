"""Declarative pipeline profiles + a thin executor over the skill dispatch registry.

This is the single source of truth for *which* skills run together and *in what
order*. Both execution paths consume it:

* the batch path (`app/services/analysis.py::run_core_pipeline`) runs the FULL
  profile and layers its analysis-trace on top via the ``on_complete`` hook;
* the chat planner (`app/opar/plan.py`) maps an intent to a profile so chat and
  batch share one definition instead of two hand-wired skill graphs.

The executor reuses the dispatch handlers (`app/skills/dispatch.invoke_skill`),
so skill *parameters* live in exactly one place. Conditional skills are modelled
declaratively in ``GATING`` with the same stub outputs the batch path used, so a
gated-off skill yields an identical placeholder.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Tuple

from app.skills.dispatch import SkillContext, invoke_skill


class PipelineProfile(str, Enum):
    """Named bundles of skills run together for a given purpose."""

    FULL = "full"              # everything — batch /api/analyze
    BENCHMARK = "benchmark"    # profiling + benchmarkers + FP&A diagnostics
    VALUE_BRIDGE = "value_bridge"  # benchmark + savings modelling chain
    INCREMENTAL = "incremental"    # spend-sensitive re-run only


# Ordered skill lists. Order matters: a handler reads upstream results via
# ``ctx.prior(...)``, so dependencies must appear earlier in the list.
_BENCHMARK_SKILLS: List[str] = [
    "spend-profiler",
    "document-contextualizer",
    "peer-benchmarker",
    "internal-benchmarker",
    "heuristic-analyzer",
    "bva-analyzer",
    "temporal-analyzer",
    "payment-terms-optimizer",
]

_VALUE_BRIDGE_SKILLS: List[str] = _BENCHMARK_SKILLS + [
    "root-cause-analyzer",
    "savings-modeler",
    "value-bridge-calculator",
    "data-validator",
]

# The FULL batch graph (mirrors the historical run_core_pipeline sequence).
_FULL_SKILLS: List[str] = [
    "spend-profiler",
    "document-contextualizer",
    "peer-benchmarker",
    "internal-benchmarker",
    "heuristic-analyzer",
    "root-cause-analyzer",
    "savings-modeler",
    "value-bridge-calculator",
    "data-validator",
    # strategic (board-deck / CFO-brief / business-case consumers)
    "assumption-register",
    "scenario-modeler",
    "value-to-shareholder-bridge",
    "brsr-cobenefit-calculator",
    "peer-disclosure-miner",
    # FP&A diagnostics
    "bva-analyzer",
    "temporal-analyzer",
    "payment-terms-optimizer",
    # India v2.0
    "indian-tax-optimizer",
    # enterprise
    "vendor-master-builder",
    "conflict-detector",          # gated: ≥2 source systems
    "contract-lifecycle-manager",
    "msme-compliance-checker",
    "consolidation-analyzer",     # gated: ≥2 legal entities or entity_tree
    # phase 5
    "cost-to-serve-analyzer",
    # document-aware evidence (after savings + contract-lifecycle)
    "evidence-gatherer",
    # evidence qualification (after evidence gatherer)
    "sme-critique",
]

_INCREMENTAL_SKILLS: List[str] = [
    "spend-profiler",
    "internal-benchmarker",
    "vendor-master-builder",
    "msme-compliance-checker",
]

PROFILE_SKILLS: Dict[PipelineProfile, List[str]] = {
    PipelineProfile.FULL: _FULL_SKILLS,
    PipelineProfile.BENCHMARK: _BENCHMARK_SKILLS,
    PipelineProfile.VALUE_BRIDGE: _VALUE_BRIDGE_SKILLS,
    PipelineProfile.INCREMENTAL: _INCREMENTAL_SKILLS,
}


# ── Conditional (gated) skills ───────────────────────────────────────────────
# When the predicate is False the skill is skipped and its declared stub output
# is used instead — identical to the placeholder run_core_pipeline emitted.

@dataclass(frozen=True)
class Gate:
    predicate: Callable[[SkillContext], bool]
    stub: Callable[[], Dict[str, Any]]


def _has_multi_source(ctx: SkillContext) -> bool:
    return len({ln.source_system_id for ln in ctx.lines if ln.source_system_id}) >= 2


def _has_multi_entity(ctx: SkillContext) -> bool:
    entity_ids = {ln.legal_entity_id for ln in ctx.lines if ln.legal_entity_id}
    return len(entity_ids) >= 2 or ctx.entity_tree is not None


def _conflict_stub() -> Dict[str, Any]:
    return {
        "conflict_count": 0, "by_type": {}, "by_severity": {}, "unresolved": 0,
        "auto_resolvable": 0, "requires_escalation": 0, "conflicts": [],
    }


def _consolidation_stub() -> Dict[str, Any]:
    return {
        "consolidation_available": False,
        "reason": "Single entity — no consolidation needed.",
        "group_total_spend": 0.0, "group_addressable_spend": 0.0,
        "intercompany_eliminated": 0.0, "addressable_pct": 0.0, "entity_count": 1,
        "completeness_coverage_pct": 100.0, "missing_entities": [], "entities": [],
        "top_categories": [],
    }


GATING: Dict[str, Gate] = {
    "conflict-detector": Gate(_has_multi_source, _conflict_stub),
    "consolidation-analyzer": Gate(_has_multi_entity, _consolidation_stub),
}


# ── Intent → profile map (removed — agent controller + plan._DEP_MAP supersede) ──


# ── Executor ─────────────────────────────────────────────────────────────────

OnComplete = Callable[[str, Dict[str, Any]], None]


def run_profile(
    profile: PipelineProfile,
    ctx: SkillContext,
    *,
    on_complete: OnComplete | None = None,
    gating: bool = True,
    skills: List[str] | None = None,
) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, str]]:
    """Run a profile's skills in order through the dispatch registry.

    Results are accumulated into ``ctx.prior_results`` so each handler can read
    its upstream dependencies. ``on_complete(name, output)`` fires after every
    skill (including gated stubs) — the batch path uses it to stream progress and
    build its analysis trace. Returns ``(outputs, degraded_reasons)``.
    """
    skill_list = skills if skills is not None else PROFILE_SKILLS[profile]
    outputs = ctx.prior_results  # shared dict — handlers read priors from it
    degraded: Dict[str, str] = {}
    for name in skill_list:
        gate = GATING.get(name)
        if gating and gate is not None and not gate.predicate(ctx):
            output: Dict[str, Any] = gate.stub()
        else:
            output, reason = invoke_skill(name, ctx)
            if reason:
                degraded[name] = reason
        outputs[name] = output
        if on_complete is not None:
            on_complete(name, output)
    return outputs, degraded
