"""Reflect persistence — session cache merge, analysis trace, memory writes."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from app.config import UPLOAD_DIR
from app.memory import MemoryStore
from app.opar.memory_adapter import get_memory_adapter
from app.opar.models import ActResult, AdvisorySections, MemoryUpdate, ObserveContext
from app.opar.provenance import record_llm_narrative
from app.storage import read_json, write_json

_memory = MemoryStore()

_CONFLICT_TYPE_LABELS: Dict[str, str] = {
    "tds_mismatch": "TDS mismatch",
    "gst_mismatch": "GST mismatch",
    "vendor_duplicate": "Duplicate vendor (GSTIN/name)",
    "intercompany_inflation": "Intercompany inflation",
    "fx_mismatch": "FX rate mismatch",
    "benchmark_disagreement": "Benchmark disagreement",
    "amount_mismatch": "Amount mismatch across sources",
    "cost_center_lag": "Cost centre mapping lag",
}

def _merge_with_session_cache(
    session_id: str,
    validated: Dict[str, Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Overlay cached skill outputs so follow-up turns can use prior value/SME analysis."""
    merged: Dict[str, Dict[str, Any]] = dict(validated)
    cached = _memory.get("session", session_id)
    if not isinstance(cached, dict):
        return merged
    prior = cached.get("skill_outputs", {})
    if not isinstance(prior, dict):
        return merged
    for skill, output in prior.items():
        if skill not in merged and isinstance(output, dict):
            merged[skill] = output
    try:
        from app.opar.hitl.probe_answers import apply_probe_answers_to_skill_outputs

        return apply_probe_answers_to_skill_outputs(merged, session_id)
    except Exception:
        return merged


def _build_chat_analysis_trace(validated: Dict[str, Dict[str, Any]], currency: str) -> List[Dict[str, Any]]:
    """Lightweight, ordered derivation trace for chat-only sessions (no /api/analyze).

    Gives the "How this analysis was derived" panel something to show when the full
    batch trace is absent. Deliberately concise — the batch path emits the rich
    version via run_core_pipeline's on_complete hook."""
    trace: List[Dict[str, Any]] = []

    def add(phase: str, title: str, detail: str, metrics: Dict[str, Any] | None = None) -> None:
        trace.append({
            "step": len(trace) + 1, "phase": phase, "title": title,
            "detail": detail, "source_documents": [], "metrics": metrics or {},
        })

    profile = validated.get("spend-profiler")
    if isinstance(profile, dict):
        total = float(profile.get("total_spend", 0.0) or 0.0)
        cats = [c for c in profile.get("category_profile", []) if isinstance(c, dict)]
        add("ingest", "Read spend data",
            f"Profiled {len(cats)} categories totalling {currency} {total:,.0f}.",
            {"category_count": len(cats), "total_spend": total})
    peer = validated.get("peer-benchmarker")
    if isinstance(peer, dict):
        comps = peer.get("comparisons", []) or []
        add("benchmark", "Benchmarked against peers",
            f"Compared {len(comps)} categories to industry peers.",
            {"comparison_count": len(comps)})
    rc = validated.get("root-cause-analyzer")
    if isinstance(rc, dict):
        findings = rc.get("root_cause_findings", []) or []
        add("root_cause", "Diagnosed root causes",
            f"Identified {len(findings)} root-cause finding(s).",
            {"finding_count": len(findings)})
    bridge = validated.get("value-bridge-calculator")
    if isinstance(bridge, dict):
        mid = float((bridge.get("confidence_bands", {}) or {}).get("mid", 0.0) or 0.0)
        inits = (validated.get("savings-modeler", {}) or {}).get("initiatives", []) or []
        add("savings", "Modelled savings opportunities",
            f"Built {len(inits)} initiative(s); mid-case savings {currency} {mid:,.0f}.",
            {"initiative_count": len(inits), "mid_case_savings": mid})
    return trace


