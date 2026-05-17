"""Skill dispatch registry — T2-2.

Replaces the 130-line if/elif switch in app/opar/act._invoke_skill with a
clean handler map (Fowler, *Refactoring* §12.6 — Replace Conditional with
Polymorphism).

Usage
-----
From act.py::

    from app.skills.dispatch import invoke_skill, SkillContext
    ctx = SkillContext(lines=lines, docs_text=docs_text, ...)
    output, degraded = invoke_skill(task.skill_name, ctx)

Adding a new skill
------------------
1. Write a handler function with signature
   ``handler(ctx: SkillContext) -> tuple[dict, str | None]``
2. Decorate it with ``@register("my-new-skill")``.
No changes to act.py are required.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List

from app.models import NormalizedSpendLine


# ---------------------------------------------------------------------------
# Context dataclass + registry primitives
# ---------------------------------------------------------------------------

@dataclass
class SkillContext:
    """Standardised context bundle passed to every skill handler."""

    lines: List[NormalizedSpendLine]
    docs_text: List[str]
    manifest: dict
    prior_results: Dict[str, Dict[str, Any]]
    user_message: str = ""
    headcount: float | None = None

    # ── Convenience accessors ───────────────────────────────────────────────

    @property
    def industry(self) -> str:
        return self.manifest.get("industry") or ""

    @property
    def annual_revenue(self) -> float:
        return float(self.manifest.get("annual_revenue") or 0.0)

    @property
    def company_name(self) -> str | None:
        return self.manifest.get("company_name")

    def prior(self, skill: str) -> Dict[str, Any]:
        """Return a prior skill result, or an empty dict if not yet run."""
        return self.prior_results.get(skill, {})

    @property
    def model_manifest(self) -> Dict[str, Any]:
        return self.manifest.get("model_manifest", {}) if isinstance(self.manifest, dict) else {}


SkillHandler = Callable[[SkillContext], tuple[Dict[str, Any], str | None]]

_REGISTRY: Dict[str, SkillHandler] = {}


def register(name: str) -> Callable[[SkillHandler], SkillHandler]:
    """Decorator — register a handler under the given skill *name*."""
    def decorator(fn: SkillHandler) -> SkillHandler:
        _REGISTRY[name] = fn
        return fn
    return decorator


def invoke_skill(name: str, ctx: SkillContext) -> tuple[Dict[str, Any], str | None]:
    """Dispatch *name* to its registered handler.

    Returns ``(output_dict, degraded_reason | None)``.
    Raises ``KeyError`` for unrecognised skill names.
    """
    handler = _REGISTRY.get(name)
    if handler is None:
        raise KeyError(
            f"Unknown skill: '{name}'. Registered skills: {sorted(_REGISTRY)}"
        )
    return handler(ctx)


def registered_skills() -> List[str]:
    """Return sorted list of all registered skill names."""
    return sorted(_REGISTRY)


# ---------------------------------------------------------------------------
# Internal helpers (shared across handlers)
# ---------------------------------------------------------------------------

def _get_profile(ctx: SkillContext) -> Dict[str, Any]:
    """Return spend-profiler output; runs on-demand if not in prior_results."""
    from app.skills import engine  # lazy import — engine is a large module

    profile = ctx.prior("spend-profiler")
    if not profile and ctx.lines:
        profile = engine.spend_profiler(ctx.lines)
    return profile


def _get_bench_resolved(ctx: SkillContext) -> Dict[str, Any]:
    from app.services.benchmarks import resolve_benchmark_payload  # lazy

    profile = _get_profile(ctx)
    categories = [
        c.get("category_id")
        for c in profile.get("category_profile", [])
        if c.get("category_id")
    ]
    return resolve_benchmark_payload(
        industry=ctx.industry,
        categories=categories,
        annual_revenue=ctx.annual_revenue,
    )


def _build_transaction_examples(
    lines: List[NormalizedSpendLine],
    max_categories: int = 8,
    max_examples_per_category: int = 3,
) -> Dict[str, list]:
    """Compact per-category spend examples for LLM narrative grounding."""
    grouped: Dict[str, List[NormalizedSpendLine]] = {}
    for line in lines:
        grouped.setdefault(line.category_id, []).append(line)
    out: Dict[str, list] = {}
    for category_id, cat_lines in grouped.items():
        top = sorted(cat_lines, key=lambda x: float(x.amount or 0.0), reverse=True)[
            :max_examples_per_category
        ]
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
    limited = sorted(
        out.items(),
        key=lambda kv: sum(e["amount"] for e in kv[1]),
        reverse=True,
    )[:max_categories]
    return dict(limited)


# ---------------------------------------------------------------------------
# Skill handlers — one per skill, decorated with @register
# ---------------------------------------------------------------------------

from app.skills import engine as _engine  # noqa: E402  (after primitives)


# ── Tier 0: raw data ingestion ───────────────────────────────────────────────

@register("spend-profiler")
def _spend_profiler(ctx: SkillContext) -> tuple[Dict[str, Any], str | None]:
    return _engine.spend_profiler(ctx.lines), None


@register("document-contextualizer")
def _document_contextualizer(ctx: SkillContext) -> tuple[Dict[str, Any], str | None]:
    return _engine.document_contextualizer(ctx.docs_text), None


# ── Tier 1: FP&A analytics ──────────────────────────────────────────────────

@register("bva-analyzer")
def _bva_analyzer(ctx: SkillContext) -> tuple[Dict[str, Any], str | None]:
    return _engine.bva_analyzer(ctx.lines), None


@register("temporal-analyzer")
def _temporal_analyzer(ctx: SkillContext) -> tuple[Dict[str, Any], str | None]:
    return _engine.temporal_analyzer(ctx.lines), None


@register("payment-terms-optimizer")
def _payment_terms_optimizer(ctx: SkillContext) -> tuple[Dict[str, Any], str | None]:
    return _engine.payment_terms_optimizer(
        ctx.lines,
        industry=ctx.industry or "default",
    ), None


@register("heuristic-analyzer")
def _heuristic_analyzer(ctx: SkillContext) -> tuple[Dict[str, Any], str | None]:
    profile = _get_profile(ctx)
    return _engine.heuristic_analyzer(
        profile,
        ctx.annual_revenue,
        headcount=ctx.headcount,
    ), None


@register("internal-benchmarker")
def _internal_benchmarker(ctx: SkillContext) -> tuple[Dict[str, Any], str | None]:
    return _engine.internal_benchmarker(ctx.lines), None


@register("peer-benchmarker")
def _peer_benchmarker(ctx: SkillContext) -> tuple[Dict[str, Any], str | None]:
    profile = _get_profile(ctx)
    bench = _get_bench_resolved(ctx)
    return _engine.peer_benchmarker(
        profile,
        bench["benchmark_data"],
        ctx.industry,
        ctx.annual_revenue,
        selected_dataset=bench.get("selected_dataset"),
        selection_rationale=bench.get("selection_rationale"),
    ), None


@register("root-cause-analyzer")
def _root_cause_analyzer(ctx: SkillContext) -> tuple[Dict[str, Any], str | None]:
    profile = _get_profile(ctx)
    peer = ctx.prior("peer-benchmarker")
    return _engine.root_cause_analyzer(
        profile,
        peer,
        ctx.lines,
        headcount=ctx.headcount,
    ), None


# ── Tier 2: savings modelling ────────────────────────────────────────────────

@register("savings-modeler")
def _savings_modeler(ctx: SkillContext) -> tuple[Dict[str, Any], str | None]:
    peer = ctx.prior("peer-benchmarker")
    internal = ctx.prior("internal-benchmarker")
    heuristic = ctx.prior("heuristic-analyzer")
    raw_rows = _engine.build_raw_rows(peer, internal, heuristic)
    root = ctx.prior("root-cause-analyzer")
    return _engine.savings_modeler({"raw_rows": raw_rows}, root), None


@register("value-bridge-calculator")
def _value_bridge_calculator(ctx: SkillContext) -> tuple[Dict[str, Any], str | None]:
    profile = _get_profile(ctx)
    peer = ctx.prior("peer-benchmarker")
    internal = ctx.prior("internal-benchmarker")
    heuristic = ctx.prior("heuristic-analyzer")
    total = profile.get("total_spend", 0.0)
    savings_model = ctx.prior_results.get("savings-modeler")
    return _engine.value_bridge_calculator(
        peer,
        internal,
        heuristic,
        total,
        savings_model=savings_model,
    ), None


@register("data-validator")
def _data_validator(ctx: SkillContext) -> tuple[Dict[str, Any], str | None]:
    bridge = ctx.prior("value-bridge-calculator")
    return _engine.data_validator(bridge), None


# ── Tier 3: charts & reporting ───────────────────────────────────────────────

@register("chart-builder")
def _chart_builder(ctx: SkillContext) -> tuple[Dict[str, Any], str | None]:
    from app.services.spend_charts import build_spend_profile_chart_html  # lazy

    profile = _get_profile(ctx)
    chart_plan = _engine.chart_builder(profile)
    session_key = (
        ctx.manifest.get("session_id")
        or ctx.manifest.get("turn_id")
        or "session"
    )
    chart_filename = f"{session_key}_spend_profile_chart.html"
    chart_path = build_spend_profile_chart_html(profile, chart_plan, filename=chart_filename)
    return {**chart_plan, "chart_url": f"/api/exports/{chart_path.name}"}, None


@register("business-case-builder")
def _business_case_builder(ctx: SkillContext) -> tuple[Dict[str, Any], str | None]:
    from app.services.business_case import build_business_case  # lazy

    profile = _get_profile(ctx)
    bridge = ctx.prior("value-bridge-calculator")
    analysis = {
        "company_name": ctx.company_name,
        "industry": ctx.industry,
        "annual_revenue": ctx.annual_revenue,
        "skill_outputs": {
            "value-bridge-calculator": bridge,
            "spend-profiler": profile,
        },
    }
    return {"business_case": build_business_case(analysis)}, None


# ── Tier 4: LLM synthesis (graceful fallback on provider failure) ────────────

@register("analysis-synthesizer")
def _analysis_synthesizer(ctx: SkillContext) -> tuple[Dict[str, Any], str | None]:
    try:
        from app.opar.claude_client import synthesize_analysis_claude_with_meta  # lazy

        synthesized, degraded_reason = synthesize_analysis_claude_with_meta(
            user_message=ctx.user_message,
            manifest=ctx.manifest,
            model_manifest=ctx.model_manifest,
            skill_outputs=ctx.prior_results,
            docs_text=ctx.docs_text,
            transaction_examples=_build_transaction_examples(ctx.lines),
        )
        return (synthesized or {}), degraded_reason
    except Exception:
        return {}, "provider_unavailable"


@register("executive-communication")
def _executive_communication(ctx: SkillContext) -> tuple[Dict[str, Any], str | None]:
    try:
        from app.opar.claude_client import draft_executive_communication_claude_with_meta  # lazy

        drafted, degraded_reason = draft_executive_communication_claude_with_meta(
            user_message=ctx.user_message,
            manifest=ctx.manifest,
            model_manifest=ctx.model_manifest,
            skill_outputs=ctx.prior_results,
            transaction_examples=_build_transaction_examples(ctx.lines),
        )
        return (drafted or {}), degraded_reason
    except Exception:
        return {}, "provider_unavailable"
