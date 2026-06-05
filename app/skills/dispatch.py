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

from dataclasses import dataclass
from typing import Any, Callable, Dict, List

from app.models import NormalizedSpendLine
from app.opar.transaction_examples import build_transaction_examples_from_lines


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
    wacc: float | None = None
    effective_tax_rate: float | None = None
    reporting_currency: str = "USD"
    entity_tree: Dict[str, Any] | None = None
    segment_revenue: Dict[str, float] | None = None
    sector_weights: Dict[str, float] | None = None

    # ── Convenience accessors ───────────────────────────────────────────────

    @property
    def industry(self) -> str:
        return self.manifest.get("industry") or ""

    @property
    def annual_revenue(self) -> float:
        return float(self.manifest.get("annual_revenue") or 0.0)

    @property
    def discount_rate(self) -> float:
        return float(
            self.wacc
            if self.wacc is not None
            else self.manifest.get("wacc")
            or 0.10
        )

    @property
    def tax_rate(self) -> float:
        return float(
            self.effective_tax_rate
            if self.effective_tax_rate is not None
            else self.manifest.get("effective_tax_rate")
            or 0.0
        )

    @property
    def company_name(self) -> str | None:
        return self.manifest.get("company_name")

    def prior(self, skill: str) -> Dict[str, Any]:
        """Return a prior skill result, or an empty dict if not yet run."""
        return self.prior_results.get(skill, {})

    @property
    def model_manifest(self) -> Dict[str, Any]:
        return self.manifest.get("model_manifest", {}) if isinstance(self.manifest, dict) else {}

    @property
    def document_context(self) -> Dict[str, Any]:
        context = self.prior("document-contextualizer")
        if context:
            return context
        if self.docs_text:
            return _engine.document_contextualizer(self.docs_text)
        return {}


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
    return build_transaction_examples_from_lines(
        lines,
        max_categories=max_categories,
        max_examples_per_category=max_examples_per_category,
    )


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
    out = _engine.document_contextualizer(ctx.docs_text)
    # Fold an ingestion summary (parser notes) into the context summary when one
    # was threaded through the manifest, so downstream skills and the trace see it.
    ingestion_summary = ctx.manifest.get("ingestion_summary")
    if ingestion_summary:
        base = str(out.get("context_summary") or "").strip()
        out["context_summary"] = f"{base}\n{ingestion_summary}".strip() if base else ingestion_summary
    return out, None


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
        wacc=ctx.discount_rate,
        industry=ctx.industry or "default",
    ), None


@register("heuristic-analyzer")
def _heuristic_analyzer(ctx: SkillContext) -> tuple[Dict[str, Any], str | None]:
    profile = _get_profile(ctx)
    return _engine.heuristic_analyzer(
        profile,
        ctx.annual_revenue,
        headcount=ctx.headcount,
        reporting_currency=ctx.reporting_currency,
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
        industry=ctx.industry,
        annual_revenue=ctx.annual_revenue,
        reporting_currency=ctx.reporting_currency,
    ), None


# ── Tier 2: savings modelling ────────────────────────────────────────────────

@register("savings-modeler")
def _savings_modeler(ctx: SkillContext) -> tuple[Dict[str, Any], str | None]:
    peer = ctx.prior("peer-benchmarker")
    internal = ctx.prior("internal-benchmarker")
    heuristic = ctx.prior("heuristic-analyzer")
    raw_rows = _engine.build_raw_rows(peer, internal, heuristic)
    root = ctx.prior("root-cause-analyzer")
    profile = _get_profile(ctx)
    return _engine.savings_modeler(
        {"raw_rows": raw_rows},
        root,
        discount_rate=ctx.discount_rate,
        effective_tax_rate=ctx.tax_rate,
        industry=ctx.industry,
        spend_profile=profile,
        headcount=float(ctx.headcount or 0.0),
        annual_revenue=ctx.annual_revenue,
        document_context=ctx.document_context,
        spend_lines=ctx.lines,
    ), None


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


@register("sme-critique")
def _sme_critique(ctx: SkillContext) -> tuple[Dict[str, Any], str | None]:
    savings_model = ctx.prior("savings-modeler")
    profile = _get_profile(ctx)
    benchmarks = ctx.prior("peer-benchmarker")
    root_causes = ctx.prior("root-cause-analyzer")
    contract_lifecycle = ctx.prior("contract-lifecycle-manager")
    if not contract_lifecycle and ctx.lines:
        contract_lifecycle = _engine.contract_lifecycle_manager(ctx.lines)
    return _engine.sme_critique_analyzer(
        savings_model,
        profile,
        benchmarks,
        root_causes,
        contract_lifecycle,
    ), None