def apply_memory_updates(
    ctx: ObserveContext,
    validated: Dict[str, Dict[str, Any]],
) -> tuple[list[MemoryUpdate], Dict[str, list[MemoryUpdate]]]:
    adapter = get_memory_adapter()
    user_updates: list[MemoryUpdate] = []
    agent_updates: Dict[str, list[MemoryUpdate]] = {}
    if "spend-profiler" in validated and ctx.user_id:
        profile = validated["spend-profiler"]
        adapter.add_user(ctx.user_id, {
            "company_name": ctx.user_id,
            "last_total_spend": profile.get("total_spend", 0),
        })
        user_updates.append(MemoryUpdate(scope="user", key=ctx.user_id, content={"profile": profile}))
    if "value-bridge-calculator" in validated:
        bridge = validated["value-bridge-calculator"]
        adapter.add_session(ctx.session_id, {"value_bridge": bridge}, {"phase": "reflect"})
    return user_updates, agent_updates


def persist_session_analysis(
    *,
    ctx: ObserveContext,
    act_result: ActResult,
    validated: Dict[str, Dict[str, Any]],
    manifest: Dict[str, Any],
    reporting_currency: str,
    advisory_sections: AdvisorySections | None,
) -> None:
    if not validated:
        return
    existing_analysis = _memory.get("session", ctx.session_id)
    analysis_snapshot: Dict[str, Any] = dict(existing_analysis) if isinstance(existing_analysis, dict) else {}
    merged_outputs: Dict[str, Any] = {}
    prior_outputs = analysis_snapshot.get("skill_outputs", {})
    if isinstance(prior_outputs, dict):
        merged_outputs.update(prior_outputs)
    merged_outputs.update(validated)
    prior_spend = analysis_snapshot.get("normalized_spend", [])
    if not prior_spend and getattr(act_result, "normalized_spend", None):
        prior_spend = [l.model_dump(mode="json") for l in act_result.normalized_spend]
    prior_trace = analysis_snapshot.get("analysis_trace", [])
    if not prior_trace:
        prior_trace = _build_chat_analysis_trace(merged_outputs, reporting_currency)
    analysis_snapshot.update({
        "session_id": ctx.session_id,
        "engagement_id": manifest.get("engagement_id") or analysis_snapshot.get("engagement_id") or getattr(ctx, "engagement_id", None),
        "company_name": manifest.get("company_name") or analysis_snapshot.get("company_name"),
        "industry": manifest.get("industry") or analysis_snapshot.get("industry") or "",
        "annual_revenue": float(manifest.get("annual_revenue") or analysis_snapshot.get("annual_revenue") or 0),
        "reporting_currency": reporting_currency,
        "normalized_spend": prior_spend,
        "context_summary": analysis_snapshot.get("context_summary", ""),
        "analysis_trace": prior_trace,
        "wacc": manifest.get("wacc", analysis_snapshot.get("wacc")),
        "effective_tax_rate": manifest.get("effective_tax_rate", analysis_snapshot.get("effective_tax_rate")),
        "skill_outputs": merged_outputs,
        "advisory_sections": advisory_sections.model_dump() if advisory_sections else analysis_snapshot.get("advisory_sections", {}),
        "response_artefacts": getattr(act_result, "response_artefacts", None) or analysis_snapshot.get("response_artefacts", []),
        "last_run_intent": ctx.intent_class,
        "skills_run_this_turn": list(validated.keys()),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    if "spend-profiler" in validated:
        from app.services.spend_base import repair_spend_base_if_needed

        analysis_snapshot = repair_spend_base_if_needed(ctx.session_id, analysis_snapshot)
    _memory.put("session", ctx.session_id, analysis_snapshot)


def persist_conflict_manifest(session_id: str, validated: Dict[str, Dict[str, Any]]) -> None:
    manifest_path = UPLOAD_DIR / session_id / "manifest.json"
    if "conflict-detector" not in validated or not manifest_path.parent.exists():
        return
    cd = validated["conflict-detector"]
    if not isinstance(cd, dict):
        return
    manifest = read_json(manifest_path, {})
    manifest["conflict_state"] = {
        "total": int(cd.get("conflict_count") or cd.get("total") or 0),
        "unresolved": int(cd.get("unresolved") or 0),
        "by_type": cd.get("by_type") or {},
        "has_intercompany": bool((cd.get("by_type") or {}).get("intercompany_inflation")),
    }
    write_json(manifest_path, manifest)


def record_advisory_provenance(
    ctx: ObserveContext,
    validated: Dict[str, Dict[str, Any]],
    advisory_sections: AdvisorySections | None,
) -> Dict[str, Any] | None:
    if not advisory_sections or not advisory_sections.executive_takeaway:
        return None
    try:
        return record_llm_narrative(
            narrative=advisory_sections.executive_takeaway,
            engagement_id=getattr(ctx, "engagement_id", ctx.session_id),
            turn_id=ctx.turn_id,
            skill_outputs_used=list(validated.keys()),
            prompt_text=ctx.user_message,
            model_version="claude-sonnet-4-6",
            seed=0,
        )
    except Exception:
        return None


def build_next_options(
    ctx: ObserveContext,
    validated: Dict[str, Dict[str, Any]],
    sme_portfolio_probes: List[Dict[str, Any]],
    *,
    gate2_blocked: bool,
    forced_reg_decision: bool,
) -> tuple[list[str], list[Dict[str, str]]]:
    artefacts: list[str] = []
    next_options: list[Dict[str, str]] = []

    if "business-case-builder" in validated:
        next_options.append({"label": "Export as document", "message": "Export the business case as a document"})
    if "value-bridge-calculator" in validated and "business-case-builder" not in validated:
        next_options.append({"label": "Generate business case", "message": "Generate business case"})

    if sme_portfolio_probes:
        probe_ctas: list[Dict[str, str]] = []
        for probe in sme_portfolio_probes[:3]:
            label = str(probe.get("chat_cta") or probe.get("question", ""))[:60]
            question = str(probe.get("question") or "")
            fam = str(probe.get("probe_family_id") or "")
            if label and question:
                probe_ctas.append({"label": label, "message": question, "probe_family_id": fam})
        next_options = probe_ctas + next_options

    chart_url = validated.get("chart-builder", {}).get("chart_url")
    if chart_url:
        artefacts.append(chart_url)
        next_options.append({"label": "Open spend chart", "message": "Show spend profile chart"})

    benchmark_skills = {"peer-benchmarker", "internal-benchmarker", "heuristic-analyzer"}
    if all(s in validated for s in benchmark_skills) and "value-bridge-calculator" not in validated:
        next_options.append({"label": "Calculate value-at-the-table", "message": "Calculate the value-at-the-table matrix"})

    unresolved_conflicts = getattr(ctx, "unresolved_conflict_count", 0)
    multi_source = getattr(ctx, "multi_source_upload", False)
    has_ic = getattr(ctx, "has_intercompany_lines", False)

    if unresolved_conflicts > 0:
        next_options.append({
            "label": f"Resolve {unresolved_conflicts} data conflict{'s' if unresolved_conflicts != 1 else ''}",
            "message": "Show me all unresolved conflicts and resolution options",
        })
    elif multi_source and not unresolved_conflicts:
        next_options.append({
            "label": "Detect cross-source conflicts",
            "message": "Check for TDS, GST, and vendor conflicts across uploaded sources",
        })

    if has_ic or (getattr(ctx, "conflict_count", 0) > 0 and "intercompany_inflation" in str(getattr(ctx, "conflict_summary", {}))):
        next_options.append({
            "label": "View consolidated group spend",
            "message": "Show consolidated spend with intercompany elimination applied",
        })

    if multi_source:
        next_options.append({
            "label": "Build vendor master",
            "message": "Deduplicate vendors by GSTIN across all sources and build canonical master",
        })

    if gate2_blocked:
        next_options.append({
            "label": "Review assumption quality",
            "message": "Show me the assumption quality issues blocking Gate-2",
        })

    if forced_reg_decision:
        next_options.append({
            "label": "Review regulatory events",
            "message": "Show me the regulatory events requiring a decision",
        })

    return artefacts, next_options
