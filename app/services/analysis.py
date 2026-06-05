from __future__ import annotations

import json
from typing import Any, Callable, Dict, List

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
    progress_cb: Callable[[str, str], None] | None = None,
    source_files: Dict[str, List[str]] | None = None,
) -> Dict[str, Any]:
    # --- Traceability scaffolding --------------------------------------------
    # Build a human-readable, ordered trace of how the analysis is derived, with
    # the source documents each step drew on. The same narrative is streamed live
    # via progress_cb so the chat UI can show steps as they happen, then the
    # persisted trace backs the "How this analysis was derived" collapsible.
    spend_files = [f for f in (source_files or {}).get("spend", []) if f]
    context_files = [f for f in (source_files or {}).get("context", []) if f]
    analysis_trace: List[Dict[str, Any]] = []

    def _emit(phase: str, title: str, detail: str,
              sources: List[str] | None = None,
              metrics: Dict[str, Any] | None = None) -> None:
        analysis_trace.append({
            "step": len(analysis_trace) + 1,
            "phase": phase,
            "title": title,
            "detail": detail,
            "source_documents": [s for s in (sources or []) if s],
            "metrics": metrics or {},
        })
        if progress_cb:
            try:
                progress_cb("act", f"{title} — {detail}")
            except Exception:  # pragma: no cover - never let tracing break analysis
                pass

    def _money(value: float) -> str:
        return f"{reporting_currency} {value:,.0f}"

    profile = engine.spend_profiler(lines)
    total_spend = float(profile.get("total_spend", 0.0) or 0.0)
    cat_profile = [c for c in profile.get("category_profile", []) if isinstance(c, dict)]
    _emit(
        "ingest",
        "Read spend data",
        (
            f"Parsed {len(lines):,} spend lines totalling {_money(total_spend)}"
            + (f" across {len(spend_files)} file(s)." if spend_files else ".")
        ),
        sources=spend_files,
        metrics={"line_count": len(lines), "total_spend": total_spend,
                 "reporting_currency": reporting_currency},
    )
    if cat_profile:
        top = cat_profile[:3]
        top_desc = ", ".join(
            f"{c.get('category_name') or c.get('category_id')} "
            f"{(float(c.get('spend', 0.0)) / total_spend * 100):.0f}%"
            for c in top if total_spend > 0
        )
        _emit(
            "profile",
            "Profiled spend by category",
            f"Classified into {len(cat_profile)} categories"
            + (f"; top: {top_desc}." if top_desc else "."),
            sources=spend_files,
            metrics={"category_count": len(cat_profile)},
        )

    context = engine.document_contextualizer(docs_text)
    if ingestion_summary:
        base = str(context.get("context_summary") or "").strip()
        context["context_summary"] = f"{base}\n{ingestion_summary}".strip() if base else ingestion_summary

    if any(t.strip() for t in docs_text):
        constraints = [c for c in (context.get("constraints") or []) if c]
        maturity = str(context.get("procurement_maturity") or "").strip()
        ctx_inferred = str(context.get("inferred_industry") or "").strip()
        extraction_method = str(context.get("extraction_method") or "").strip()
        bits: List[str] = []
        if extraction_method:
            bits.append(f"via **{extraction_method}**")
        if ctx_inferred:
            bits.append(f"inferred sector **{ctx_inferred}** (used for benchmarking when industry unset)")
        if maturity:
            bits.append(f"procurement maturity **{maturity}**")
        if constraints:
            preview = "; ".join(str(c) for c in constraints[:3])
            suffix = f" (+{len(constraints) - 3} more)" if len(constraints) > 3 else ""
            bits.append(f"constraints ({len(constraints)}): {preview}{suffix}")
        _emit(
            "context",
            "Read context documents",
            "Extracted " + ("; ".join(bits) if bits else "qualitative context") + ".",
            sources=context_files,
            metrics={
                "constraint_count": len(constraints),
                "inferred_industry": ctx_inferred,
                "extraction_method": extraction_method,
            },
        )

    # Auto-detect industry if not supplied — prefer document signals, fall back to spend patterns
    if not industry:
        industry = context.get("inferred_industry", "")
    if not industry and lines:
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
    comparisons = [c for c in benchmarks.get("comparisons", []) if isinstance(c, dict)]
    above_median = [
        c for c in comparisons
        if str(c.get("percentile_band") or "") in ("P50-P75", "P75-P90", "P90+")
    ]
    dataset_name = ""
    bench_meta = benchmarks.get("benchmark_metadata") or {}
    if isinstance(bench_meta, dict):
        dataset_name = str(bench_meta.get("source_name") or "")
    sel_rationale = bench_resolved.get("selection_rationale") or {}
    rationale_bits: List[str] = []
    if isinstance(sel_rationale, dict):
        if sel_rationale.get("source"):
            rationale_bits.append(f"source **{sel_rationale['source']}**")
        if sel_rationale.get("pack_id"):
            rationale_bits.append(f"sector pack **{sel_rationale['pack_id']}**")
        if sel_rationale.get("score") is not None:
            rationale_bits.append(f"dataset score {sel_rationale['score']}")
        if sel_rationale.get("match_ratio") is not None:
            rationale_bits.append(f"category match {float(sel_rationale['match_ratio']):.0%}")
    rationale_text = f" Rationale: {', '.join(rationale_bits)}." if rationale_bits else ""
    _emit(
        "benchmark",
        "Benchmarked against peers",
        (
            f"Compared {len(comparisons)} categories to **{industry or 'industry'}** peers"
            + (f" using dataset **{dataset_name}**" if dataset_name else "")
            + f"; {len(above_median)} above the peer median (optimization headroom)."
            + rationale_text
        ),
        sources=spend_files,
        metrics={
            "comparison_count": len(comparisons),
            "above_median_count": len(above_median),
            "selection_rationale": sel_rationale if isinstance(sel_rationale, dict) else {},
        },
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
    rc_findings = [r for r in root_causes.get("root_cause_findings", []) if isinstance(r, dict)]
    if rc_findings:
        finding_lines: List[str] = []
        for finding in rc_findings[:3]:
            cat = str(finding.get("category_name") or finding.get("category_id") or "category")
            rc_list = finding.get("root_causes") or []
            primary = rc_list[0] if isinstance(rc_list, list) and rc_list else finding
            if isinstance(primary, dict):
                diagnosis = str(primary.get("diagnosis") or "").strip()
                lever = str(primary.get("recommended_lever") or "").strip()
                if diagnosis and lever:
                    finding_lines.append(f"**{cat}**: {diagnosis} → lever **{lever}**")
                elif diagnosis:
                    finding_lines.append(f"**{cat}**: {diagnosis}")
                else:
                    finding_lines.append(f"**{cat}**")
            else:
                finding_lines.append(f"**{cat}**")
        suffix = f" (+{len(rc_findings) - 3} more)" if len(rc_findings) > 3 else ""
        _emit(
            "root_cause",
            "Diagnosed root causes",
            (
                f"Identified {len(rc_findings)} root-cause finding(s)"
                + (f"; top drivers: {'; '.join(finding_lines)}{suffix}." if finding_lines else ".")
            ),
            sources=spend_files,
            metrics={"finding_count": len(rc_findings)},
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
        document_context=context,
        spend_lines=lines,
    )
    bridge = engine.value_bridge_calculator(benchmarks, internal, heuristics, profile["total_spend"], savings_model=savings_model)
    validation = engine.data_validator(bridge)
    validate_core_skill_outputs(profile, context, benchmarks, internal, heuristics, bridge, validation)

    initiative_list = [i for i in savings_model.get("initiatives", []) if isinstance(i, dict)]
    mid_savings = float((bridge.get("confidence_bands", {}) or {}).get("mid", 0.0) or 0.0)

    def _initiative_savings(item: Dict[str, Any]) -> float:
        net = item.get("net_savings") or {}
        if isinstance(net, dict):
            for key in ("total_3yr", "y3", "y1"):
                val = net.get(key)
                if val is not None:
                    try:
                        return float(val)
                    except (TypeError, ValueError):
                        continue
        try:
            return float(item.get("annualized_run_rate_savings") or 0.0)
        except (TypeError, ValueError):
            return 0.0

    ranked_initiatives = sorted(
        initiative_list,
        key=_initiative_savings,
        reverse=True,
    )
    initiative_bits: List[str] = []
    for item in ranked_initiatives[:3]:
        name = str(item.get("lever_name") or item.get("lever") or "initiative")
        amt = _initiative_savings(item)
        if amt > 0:
            initiative_bits.append(f"**{name}** {_money(amt)}")
        else:
            initiative_bits.append(f"**{name}**")
    initiative_suffix = (
        f" (+{len(initiative_list) - 3} more)" if len(initiative_list) > 3 else ""
    )
    _emit(
        "savings",
        "Modelled savings opportunities",
        (
            f"Built {len(initiative_list)} initiative(s); mid-case portfolio savings "
            f"{_money(mid_savings)}"
            + (f" (~{(mid_savings / total_spend * 100):.1f}% of spend)" if total_spend > 0 else "")
            + (f"; leading initiatives: {', '.join(initiative_bits)}{initiative_suffix}." if initiative_bits else ".")
        ),
        sources=spend_files,
        metrics={"initiative_count": len(initiative_list), "mid_case_savings": mid_savings},
    )

    # --- Strategic skills (board-deck / CFO-brief / business-case consumers) ---
    # scenario surface, shareholder-value bridge, BRSR co-benefits, assumption
    # register, and peer disclosure mining. These previously ran in neither
    # pipeline, so downstream board-deck / CFO-brief sections that read them
    # silently rendered empty. Wiring them here populates those sections.
    initiatives = savings_model.get("initiatives", [])
    base_savings_mid = float(bridge.get("confidence_bands", {}).get("mid", 0.0) or 0.0)
    assumptions = engine.assumption_register(lines)
    scenarios = engine.scenario_modeler(
        lines,
        initiatives=initiatives,
        base_savings=base_savings_mid,
        wacc=wacc,
        effective_tax_rate=effective_tax_rate,
    )
    shareholder_bridge = engine.value_to_shareholder_bridge(
        lines,
        initiatives=initiatives,
        annual_revenue=annual_revenue,
        wacc=wacc,
    )
    brsr_cobenefits = engine.brsr_cobenefit_calculator(lines, initiatives=initiatives)
    peer_disclosures = engine.peer_disclosure_miner(lines, peer_set=benchmarks.get("peer_set"))

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

    # --- SME Critique — evidence qualification for savings initiatives ---
    # Runs after savings_modeler and contract_lifecycle_manager are both available.
    sme_critique = engine.sme_critique_analyzer(
        savings_model,
        profile,
        benchmarks,
        root_causes,
        contract_lifecycle,
    )

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
        # SME critique — evidence maturity and probe questions
        "sme-critique": sme_critique,
        # Strategic skills feeding board-deck / CFO-brief / business-case
        "assumption-register": assumptions,
        "scenario-modeler": scenarios,
        "value-to-shareholder-bridge": shareholder_bridge,
        "brsr-cobenefit-calculator": brsr_cobenefits,
        "peer-disclosure-miner": peer_disclosures,
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
        analysis_trace=analysis_trace,
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
