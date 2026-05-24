from __future__ import annotations

import json
from typing import Any, Dict, List

from app.config import ROOT_DIR
from app.memory import MemoryStore
from app.models import NormalizedSpendLine, SessionAnalysisState
from app.services.benchmarks import resolve_benchmark_payload
from app.skills.contracts import (
    validate_bva_output,
    validate_consolidation_output,
    validate_contract_lifecycle_output,
    validate_core_skill_outputs,
    validate_cost_to_serve_output,
    validate_msme_output,
    validate_payment_terms_output,
    validate_temporal_output,
    validate_vendor_master_output,
)
from app.skills import engine


TAXONOMY_PATH = ROOT_DIR / "skills" / "spend-profiler" / "references" / "spend_taxonomy.json"

# Module-level cache: taxonomy is read once per process and reused across requests.
_TAXONOMY: Dict[str, Any] | None = None

# Shared memory store — stateless wrapper, safe to reuse.
_memory = MemoryStore()


def load_taxonomy() -> Dict[str, Any]:
    global _TAXONOMY
    if _TAXONOMY is None:
        _TAXONOMY = json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))
    return _TAXONOMY


def run_core_pipeline(
    session_id: str,
    lines: List[NormalizedSpendLine],
    docs_text: List[str],
    industry: str,
    annual_revenue: float,
    company_name: str | None = None,
    headcount: float | None = None,
    wacc: float = 0.10,
    effective_tax_rate: float = 0.0,
    reporting_currency: str = "USD",
    engagement_id: str | None = None,
    entity_tree: Dict[str, Any] | None = None,
    segment_revenue: Dict[str, float] | None = None,
    sector_weights: Dict[str, float] | None = None,
    ingestion_summary: str | None = None,
) -> Dict[str, Any]:
    profile = engine.spend_profiler(lines)
    context = engine.document_contextualizer(docs_text)
    if ingestion_summary:
        base = str(context.get("context_summary") or "").strip()
        context["context_summary"] = f"{base}\n{ingestion_summary}".strip() if base else ingestion_summary

    # Auto-detect industry if not supplied — prefer document signals, fall back to spend patterns
    if not industry:
        industry = context.get("inferred_industry", "")
    if not industry and lines:
        total_spend = sum(x.reporting_amount for x in lines)
        industry = engine.infer_industry_from_spend(lines, total_spend)

    categories = [c.get("category_id") for c in profile.get("category_profile", []) if c.get("category_id")]
    bench_resolved = resolve_benchmark_payload(industry=industry, categories=categories, annual_revenue=annual_revenue)
    benchmarks = engine.peer_benchmarker(
        profile,
        bench_resolved["benchmark_data"],
        industry,
        annual_revenue,
        selected_dataset=bench_resolved.get("selected_dataset"),
        selection_rationale=bench_resolved.get("selection_rationale"),
    )
    internal = engine.internal_benchmarker(lines)
    heuristics = engine.heuristic_analyzer(profile, annual_revenue, headcount=headcount, reporting_currency=reporting_currency)
    root_causes = engine.root_cause_analyzer(
        profile, benchmarks, lines,
        headcount=headcount,
        industry=industry,
        annual_revenue=annual_revenue,
        reporting_currency=reporting_currency,
    )

    # Build raw rows once and feed them to savings_modeler — avoids a full
    # value_bridge_calculator call just to produce the intermediate raw_rows.
    raw_rows = engine.build_raw_rows(benchmarks, internal, heuristics)
    savings_model = engine.savings_modeler(
        {"raw_rows": raw_rows},
        root_causes,
        effective_tax_rate=effective_tax_rate,
        industry=industry,
        spend_profile=profile,
        headcount=float(headcount or 0.0),
        annual_revenue=annual_revenue,
    )
    bridge = engine.value_bridge_calculator(benchmarks, internal, heuristics, profile["total_spend"], savings_model=savings_model)
    validation = engine.data_validator(bridge)
    validate_core_skill_outputs(profile, context, benchmarks, internal, heuristics, bridge, validation)

    # --- FP&A: BvA Analyzer (runs when both actual and budget lines present) ---
    has_budget = any(x.amount_type == "budget" for x in lines)
    bva = engine.bva_analyzer(lines)
    validate_bva_output(bva)

    # --- FP&A: Temporal Analyzer (runs when fiscal_period is populated) ---
    has_periods = any(x.fiscal_period for x in lines)
    temporal = engine.temporal_analyzer(lines)
    validate_temporal_output(temporal)

    # --- FP&A: Payment Terms Optimizer (runs when payment_terms_days present) ---
    payment_terms = engine.payment_terms_optimizer(lines, wacc=wacc, industry=industry)
    validate_payment_terms_output(payment_terms)

    # --- India v2.0: Indian Tax Optimizer (runs when GST fields present) ---
    tax_opt = engine.indian_tax_optimizer(lines, effective_tax_rate=effective_tax_rate)

    # --- Phase 3: Vendor Master Builder (always runs — dedup is always useful) ---
    vendor_master = engine.vendor_master_builder(lines)
    validate_vendor_master_output(vendor_master)

    # --- Phase 3: Conflict Detector (runs when ≥2 source systems detected) ---
    source_systems = list({l.source_system_id for l in lines if l.source_system_id})
    has_multi_source = len(source_systems) >= 2
    conflict_detection = (
        engine.conflict_detector(lines) if has_multi_source
        else {"conflict_count": 0, "by_type": {}, "by_severity": {}, "unresolved": 0,
              "auto_resolvable": 0, "requires_escalation": 0, "conflicts": []}
    )

    # --- Phase 3: Contract Lifecycle Manager (runs when contract fields present) ---
    has_contracts = any(l.contract_expiry_date or l.contract_status for l in lines)
    contract_lifecycle = engine.contract_lifecycle_manager(lines)
    validate_contract_lifecycle_output(contract_lifecycle)

    # --- Phase 3: MSME Compliance Checker (runs when MSME flags present) ---
    msme_compliance = engine.msme_compliance_checker(lines)
    validate_msme_output(msme_compliance)

    # --- Phase 3: Consolidation Analyzer (runs when entity_tree provided or
    #     when legal_entity_id is populated across multiple entities) ---
    entity_ids = list({l.legal_entity_id for l in lines if l.legal_entity_id})
    has_multi_entity = len(entity_ids) >= 2 or entity_tree is not None
    consolidation = (
        engine.consolidation_analyzer(lines, entity_tree=entity_tree) if has_multi_entity
        else {"consolidation_available": False, "reason": "Single entity — no consolidation needed.",
              "group_total_spend": 0.0, "group_addressable_spend": 0.0,
              "intercompany_eliminated": 0.0, "addressable_pct": 0.0, "entity_count": 1,
              "completeness_coverage_pct": 100.0, "missing_entities": [], "entities": [], "top_categories": []}
    )
    validate_consolidation_output(consolidation)

    # --- Phase 5: Cost-to-Serve Analyzer ---
    cost_to_serve = engine.cost_to_serve_analyzer(
        lines,
        segment_revenue=segment_revenue,
        annual_revenue=annual_revenue,
        headcount=float(headcount or 0.0),
    )
    validate_cost_to_serve_output(cost_to_serve)

    skill_outputs = {
        "spend-profiler": profile,
        "document-contextualizer": context,
        "peer-benchmarker": benchmarks,
        "internal-benchmarker": internal,
        "heuristic-analyzer": heuristics,
        "root-cause-analyzer": root_causes,
        "savings-modeler": savings_model,
        "value-bridge-calculator": bridge,
        "data-validator": validation,
        # FP&A skills
        "bva-analyzer": bva,
        "temporal-analyzer": temporal,
        "payment-terms-optimizer": payment_terms,
        # India v2.0 skills
        "indian-tax-optimizer": tax_opt,
        # Phase 3: enterprise skills
        "vendor-master-builder": vendor_master,
        "conflict-detector": conflict_detection,
        "contract-lifecycle-manager": contract_lifecycle,
        "msme-compliance-checker": msme_compliance,
        "consolidation-analyzer": consolidation,
        # Phase 5
        "cost-to-serve-analyzer": cost_to_serve,
    }

    state = SessionAnalysisState(
        session_id=session_id,
        engagement_id=engagement_id,
        company_name=company_name,
        industry=industry,
        annual_revenue=annual_revenue,
        reporting_currency=reporting_currency,
        normalized_spend=lines,
        context_summary=context["context_summary"],
        skill_outputs=skill_outputs,
    )
    state_dict = state.model_dump(mode="json")
    _memory.put("session", session_id, state_dict)
    # Persist a thin manifest snapshot so get_session_manifest can recover the
    # session directory even if data/uploads/{id}/ is wiped after analysis.
    _memory.put("session_meta", session_id, {
        "session_id": session_id,
        "company_name": company_name or "",
        "industry": industry,
        "annual_revenue": annual_revenue,
        "reporting_currency": reporting_currency,
        "engagement_id": engagement_id,
    })
    if company_name:
        _memory.put(
            "user",
            company_name.lower().replace(" ", "_"),
            {
                "company_name": company_name,
                "industry": industry,
                "last_total_spend": profile["total_spend"],
                "reporting_currency": reporting_currency,
            },
        )
    _memory.put(
        "agent",
        "core_pipeline",
        {
            "last_session_id": session_id,
            "industry": industry,
            "row_count": len(lines),
            "has_budget_data": has_budget,
            "has_temporal_data": has_periods,
            "has_payment_terms": payment_terms.get("payment_terms_available", False),
            "has_multi_source": has_multi_source,
            "has_contracts": has_contracts,
            "has_msme_data": msme_compliance.get("msme_data_available", False),
            "has_multi_entity": has_multi_entity,
            "conflict_count": conflict_detection.get("conflict_count", 0),
        },
    )
    return state.model_dump(mode="json")