# ── Tier 3: charts & reporting ───────────────────────────────────────────────

@register("chart-builder")
def _chart_builder(ctx: SkillContext) -> tuple[Dict[str, Any], str | None]:
    from app.services.spend_charts import build_spend_profile_chart_html  # lazy

    profile = _get_profile(ctx)
    chart_plan = _engine.chart_builder(profile, user_message=ctx.user_message or None)
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
        from app.services.document_index import retrieve_context  # lazy

        retrieved = retrieve_context(
            ctx.manifest.get("engagement_id") or "", ctx.user_message
        ) or None
        synthesized, degraded_reason = synthesize_analysis_claude_with_meta(
            user_message=ctx.user_message,
            manifest=ctx.manifest,
            model_manifest=ctx.model_manifest,
            skill_outputs=ctx.prior_results,
            docs_text=ctx.docs_text,
            transaction_examples=_build_transaction_examples(ctx.lines),
            deep_research_summary=ctx.manifest.get("deep_research_summary") or None,
            retrieved_context=retrieved,
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


# ── Group 0: security & context preparation ──────────────────────────────────

@register("pii-stripper")
def _pii_stripper(ctx: SkillContext) -> tuple[Dict[str, Any], str | None]:
    return _engine.pii_stripper(ctx.lines), None


@register("data-classifier")
def _data_classifier(ctx: SkillContext) -> tuple[Dict[str, Any], str | None]:
    return _engine.data_classifier(ctx.lines, skill_outputs=ctx.prior_results), None


@register("llm-context-builder")
def _llm_context_builder(ctx: SkillContext) -> tuple[Dict[str, Any], str | None]:
    classification = ctx.prior("data-classifier") or None
    return _engine.llm_context_builder(ctx.prior_results, classification=classification), None


# ── Context & assumption tracking ───────────────────────────────────────────

@register("assumption-register")
def _assumption_register(ctx: SkillContext) -> tuple[Dict[str, Any], str | None]:
    return _engine.assumption_register(ctx.lines), None


# ── Compliance & ESG ─────────────────────────────────────────────────────────

@register("indian-tax-optimizer")
def _indian_tax_optimizer(ctx: SkillContext) -> tuple[Dict[str, Any], str | None]:
    return _engine.indian_tax_optimizer(ctx.lines, effective_tax_rate=ctx.tax_rate), None


@register("brsr-cobenefit-calculator")
def _brsr_cobenefit_calculator(ctx: SkillContext) -> tuple[Dict[str, Any], str | None]:
    initiatives, _wacc, _tax_rate, _base = _portfolio_inputs(ctx)
    return _engine.brsr_cobenefit_calculator(ctx.lines, initiatives=initiatives), None


# ── Strategic analytics ───────────────────────────────────────────────────────

def _portfolio_inputs(ctx: SkillContext) -> tuple[list, float, float, float]:
    """Shared inputs for strategic skills: (initiatives, wacc, tax_rate, base_savings_mid)."""
    savings = ctx.prior("savings-modeler")
    initiatives = savings.get("initiatives", []) if isinstance(savings, dict) else []
    wacc = ctx.discount_rate
    tax_rate = ctx.tax_rate
    bridge = ctx.prior("value-bridge-calculator")
    base_savings_mid = float(bridge.get("confidence_bands", {}).get("mid", 0.0) or 0.0) if isinstance(bridge, dict) else 0.0
    return initiatives, wacc, tax_rate, base_savings_mid


@register("scenario-modeler")
def _scenario_modeler(ctx: SkillContext) -> tuple[Dict[str, Any], str | None]:
    initiatives, wacc, tax_rate, base_savings_mid = _portfolio_inputs(ctx)
    return _engine.scenario_modeler(
        ctx.lines,
        initiatives=initiatives,
        base_savings=base_savings_mid,
        wacc=wacc,
        effective_tax_rate=tax_rate,
    ), None


@register("value-to-shareholder-bridge")
def _value_to_shareholder_bridge(ctx: SkillContext) -> tuple[Dict[str, Any], str | None]:
    initiatives, wacc, _tax_rate, _base = _portfolio_inputs(ctx)
    return _engine.value_to_shareholder_bridge(
        ctx.lines,
        initiatives=initiatives,
        annual_revenue=ctx.annual_revenue,
        wacc=wacc,
    ), None


@register("peer-disclosure-miner")
def _peer_disclosure_miner(ctx: SkillContext) -> tuple[Dict[str, Any], str | None]:
    bench = ctx.prior("peer-benchmarker")
    peer_set = bench.get("peer_set") if bench else None
    return _engine.peer_disclosure_miner(ctx.lines, peer_set=peer_set), None


# ── Enterprise: data quality & multi-entity ──────────────────────────────────

@register("conflict-detector")
def _conflict_detector(ctx: SkillContext) -> tuple[Dict[str, Any], str | None]:
    return _engine.conflict_detector(ctx.lines), None


@register("vendor-master-builder")
def _vendor_master_builder(ctx: SkillContext) -> tuple[Dict[str, Any], str | None]:
    return _engine.vendor_master_builder(ctx.lines), None


@register("consolidation-analyzer")
def _consolidation_analyzer(ctx: SkillContext) -> tuple[Dict[str, Any], str | None]:
    entity_tree = ctx.manifest.get("entity_tree")
    return _engine.consolidation_analyzer(ctx.lines, entity_tree=entity_tree), None


@register("msme-compliance-checker")
def _msme_compliance_checker(ctx: SkillContext) -> tuple[Dict[str, Any], str | None]:
    return _engine.msme_compliance_checker(ctx.lines), None


@register("contract-lifecycle-manager")
def _contract_lifecycle_manager(ctx: SkillContext) -> tuple[Dict[str, Any], str | None]:
    return _engine.contract_lifecycle_manager(ctx.lines), None


@register("gstr-reconciler")
def _gstr_reconciler(ctx: SkillContext) -> tuple[Dict[str, Any], str | None]:
    gstr_2a = ctx.manifest.get("gstr_2a_data")
    return _engine.gstr_reconciler(ctx.lines, gstr_2a=gstr_2a), None


@register("zbb-modeler")
def _zbb_modeler(ctx: SkillContext) -> tuple[Dict[str, Any], str | None]:
    profile = _get_profile(ctx)
    drivers = (
        {"categories": profile.get("category_profile")}
        if profile.get("category_profile")
        else None
    )
    return _engine.zbb_modeler(ctx.lines, drivers=drivers), None


@register("cost-to-serve-analyzer")
def _cost_to_serve_analyzer(ctx: SkillContext) -> tuple[Dict[str, Any], str | None]:
    return _engine.cost_to_serve_analyzer(
        ctx.lines,
        segment_revenue=ctx.segment_revenue,
        annual_revenue=ctx.annual_revenue,
        headcount=ctx.headcount or 0.0,
    ), None


# ── Output & reporting ────────────────────────────────────────────────────────

@register("dashboard-builder")
def _dashboard_builder(ctx: SkillContext) -> tuple[Dict[str, Any], str | None]:
    from app.services.dashboard import build_dashboard_html  # lazy

    session_key = ctx.manifest.get("session_id") or "session"
    analysis = {
        "company_name": ctx.company_name,
        "industry": ctx.industry,
        "annual_revenue": ctx.annual_revenue,
        "skill_outputs": ctx.prior_results,
    }
    path = build_dashboard_html(analysis, filename=f"{session_key}_dashboard.html")
    return {"dashboard_url": f"/api/v1/exports/{path.name}", "filename": path.name}, None


@register("export-formatter")
def _export_formatter(ctx: SkillContext) -> tuple[Dict[str, Any], str | None]:
    from app.services.pmo_export import build_pmo_data, export_pmo_xlsx  # lazy
    from app.services.pipeline import pipeline_summary as get_pipeline_summary  # lazy

    # build_pmo_data(pipeline_summary, initiatives, *, company_name=...): the
    # initiative tracker is sourced from the savings-modeler portfolio, and the
    # KPI headline from the live pipeline summary.
    savings = ctx.prior("savings-modeler")
    initiatives = savings.get("initiatives", []) if isinstance(savings, dict) else []
    summary = get_pipeline_summary()
    pmo_data = build_pmo_data(summary, initiatives, company_name=ctx.company_name or "Client")
    session_key = ctx.manifest.get("session_id") or "session"
    path = export_pmo_xlsx(pmo_data, filename=f"{session_key}_pmo_export.xlsx")
    return {"export_url": f"/api/v1/exports/{path.name}", "filename": path.name}, None
