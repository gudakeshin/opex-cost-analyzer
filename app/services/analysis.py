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
from app.skills.dispatch import SkillContext
from app.opar.pipeline_profile import PipelineProfile, run_profile
from app.services.spend_base import bump_spend_base_revision, refresh_spend_base
from app.services.spend_line_merge import merge_persisted_line_adjustments, prior_lines_from_session


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

    # --- Build the dispatch context; the FULL profile + executor own skill
    #     invocation so batch and chat share one parameter source. The trace
    #     below is layered on via the on_complete hook so the live progress
    #     stream and "How this analysis was derived" panel are preserved. ---
    existing_session = _memory.get("session", session_id)
    prior_lines = prior_lines_from_session(existing_session) if existing_session else []
    if prior_lines:
        lines = merge_persisted_line_adjustments(lines, prior_lines)
    conflict_user_actions = dict(existing_session.get("conflict_user_actions") or {}) if existing_session else {}

    from app.services.engagement_sanity import is_placeholder_industry
    from app.services.sector_packs import resolve_sector_pack_id

    industry = resolve_sector_pack_id(industry) or industry
    resolved = {"industry": industry}
    manifest: Dict[str, Any] = {
        "session_id": session_id,
        "engagement_id": engagement_id,
        "company_name": company_name,
        "industry": industry,
        "annual_revenue": annual_revenue,
        "wacc": wacc,
        "effective_tax_rate": effective_tax_rate,
        "entity_tree": entity_tree,
        "ingestion_summary": ingestion_summary,
        "conflict_user_actions": conflict_user_actions,
    }
    ctx = SkillContext(
        lines=lines,
        docs_text=docs_text,
        manifest=manifest,
        prior_results={},
        headcount=headcount,
        wacc=wacc,
        effective_tax_rate=effective_tax_rate,
        reporting_currency=reporting_currency,
        entity_tree=entity_tree,
        segment_revenue=segment_revenue,
        sector_weights=sector_weights,
    )
    outputs: Dict[str, Dict[str, Any]] = ctx.prior_results

    def _on_complete(name: str, output: Dict[str, Any]) -> None:
        if name == "spend-profiler":
            total_spend = float(output.get("total_spend", 0.0) or 0.0)
            cat_profile = [c for c in output.get("category_profile", []) if isinstance(c, dict)]
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
        elif name == "document-contextualizer":
            # Auto-detect industry (document signals → spend patterns) before any
            # benchmark-dependent skill runs and reads ctx.industry from manifest.
            ind = resolved["industry"]
            if not ind or is_placeholder_industry(ind):
                inferred = str(output.get("inferred_industry") or "")
                if not inferred and lines:
                    total_spend = float(outputs.get("spend-profiler", {}).get("total_spend", 0.0) or 0.0)
                    inferred = engine.infer_industry_from_spend(lines, total_spend) or ""
                if inferred:
                    ind = resolve_sector_pack_id(inferred) or inferred
            resolved["industry"] = ind
            manifest["industry"] = ind
            if any(t.strip() for t in docs_text):
                constraints = [c for c in (output.get("constraints") or []) if c]
                maturity = str(output.get("procurement_maturity") or "").strip()
                ctx_inferred = str(output.get("inferred_industry") or "").strip()
                extraction_method = str(output.get("extraction_method") or "").strip()
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
        elif name == "peer-benchmarker":
            categories = [c.get("category_id") for c in outputs.get("spend-profiler", {}).get("category_profile", []) if c.get("category_id")]
            bench_resolved = resolve_benchmark_payload(industry=resolved["industry"], categories=categories, annual_revenue=annual_revenue)
            comparisons = [c for c in output.get("comparisons", []) if isinstance(c, dict)]
            above_median = [
                c for c in comparisons
                if str(c.get("percentile_band") or "") in ("P50-P75", "P75-P90", "P90+")
            ]
            dataset_name = ""
            bench_meta = output.get("benchmark_metadata") or {}
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
                    f"Compared {len(comparisons)} categories to **{resolved['industry'] or 'industry'}** peers"
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
        elif name == "root-cause-analyzer":
            rc_findings = [r for r in output.get("root_cause_findings", []) if isinstance(r, dict)]
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
        elif name == "evidence-gatherer":
            summary = output.get("corpus_summary") or {}
            inventory = output.get("evidence_inventory") or []
            doc_sources: List[str] = []
            for item in inventory:
                if not isinstance(item, dict):
                    continue
                for sig in (item.get("signals") or {}).values():
                    if isinstance(sig, dict) and sig.get("source") == "document":
                        doc_sources.extend(str(p) for p in (sig.get("provenance") or []) if p)
            doc_sources = list(dict.fromkeys(doc_sources))[:8]
            _emit(
                "evidence",
                "Searched document corpus for evidence",
                (
                    f"Searched {int(summary.get('searched_documents') or 0)} document(s), "
                    f"ran {int(summary.get('retrieval_queries_run') or 0)} retrieval queries, "
                    f"found {int(summary.get('signals_found') or 0)} evidence signal(s) "
                    f"across {len(inventory)} initiative(s)."
                ),
                sources=doc_sources or context_files,
                metrics={
                    "docs_searched": int(summary.get("searched_documents") or 0),
                    "chunks_retrieved": int(summary.get("chunks_retrieved") or 0),
                    "signals_found": int(summary.get("signals_found") or 0),
                },
            )
        elif name == "value-bridge-calculator":
            # Savings step is emitted here (not after savings-modeler) because the
            # mid-case portfolio figure comes from the value bridge confidence band.
            savings_model = outputs.get("savings-modeler", {})
            total_spend = float(outputs.get("spend-profiler", {}).get("total_spend", 0.0) or 0.0)
            initiative_list = [i for i in savings_model.get("initiatives", []) if isinstance(i, dict)]
            mid_savings = float((output.get("confidence_bands", {}) or {}).get("mid", 0.0) or 0.0)
            ranked_initiatives = sorted(initiative_list, key=_initiative_savings, reverse=True)
            initiative_bits: List[str] = []
            for item in ranked_initiatives[:3]:
                iname = str(item.get("lever_name") or item.get("lever") or "initiative")
                amt = _initiative_savings(item)
                initiative_bits.append(f"**{iname}** {_money(amt)}" if amt > 0 else f"**{iname}**")
            initiative_suffix = f" (+{len(initiative_list) - 3} more)" if len(initiative_list) > 3 else ""
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

    run_profile(PipelineProfile.FULL, ctx, on_complete=_on_complete)
    industry = resolved["industry"]
    skill_outputs = outputs

    # --- References for validation + persistence (read from executor outputs) ---
    profile = outputs["spend-profiler"]
    context = outputs["document-contextualizer"]
    benchmarks = outputs["peer-benchmarker"]
    internal = outputs["internal-benchmarker"]
    heuristics = outputs["heuristic-analyzer"]
    bridge = outputs["value-bridge-calculator"]
    validation = outputs["data-validator"]
    payment_terms = outputs["payment-terms-optimizer"]
    msme_compliance = outputs["msme-compliance-checker"]
    conflict_detection = outputs["conflict-detector"]
    contract_lifecycle = outputs["contract-lifecycle-manager"]
    consolidation = outputs["consolidation-analyzer"]

    # --- Contract validations (raise on malformed skill output) ---
    validate_core_skill_outputs(profile, context, benchmarks, internal, heuristics, bridge, validation)
    validate_bva_output(outputs["bva-analyzer"])
    validate_temporal_output(outputs["temporal-analyzer"])
    validate_payment_terms_output(payment_terms)
    validate_vendor_master_output(outputs["vendor-master-builder"])
    validate_contract_lifecycle_output(contract_lifecycle)
    validate_msme_output(msme_compliance)
    validate_consolidation_output(consolidation)
    validate_cost_to_serve_output(outputs["cost-to-serve-analyzer"])

    # --- Data-shape flags for agent memory ---
    has_budget = any(x.amount_type == "budget" for x in lines)
    has_periods = any(x.fiscal_period for x in lines)
    has_multi_source = len({ln.source_system_id for ln in lines if ln.source_system_id}) >= 2
    has_contracts = any(ln.contract_expiry_date or ln.contract_status for ln in lines)
    has_multi_entity = len({ln.legal_entity_id for ln in lines if ln.legal_entity_id}) >= 2 or entity_tree is not None

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
    if conflict_user_actions:
        state_dict["conflict_user_actions"] = conflict_user_actions
    state_dict = bump_spend_base_revision(state_dict)
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
    existing_keys: set[tuple[str | None, str | None]] = {
        (ln.source_record_id, ln.source_file_hash)
        for ln in existing_lines
        if ln.source_record_id and ln.source_file_hash
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

    impact = refresh_spend_base(
        session_id,
        reason="incremental_upload",
        lines=merged,
        existing=existing,
    )

    return {
        "status": "updated",
        "session_id": session_id,
        "lines_added": added,
        "total_lines": len(merged),
        "updated_skills": impact["updated_skills"],
        "total_spend": impact["new_total_spend"],
        "spend_base_revision": impact["spend_base_revision"],
    }


def reprofile_after_spend_correction(
    session_id: str,
    lines: List[NormalizedSpendLine],
    existing: Dict[str, Any],
) -> Dict[str, Any]:
    """Re-run spend-sensitive skills after conflict resolution adjusts line-level spend."""
    return refresh_spend_base(
        session_id,
        reason="conflict_resolution",
        lines=lines,
        existing=existing,
    )