def run_incremental_pipeline(
    session_id: str,
    new_lines: List[NormalizedSpendLine],
) -> Dict[str, Any]:
    """Re-run spend-sensitive skills with newly uploaded lines merged into the session.

    Skips a full re-analysis: only re-runs the skills whose outputs change when
    spend rows are added (spend-profiler, internal-benchmarker, vendor-master-builder,
    msme-compliance-checker). Benchmark comparisons and root-cause analysis are left
    intact — call run_core_pipeline for a full refresh when needed.

    Returns a summary dict (not a full SessionAnalysisState) suitable for the
    incremental endpoint response.
    """
    existing = _memory.get("session", session_id)
    if not existing:
        raise ValueError(f"Session {session_id} not found — run full analysis first")

    # Reconstruct existing normalized spend lines from stored JSON.
    existing_lines: List[NormalizedSpendLine] = []
    for raw in existing.get("normalized_spend", []):
        if isinstance(raw, dict):
            existing_lines.append(NormalizedSpendLine(**raw))
        elif isinstance(raw, NormalizedSpendLine):
            existing_lines.append(raw)

    # Dedup: skip lines already present by (source_record_id, source_file_hash).
    existing_keys = {
        (l.source_record_id, l.source_file_hash)
        for l in existing_lines
        if l.source_record_id and l.source_file_hash
    }
    merged = list(existing_lines)
    added = 0
    for line in new_lines:
        key = (line.source_record_id, line.source_file_hash)
        if key and key in existing_keys:
            continue
        merged.append(line)
        existing_keys.add(key)
        added += 1

    if not added:
        return {
            "status": "no_new_lines",
            "session_id": session_id,
            "lines_added": 0,
            "total_lines": len(existing_lines),
            "updated_skills": [],
        }

    # Re-run affected skills.
    profile = engine.spend_profiler(merged)
    internal = engine.internal_benchmarker(merged)
    vendor_master = engine.vendor_master_builder(merged)
    validate_vendor_master_output(vendor_master)
    msme_compliance = engine.msme_compliance_checker(merged)
    validate_msme_output(msme_compliance)

    updated_state = dict(existing)
    updated_state["normalized_spend"] = [l.model_dump(mode="json") for l in merged]
    updated_state.setdefault("skill_outputs", {})
    updated_state["skill_outputs"]["spend-profiler"] = profile
    updated_state["skill_outputs"]["internal-benchmarker"] = internal
    updated_state["skill_outputs"]["vendor-master-builder"] = vendor_master
    updated_state["skill_outputs"]["msme-compliance-checker"] = msme_compliance

    _memory.put("session", session_id, updated_state)

    return {
        "status": "updated",
        "session_id": session_id,
        "lines_added": added,
        "total_lines": len(merged),
        "updated_skills": [
            "spend-profiler",
            "internal-benchmarker",
            "vendor-master-builder",
            "msme-compliance-checker",
        ],
        "total_spend": profile.get("total_spend", 0.0),
    }
