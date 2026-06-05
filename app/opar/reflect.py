from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

import pandas as pd

from app.config import ANTHROPIC_ENABLED, UPLOAD_DIR
from app.memory import MemoryStore
from app.opar.category_resolver import match_category_from_query, tokenize
from app.opar.memory_adapter import get_memory_adapter
from app.utils.inr_format import format_money
from app.opar.quality import assumptions_from_initiative, check_gate2
from app.opar.provenance import record_llm_narrative
from app.services.reg_watcher import surface_at_reflect_gate

_memory = MemoryStore()
from app.opar.models import (
    ActResult,
    AdvisorySections,
    ConfidenceScore,
    ExecutionPlan,
    MemoryUpdate,
    ObserveContext,
    ReflectOutput,
)
from app.skills.contracts import (
    validate_analysis_synthesizer_output,
    validate_core_skill_outputs,
    validate_executive_communication_output,
    validate_peer_benchmarker_output,
)
from app.storage import read_json, write_json

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


def _tokenize(text: str) -> list[str]:
    return tokenize(text)


def _match_focus_category(ctx: ObserveContext, validated: Dict[str, Dict[str, Any]]) -> Dict[str, Any] | None:
    """Best-effort category matcher for focused optimization responses."""
    matrix = validated.get("value-bridge-calculator", {}).get("value_matrix", [])
    if not isinstance(matrix, list) or not matrix:
        return None
    query_tokens = set(_tokenize(ctx.user_message))
    if not query_tokens:
        return None
    return match_category_from_query(ctx.user_message, matrix)


def _build_focus_category_section(ctx: ObserveContext, validated: Dict[str, Dict[str, Any]]) -> str:
    row = _match_focus_category(ctx, validated)
    if not row:
        return ""
    cat = row.get("category_name") or row.get("category_id") or "Selected category"
    cid = str(row.get("category_id") or "")
    mid = float(row.get("deduped_mid_savings", 0.0))
    npv = float(row.get("net_npv", 0.0))
    payback = int(row.get("payback_months", 0) or 0)
    confidence = str(row.get("confidence") or "medium")
    lever = str(row.get("lever") or "optimization")
    lever_label = _business_lever_label(lever)
    root = str(row.get("root_cause") or "benchmark gap above norm")

    addressable = total_cat = 0.0
    supplier_count = 0
    top_suppliers: List[Dict[str, Any]] = []
    top_geos: List[Dict[str, Any]] = []
    express_like_pct = 0.0
    for c in validated.get("spend-profiler", {}).get("category_profile", []):
        if str(c.get("category_id")) == cid:
            addressable = float(c.get("addressable_spend", 0.0) or 0.0)
            total_cat = float(c.get("spend", 0.0) or 0.0)
            supplier_count = int(c.get("supplier_count", 0) or 0)
            top_suppliers = c.get("top_suppliers", []) if isinstance(c.get("top_suppliers"), list) else []
            top_geos = c.get("top_geos", []) if isinstance(c.get("top_geos"), list) else []
            express_like_pct = float(c.get("express_like_pct", 0.0) or 0.0)
            break

    quick_wins: List[str] = []
    if total_cat > 0:
        quick_wins.append(
            f"{cat} is {_format_currency(total_cat)} with {_format_currency(addressable)} modeled as addressable spend."
        )
    if len(top_suppliers) >= 2:
        fast = min(
            [s for s in top_suppliers if isinstance(s.get("avg_payment_terms_days"), (int, float))],
            key=lambda x: float(x.get("avg_payment_terms_days", 999)),
            default=None,
        )
        slow = max(
            [s for s in top_suppliers if isinstance(s.get("avg_payment_terms_days"), (int, float))],
            key=lambda x: float(x.get("avg_payment_terms_days", 0)),
            default=None,
        )
        if fast and slow:
            gap = float(slow.get("avg_payment_terms_days", 0)) - float(fast.get("avg_payment_terms_days", 0))
            if gap >= 8:
                fast_spend = float(fast.get("spend", 0.0) or 0.0)
                wc_release = fast_spend * (gap / 365.0)
                quick_wins.append(
                    f"Payment terms gap detected: {fast.get('supplier')} at Net {int(round(float(fast.get('avg_payment_terms_days', 0))))} "
                    f"vs {slow.get('supplier')} at Net {int(round(float(slow.get('avg_payment_terms_days', 0))))}. "
                    f"Moving {fast.get('supplier')} to matched terms can release about {_format_currency(wc_release)} in working capital."
                )
    if supplier_count >= 3 and top_suppliers:
        top2_share = sum(float(s.get("share_of_category", 0.0) or 0.0) for s in top_suppliers[:2])
        quick_wins.append(
            f"Supplier base is fragmented ({supplier_count} suppliers). Consolidating volume to 1-2 strategic carriers "
            f"can improve rate cards and service governance (current top-2 share {top2_share:.0%})."
        )
    if express_like_pct >= 0.15:
        quick_wins.append(
            f"About {express_like_pct:.0%} of spend appears express/priority-like; a lane-level mode audit can shift eligible volume to lower-cost modes."
        )
    if len(top_geos) >= 2:
        geo_names = ", ".join(str(g.get("geo")) for g in top_geos[:3])
        quick_wins.append(
            f"Spend is split across geographies ({geo_names}); harmonizing contracts and Incoterms by lane can reduce leakage."
        )

    payment_terms = validated.get("payment-terms-optimizer", {})
    if isinstance(payment_terms, dict):
        for opp in payment_terms.get("opportunities", []):
            if str(opp.get("category_id")) == cid:
                dpo_days = float(opp.get("dpo_improvement_days", 0.0) or 0.0)
                wc = float(opp.get("working_capital_release", 0.0) or 0.0)
                if dpo_days > 0 and wc > 0:
                    quick_wins.append(
                        f"Terms optimization potential: +{dpo_days:.0f} DPO days with {_format_currency(wc)} one-time working-capital release."
                    )
                break

    root_causes = []
    for rc in validated.get("root-cause-analyzer", {}).get("root_cause_findings", []):
        if str(rc.get("category_id")) == cid:
            root_causes = rc.get("root_causes", []) if isinstance(rc.get("root_causes"), list) else []
            break
    lever_framework: List[str] = []
    for cause in root_causes[:3]:
        lever_code = str(cause.get("recommended_lever") or lever)
        lever_framework.append(
            f"{_business_lever_label(lever_code).capitalize()}: {cause.get('implementation_approach', 'Apply targeted policy and process interventions.')}"
        )
    if not lever_framework:
        lever_framework.append(
            f"{lever_label.capitalize()}: reset commercial terms, tighten demand controls, and embed monthly performance governance."
        )

    lines = [f"**Focused optimization: {cat}**"]
    if ctx.intent_class == "business_case":
        lines.append(
            f"Modeled impact: mid-case {_format_currency(mid)}, NPV {_format_currency(npv)}, "
            f"payback {payback if payback > 0 else 'not established'} months, confidence {confidence}."
        )
    else:
        lines.append(
            f"Modeled value-release potential: mid-case {_format_currency(mid)} with confidence {confidence}. "
            "Business-case economics (NPV/payback) can be generated on request."
        )
    lines.append("")
    lines.append("**From your data: quick wins**")
    for q in quick_wins[:5]:
        lines.append(f"- {q}")
    lines.append("")
    lines.append("**Business lever framework**")
    for lf in lever_framework:
        lines.append(f"- {lf}")
    lines.append(f"- Primary modeled bottleneck: {root}.")
    return "\n".join(lines)


def _compute_quality_signals(
    validated: Dict[str, Dict[str, Any]],
    failed: Dict[str, str],
    ctx: ObserveContext,
    degradation_reasons: Dict[str, str] | None = None,
) -> Dict[str, Any]:
    """Runtime quality proxy for UI: faithfulness + relevance."""
    faithfulness = 0.95
    if failed:
        faithfulness -= min(0.35, 0.08 * len(failed))
    if degradation_reasons:
        faithfulness -= min(0.2, 0.06 * len(degradation_reasons))
    checks = validated.get("data-validator", {}).get("checks", {})
    if isinstance(checks, dict) and checks:
        failed_checks = sum(1 for v in checks.values() if not v)
        faithfulness -= min(0.25, failed_checks * 0.08)
    if not validated:
        faithfulness = 0.55
    faithfulness = max(0.0, min(1.0, faithfulness))

    relevance = 0.65
    if ctx.intent_class == "general_qa":
        relevance = 0.85 if validated else 0.65
    elif ctx.intent_class == "benchmark":
        relevance = 0.9 if "peer-benchmarker" in validated else 0.7
    elif ctx.intent_class == "value_bridge":
        relevance = 0.92 if "value-bridge-calculator" in validated else 0.72
    elif ctx.intent_class == "business_case":
        relevance = 0.92 if "business-case-builder" in validated else 0.72
    elif ctx.intent_class == "upload_data":
        relevance = 0.88 if "spend-profiler" in validated else 0.7

    focus_match = _match_focus_category(ctx, validated)
    if focus_match:
        relevance = min(0.98, relevance + 0.04)
    confidence_penalty = float(
        validated.get("value-bridge-calculator", {}).get("confidence_adjustment", {}).get("penalty", 0.0) or 0.0
    )
    if confidence_penalty > 0:
        relevance = max(0.0, relevance - min(0.15, confidence_penalty))
    relevance = max(0.0, min(1.0, relevance))

    return {
        "faithfulness_score": round(faithfulness, 2),
        "relevance_score": round(relevance, 2),
        "faithfulness_label": "high" if faithfulness >= 0.85 else ("medium" if faithfulness >= 0.7 else "low"),
        "relevance_label": "high" if relevance >= 0.85 else ("medium" if relevance >= 0.7 else "low"),
        "focus_category": focus_match.get("category_name") if focus_match else None,
        "degraded_skills": dict(degradation_reasons or {}),
    }


def _collect_grounding_tokens(validated: Dict[str, Dict[str, Any]]) -> List[str]:
    tokens: List[str] = []
    profile = validated.get("spend-profiler", {})
    total = float(profile.get("total_spend", 0.0) or 0.0)
    if total > 0:
        tokens.append(_format_currency(total))
    for row in profile.get("category_profile", [])[:6]:
        name = str(row.get("category_name") or "").strip()
        if name:
            tokens.append(name)
    for row in validated.get("value-bridge-calculator", {}).get("value_matrix", [])[:6]:
        mid = float(row.get("deduped_mid_savings", 0.0) or 0.0)
        if mid > 0:
            tokens.append(_format_currency(mid))
    return tokens


def _compute_grounding_coverage(response_text: str, validated: Dict[str, Dict[str, Any]]) -> float:
    if not response_text.strip():
        return 0.0
    tokens = _collect_grounding_tokens(validated)
    if not tokens:
        return 1.0
    lowered = response_text.lower()
    hits = sum(1 for t in tokens if t and t.lower() in lowered)
    return round(hits / max(1, len(tokens)), 2)


def _is_category_focused_request(ctx: ObserveContext | None, validated: Dict[str, Dict[str, Any]]) -> bool:
    if not ctx:
        return False
    if bool((ctx.explicit_category or "").strip()):
        return True
    return _match_focus_category(ctx, validated) is not None


def _build_transaction_examples_for_llm(validated: Dict[str, Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    examples: Dict[str, List[Dict[str, Any]]] = {}
    for row in validated.get("spend-profiler", {}).get("category_profile", []):
        cid = str(row.get("category_id") or "")
        if not cid:
            continue
        out_rows: List[Dict[str, Any]] = []
        for sup in row.get("top_suppliers", [])[:3]:
            out_rows.append(
                {
                    "supplier": sup.get("supplier", "Unknown supplier"),
                    "description": f"Top supplier share in {row.get('category_name', cid)}",
                    "amount": float(sup.get("spend", 0.0) or 0.0),
                    "why_relevant": "Material supplier concentration in this category.",
                }
            )
        if out_rows:
            examples[cid] = out_rows
    return examples


def _normalize_advisory_sections(raw: Dict[str, Any]) -> AdvisorySections | None:
    if not isinstance(raw, dict):
        return None
    payload = {
        "executive_takeaway": raw.get("executive_takeaway", ""),
        "category_focus_section": raw.get("category_focus_section", ""),
        "quick_wins_from_data": raw.get("quick_wins_from_data", []),
        "business_levers": raw.get("business_levers", []),
        "executive_callouts": raw.get("executive_callouts", []),
        "priority_actions_30_60_90": raw.get("priority_actions_30_60_90", []),
        "sme_qualification_narrative": raw.get("sme_qualification_narrative", ""),
    }
    try:
        return AdvisorySections.model_validate(payload)
    except Exception:
        return None


def _advisory_quality_ok(advisory: AdvisorySections, category_focused: bool = False) -> bool:
    if len((advisory.executive_takeaway or "").strip()) < 25:
        return False
    if len(advisory.business_levers) < 3:
        return False
    if len(advisory.quick_wins_from_data) < 2:
        return False
    generic_tokens = {"internal best practice", "best practice only", "optimize internally"}
    for lever in advisory.business_levers:
        name = (lever.lever_name or "").lower()
        if any(t in name for t in generic_tokens):
            return False
        if len((lever.what_changes or "").strip()) < 18:
            return False
        if len((lever.why_it_works or "").strip()) < 18:
            return False
        if len(lever.evidence) < 2:
            return False
    # For category-focused requests the `category_focus_section` must be a substantive
    # decision memo, not a single sentence.  Require at least 150 chars (≈2 sentences).
    if category_focused and len((advisory.category_focus_section or "").strip()) < 150:
        return False
    return True


def _compose_response_from_advisory(
    advisory: AdvisorySections,
    validated: Dict[str, Dict[str, Any]],
    include_executive_takeaway: bool = False,
    include_business_case_metrics: bool = False,
    category_focused: bool = False,
) -> str:
    bands = validated.get("value-bridge-calculator", {}).get("confidence_bands", {})
    chart = validated.get("chart-builder", {}) if isinstance(validated.get("chart-builder", {}), dict) else {}
    chart_url = chart.get("chart_url")
    chart_points = chart.get("commentary_points", []) if isinstance(chart.get("commentary_points", []), list) else []
    lines: List[str] = []
    if advisory.category_focus_section and isinstance(chart_url, str) and chart_url.startswith("/api/exports/"):
        lines.append("**Relevant chart view**")
        lines.append(f"[Open chart view]({chart_url})")
        if chart_points:
            lines.append("- Chart perspective:")
            for point in chart_points[:2]:
                lines.append(f"  - {point}")
        lines.append("")
    if bands:
        lines.append(
            f"Modeled value-release opportunity: mid-case {_format_currency(bands.get('mid', 0))} "
            f"(low {_format_currency(bands.get('low', 0))}, high {_format_currency(bands.get('high', 0))})."
        )
        lines.append("")
    if include_executive_takeaway and advisory.executive_takeaway:
        lines.append("**Executive takeaway**")
        lines.append(advisory.executive_takeaway)
        # If the LLM takeaway is too short, enrich it with explicit value logic.
        if len((advisory.executive_takeaway or "").strip()) < 260:
            recs = _recommendation_rows(validated, max_items=2)
            if recs:
                lines.append("")
                lines.append("**Business logic (value creation path)**")
                for rec in recs:
                    evidence = rec.get("evidence", [])
                    first_evidence = evidence[0] if evidence else "Primary benchmark and model signals indicate a material performance gap."
                    if include_business_case_metrics:
                        lines.append(
                            f"- In **{rec['category']}**, the core mechanism is **{rec.get('lever_label', rec['lever'])}**: "
                            f"close the identified gap through concrete operating/commercial changes, translating to "
                            f"{_format_currency(rec['dedup_mid'])} modeled mid-case impact with {_format_currency(rec['npv'])} NPV."
                        )
                    else:
                        lines.append(
                            f"- In **{rec['category']}**, the core mechanism is **{rec.get('lever_label', rec['lever'])}**: "
                            f"close the identified gap through concrete operating/commercial changes, translating to "
                            f"{_format_currency(rec['dedup_mid'])} modeled value release."
                        )
                    lines.append(f"  - Why this is credible: {first_evidence}")
                lines.append("- Leadership decision needed: confirm execution ownership and the first 30-60-90 day governance milestones.")
        lines.append("")
    if advisory.category_focus_section:
        lines.append("**Focused optimization view**")
        lines.append(advisory.category_focus_section)
        lines.append("")
    if category_focused and advisory.business_levers:
        lines.append("**Focused category recommendations**")
        for lever in advisory.business_levers[:4]:
            lines.append(f"- **{lever.lever_name}**: {lever.what_changes}")
        lines.append("")
        lines.append("**Business logic with specifics**")
        for lever in advisory.business_levers[:4]:
            lines.append(f"- **{lever.lever_name}**")
            lines.append(f"  - Why this releases value: {lever.why_it_works}")
            if lever.evidence:
                lines.append(f"  - Evidence anchor: {lever.evidence[0]}")
            if len(lever.evidence) > 1:
                lines.append(f"  - Additional specificity: {lever.evidence[1]}")
        lines.append("")
    if advisory.quick_wins_from_data:
        lines.append("**From your data: quick wins**")
        for x in advisory.quick_wins_from_data[:5]:
            lines.append(f"- {x}")
        lines.append("")
    if advisory.business_levers and not category_focused:
        lines.append("**Business levers (what should change)**")
        for lever in advisory.business_levers[:4]:
            lines.append(f"- **{lever.lever_name}**: {lever.what_changes}")
            lines.append(f"  - Why it works: {lever.why_it_works}")
            if lever.evidence:
                lines.append(f"  - Evidence: {lever.evidence[0]}")
                if len(lever.evidence) > 1:
                    lines.append(f"  - Additional evidence: {lever.evidence[1]}")
            lines.append("  - Value-release logic: convert the measured gap into codified operating/commercial changes and lock savings into run-rate.")
        lines.append("")
    if advisory.executive_callouts:
        lines.append("**Executive call-outs**")
        for c in advisory.executive_callouts[:3]:
            lines.append(f"- {c}")
        lines.append("")
    if advisory.priority_actions_30_60_90:
        lines.append("**30-60-90 day actions**")
        for a in advisory.priority_actions_30_60_90[:3]:
            lines.append(f"- Day {a.timeline}: {a.action} ({a.expected_impact})")
    return "\n".join(lines).strip()


_LLM_TOKEN_LIMIT = 80_000
_CHARS_PER_TOKEN = 4


def _estimate_tokens(payload: Dict[str, Any]) -> int:
    """Rough token estimate: serialize to JSON and divide char count by 4."""
    try:
        return len(json.dumps(payload, default=str)) // _CHARS_PER_TOKEN
    except Exception:
        return 0


def _generate_llm_advisory_sections(
    ctx: ObserveContext,
    manifest: Dict[str, Any],
    validated: Dict[str, Dict[str, Any]],
    thinking_enabled: bool = False,
    thinking_budget_tokens: int = 8000,
) -> Tuple[AdvisorySections | None, str | None]:
    if not ANTHROPIC_ENABLED:
        return None, None
    if "value-bridge-calculator" not in validated:
        return None, None
    try:
        from app.opar.claude_client import synthesize_analysis_claude
    except Exception:
        return None, None

    docs = []
    doc_summary = str(validated.get("document-contextualizer", {}).get("context_summary", "")).strip()
    if doc_summary:
        docs = [doc_summary]
    tx_examples = _build_transaction_examples_for_llm(validated)

    # Parent-child RAG: pull question-specific context (auto-merged to parents)
    # from the engagement's indexed documents. Empty when nothing is indexed,
    # in which case synthesis falls back to the front-truncated doc summary.
    retrieved_context: List[str] | None = None
    try:
        from app.services.document_index import retrieve_context

        engagement_id = ctx.engagement_id or manifest.get("engagement_id") or ""
        blocks = retrieve_context(engagement_id, ctx.user_message)
        if blocks:
            retrieved_context = blocks
    except Exception:
        retrieved_context = None

    estimated_tokens = _estimate_tokens({
        "user_message": ctx.user_message,
        "manifest": manifest,
        "skill_outputs": validated,
        "docs_text": retrieved_context or docs,
        "transaction_examples": tx_examples,
    })
    from app.config import logger as _logger
    _logger.info("llm_token_budget estimated_tokens=%d limit=%d", estimated_tokens, _LLM_TOKEN_LIMIT)
    if estimated_tokens > _LLM_TOKEN_LIMIT:
        _logger.warning(
            "llm_token_budget_exceeded estimated_tokens=%d limit=%d; skipping LLM synthesis",
            estimated_tokens,
            _LLM_TOKEN_LIMIT,
        )
        return None, None

    best_effort: AdvisorySections | None = None
    captured_thinking: str | None = None
    category_focused = _is_category_focused_request(ctx, validated)

    mode_order = (True, False) if category_focused else (False, True)
    for strict_mode in mode_order:
        try:
            raw, thinking_text = synthesize_analysis_claude(
                user_message=ctx.user_message,
                manifest=manifest,
                model_manifest=ctx.model_manifest,
                skill_outputs=validated,
                docs_text=docs,
                transaction_examples=tx_examples,
                strict_mode=strict_mode,
                thinking_enabled=thinking_enabled,
                thinking_budget_tokens=thinking_budget_tokens,
                deep_research_summary=ctx.deep_research_summary,
                retrieved_context=retrieved_context,
            )
        except Exception:
            raw, thinking_text = None, None
        if thinking_text and not captured_thinking:
            captured_thinking = thinking_text
        advisory = _normalize_advisory_sections(raw or {})
        if not advisory:
            continue
        if _advisory_quality_ok(advisory, category_focused=category_focused):
            return advisory, captured_thinking
        # Keep best effort so category asks can still use LLM-first narrative
        # instead of dropping to deterministic canned executive text.
        if (
            len((advisory.executive_takeaway or "").strip()) >= 60
            and len(advisory.business_levers) >= (2 if category_focused else 1)
        ):
            best_effort = advisory
    return best_effort, captured_thinking


def _layer1_schema_validation(
    validated: Dict[str, Dict[str, Any]],
    failed: Dict[str, str],
    plan: ExecutionPlan,
) -> None:
    """Layer 1: Schema validation via contracts."""
    required = [
        "spend-profiler",
        "document-contextualizer",
        "peer-benchmarker",
        "internal-benchmarker",
        "heuristic-analyzer",
        "value-bridge-calculator",
        "data-validator",
    ]
    if all(s in validated for s in required):
        try:
            validate_core_skill_outputs(
                validated["spend-profiler"],
                validated["document-contextualizer"],
                validated["peer-benchmarker"],
                validated["internal-benchmarker"],
                validated["heuristic-analyzer"],
                validated["value-bridge-calculator"],
                validated["data-validator"],
            )
        except Exception as e:
            failed["contract_validation"] = str(e)


def _layer1_optional_synthesis_validation(
    validated: Dict[str, Dict[str, Any]],
    failed: Dict[str, str],
) -> None:
    # Standalone peer_benchmarker quality gate — validates when present outside full pipeline.
    peer_benchmarker = validated.get("peer-benchmarker")
    if peer_benchmarker and "contract_validation" not in failed:
        try:
            validate_peer_benchmarker_output(peer_benchmarker)
        except Exception as e:
            failed["peer_benchmarker_validation"] = str(e)

    synthesis = validated.get("analysis-synthesizer")
    if not synthesis:
        return
    try:
        validate_analysis_synthesizer_output(synthesis)
    except Exception as e:
        failed["analysis_synthesizer_validation"] = str(e)

    communication = validated.get("executive-communication")
    if not communication:
        return
    try:
        validate_executive_communication_output(communication)
    except Exception as e:
        failed["executive_communication_validation"] = str(e)


def _layer2_coherence_checks(
    validated: Dict[str, Dict[str, Any]],
    failed: Dict[str, str],
    confidence_scores: Dict[str, ConfidenceScore],
) -> None:
    """Layer 2: Coherence checks (peer savings ≤ addressable, internal ≤ current, heuristic ratios)."""
    profile = validated.get("spend-profiler", {})
    peer = validated.get("peer-benchmarker", {})
    internal = validated.get("internal-benchmarker", {})
    heuristic = validated.get("heuristic-analyzer", {})
    bridge = validated.get("value-bridge-calculator", {})

    total_spend = profile.get("total_spend", 0.0)
    if total_spend <= 0:
        return

    # Peer: estimated_saving_amount should not exceed category spend (addressable)
    for row in peer.get("comparisons", []):
        cat_spend = next(
            (c["spend"] for c in profile.get("category_profile", []) if c["category_id"] == row["category_id"]),
            0.0,
        )
        saving = row.get("estimated_saving_amount", 0.0)
        if saving > cat_spend and cat_spend > 0:
            confidence_scores["peer-benchmarker"] = ConfidenceScore(
                level="low",
                factor=0.6,
                rationale="Some peer savings exceed addressable spend; conservative interpretation.",
            )
            break

    # Internal: best-practice (median) should not exceed current (max) per category
    for row in internal.get("internal_variance", []):
        median_v = row.get("median_spend", 0.0)
        max_v = row.get("max_spend", 0.0)
        if max_v > 0 and median_v > max_v:
            confidence_scores["internal-benchmarker"] = ConfidenceScore(
                level="low",
                factor=0.6,
                rationale="Internal variance coherence check flagged.",
            )
            break

    # Heuristic: actual_pct and target_pct in plausible range (e.g. 0–50%)
    for row in heuristic.get("heuristic_findings", []):
        actual = row.get("actual_pct_of_revenue", 0.0)
        target = row.get("heuristic_target_pct", 0.0)
        if actual > 50 or target > 50:
            confidence_scores["heuristic-analyzer"] = ConfidenceScore(
                level="low",
                factor=0.6,
                rationale="Heuristic ratios outside typical range.",
            )
            break


def _layer3_domain_confidence(
    validated: Dict[str, Dict[str, Any]],
    ctx: ObserveContext,
    confidence_scores: Dict[str, ConfidenceScore],
) -> None:
    """Layer 3: Domain confidence per skill based on benchmark match, data quality, field completeness."""
    dq = ctx.data_quality_score
    missing = ctx.missing_fields

    for skill_name, out in validated.items():
        if skill_name in confidence_scores:
            continue
        level = "mid"
        factor = 0.75
        rationale = "Schema validated"
        if dq < 0.6:
            level = "low"
            factor = 0.6
            rationale = f"Data quality score {dq:.2f} below threshold."
        elif missing:
            level = "low" if len(missing) > 1 else "mid"
            factor = 0.7 if len(missing) > 1 else 0.75
            rationale = f"Missing fields: {', '.join(missing)}" if missing else rationale
        elif dq >= 0.9 and not missing:
            level = "high"
            factor = 0.9
            rationale = "High data quality, complete fields."
        confidence_scores[skill_name] = ConfidenceScore(level=level, factor=factor, rationale=rationale)


def _compute_dedup_factor(validated: Dict[str, Dict[str, Any]]) -> float:
    """Compute dedup_factor (0.6–0.8) based on lever overlap."""
    bridge = validated.get("value-bridge-calculator", {})
    matrix = bridge.get("value_matrix", [])
    if not matrix:
        return 0.75
    overlap_count = 0
    for row in matrix:
        levers_with_savings = sum(
            1
            for k in ("peer_savings", "internal_savings", "heuristic_savings")
            if row.get(k, 0) > 0
        )
        if levers_with_savings >= 2:
            overlap_count += 1
    overlap_ratio = overlap_count / len(matrix) if matrix else 0.0
    return max(0.6, min(0.8, 0.8 - 0.2 * overlap_ratio))


def _build_value_bridge_matrix(validated: Dict[str, Dict[str, Any]], dedup_factor: float) -> pd.DataFrame | None:
    """Build value_bridge_matrix DataFrame with dedup applied."""
    bridge = validated.get("value-bridge-calculator", {})
    matrix = bridge.get("value_matrix", [])
    if not matrix:
        return None
    df = pd.DataFrame(matrix)
    if "deduped_mid_savings" in df.columns:
        df["deduped_mid_savings"] = df["deduped_mid_savings"] * (dedup_factor / 0.75)
    return df


def _determine_loop_control(
    validated: Dict[str, Dict[str, Any]],
    failed: Dict[str, str],
    ctx: ObserveContext,
    plan: ExecutionPlan,
) -> Tuple[bool, str | None]:
    """Determine loop_complete and next_loop_trigger per OPAR Section 4."""
    # Case 1: Hard failure — spend-profiler failed
    if "spend-profiler" in failed:
        return False, "Spend classification failed. Please review the uploaded file format."

    # Case 2: Soft failure — missing fields and low data quality
    if ctx.missing_fields and ctx.data_quality_score < 0.6:
        clarify = f"To improve confidence, please provide: {', '.join(ctx.missing_fields)}"
        return True, clarify

    # Case 3: Benchmarks done, suggest value-bridge
    benchmark_skills = {"peer-benchmarker", "internal-benchmarker", "heuristic-analyzer"}
    plan_benchmarks = {t.skill_name for t in plan.tasks if t.skill_name in benchmark_skills}
    benchmarks_complete = plan_benchmarks and all(s in validated for s in plan_benchmarks)
    value_bridge_complete = "value-bridge-calculator" in validated

    if benchmarks_complete and not value_bridge_complete:
        return True, "Benchmarking complete. Shall I calculate the value-at-the-table matrix or generate a business case?"

    # Case 4: Value bridge done, suggest business case
    if value_bridge_complete and "business-case-builder" not in [t.skill_name for t in plan.tasks]:
        return True, "Value bridge complete. Shall I generate a business case document?"

    return False, None


def _run_gate2_check(
    validated: Dict[str, Dict[str, Any]],
    ctx: ObserveContext,
) -> tuple[bool, str]:
    """Check Gate-2 promotion eligibility for all initiatives in savings-modeler output.

    Returns (gate2_blocked, narrative).
    """
    savings = validated.get("savings-modeler", {})
    if not isinstance(savings, dict):
        return False, ""
    initiatives = savings.get("initiatives", [])
    if not initiatives:
        return False, ""

    all_blocked = False
    narratives: List[str] = []
    for initiative in initiatives[:5]:  # check up to 5 to keep performance bounded
        records = assumptions_from_initiative(initiative)
        result = check_gate2(
            str(initiative.get("category_id") or initiative.get("initiative_id") or "unknown"),
            records,
        )
        if result.gate2_blocked:
            all_blocked = True
            narratives.append(result.narrative)

    combined = " | ".join(narratives[:3]) if narratives else ""
    return all_blocked, combined


def _run_reg_watcher(
    validated: Dict[str, Dict[str, Any]],
    ctx: ObserveContext,
) -> tuple[bool, List[Dict[str, Any]], str]:
    """Surface regulatory events relevant to active spend categories.

    Returns (forced_decision, events, decision_prompt).
    """
    profile = validated.get("spend-profiler", {})
    if not isinstance(profile, dict):
        return False, [], ""
    categories = [
        str(c.get("category_id") or "").lower()
        for c in profile.get("category_profile", [])
        if isinstance(c, dict)
    ]
    if not categories:
        return False, [], ""
    result = surface_at_reflect_gate(categories, engagement_week=ctx.engagement_week)
    return (
        result["forced_decision"],
        result["events"],
        result["decision_prompt"],
    )


def reflect(
    act_result: ActResult,
    plan: ExecutionPlan,
    ctx: ObserveContext,
    thinking_enabled: bool = False,
    thinking_budget_tokens: int = 8000,
) -> ReflectOutput:
    """Validate outputs (3-layer), score confidence, persist memory, determine loop control."""
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

    # Layer 4: SME critique — extract probe questions for next_options
    _sme_critique = validated.get("sme-critique", {})
    _sme_top_probes: List[Dict[str, str]] = _sme_critique.get("top_probes", []) if isinstance(_sme_critique, dict) else []

    dedup_factor = _compute_dedup_factor(validated)
    value_bridge_matrix = _build_value_bridge_matrix(validated, dedup_factor)

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

    # Resolve session currency before any response text is built so that
    # _format_currency uses ₹ Cr for INR sessions instead of hardcoded $.
    global _REFLECT_CURRENCY
    _early_analysis = _memory.get("session", ctx.session_id)
    _REFLECT_CURRENCY = str(
        (_early_analysis or {}).get("reporting_currency")
        or manifest.get("currency")
        or "INR"
    )

    advisory_sections, thinking_text = _generate_llm_advisory_sections(
        ctx, manifest, validated,
        thinking_enabled=thinking_enabled,
        thinking_budget_tokens=thinking_budget_tokens,
    )
    category_focused = _is_category_focused_request(ctx, validated)
    if advisory_sections is not None:
        response = _compose_response_from_advisory(
            advisory_sections,
            validated,
            include_executive_takeaway=bool(ctx.wants_executive_narrative),
            include_business_case_metrics=bool(ctx.intent_class == "business_case"),
            category_focused=category_focused,
        )
    else:
        response = _build_response_text(validated, failed, plan, ctx)
    artefacts: list[str] = []
    next_options: list[Dict[str, str]] = []
    quality_signals = _compute_quality_signals(validated, failed, ctx, degradation_reasons=degradation_reasons)
    grounding_coverage = _compute_grounding_coverage(response, validated)
    quality_signals["grounding_coverage"] = grounding_coverage
    if grounding_coverage < 0.2 and validated:
        recs = _recommendation_rows(validated, max_items=2)
        if recs:
            evidence_lines = ["", "**Evidence anchors**"]
            for rec in recs:
                evidence_lines.append(
                    f"- {rec['category']}: {_format_currency(rec['dedup_mid'])} modeled via {rec.get('lever_label', rec['lever'])}."
                )
            response = (response + "\n" + "\n".join(evidence_lines)).strip()

    # Persist merged session analysis so follow-up asks (e.g. "open spend chart")
    # can reuse previously generated artefacts without rerunning full flows.
    if validated:
        existing_analysis = _memory.get("session", ctx.session_id)
        analysis_snapshot: Dict[str, Any] = dict(existing_analysis) if isinstance(existing_analysis, dict) else {}
        merged_outputs: Dict[str, Any] = {}
        prior_outputs = analysis_snapshot.get("skill_outputs", {})
        if isinstance(prior_outputs, dict):
            merged_outputs.update(prior_outputs)
        merged_outputs.update(validated)
        analysis_snapshot.update({
            "session_id": ctx.session_id,
            "engagement_id": manifest.get("engagement_id") or analysis_snapshot.get("engagement_id") or getattr(ctx, "engagement_id", None),
            "company_name": manifest.get("company_name") or analysis_snapshot.get("company_name"),
            "industry": manifest.get("industry") or analysis_snapshot.get("industry") or "",
            "annual_revenue": float(manifest.get("annual_revenue") or analysis_snapshot.get("annual_revenue") or 0),
            "reporting_currency": _REFLECT_CURRENCY,
            "normalized_spend": analysis_snapshot.get("normalized_spend", []),
            "context_summary": analysis_snapshot.get("context_summary", ""),
            "analysis_trace": analysis_snapshot.get("analysis_trace", []),
            "wacc": manifest.get("wacc", analysis_snapshot.get("wacc")),
            "effective_tax_rate": manifest.get("effective_tax_rate", analysis_snapshot.get("effective_tax_rate")),
            "skill_outputs": merged_outputs,
            "advisory_sections": advisory_sections.model_dump() if advisory_sections else analysis_snapshot.get("advisory_sections", {}),
            "response_artefacts": act_result.response_artefacts if hasattr(act_result, "response_artefacts") else analysis_snapshot.get("response_artefacts", []),
            "last_run_intent": ctx.intent_class,
            "skills_run_this_turn": list(validated.keys()),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        _memory.put("session", ctx.session_id, analysis_snapshot)

    if "conflict-detector" in validated and manifest_path.parent.exists():
        cd = validated["conflict-detector"]
        if isinstance(cd, dict):
            manifest["conflict_state"] = {
                "total": int(cd.get("conflict_count") or cd.get("total") or 0),
                "unresolved": int(cd.get("unresolved") or 0),
                "by_type": cd.get("by_type") or {},
                "has_intercompany": bool((cd.get("by_type") or {}).get("intercompany_inflation")),
            }
            write_json(manifest_path, manifest)

    # Business case: show in chat only; do NOT auto-create docx. User must ask to export.
    if "business-case-builder" in validated:
        next_options.append({"label": "Export as document", "message": "Export the business case as a document"})

    # Value bridge done, suggest business case
    if "value-bridge-calculator" in validated and "business-case-builder" not in validated:
        next_options.append({"label": "Generate business case", "message": "Generate business case"})

    # SME probe CTAs — prepend the top probe questions so user's first action
    # is to answer the critical assumption, not jump to a business case.
    if _sme_top_probes:
        probe_ctas: list[Dict[str, str]] = []
        for probe in _sme_top_probes[:3]:
            label = str(probe.get("chat_cta") or probe.get("question", ""))[:60]
            question = str(probe.get("question") or "")
            if label and question:
                probe_ctas.append({"label": label, "message": question})
        # Insert before the first next_option so probes appear at the top
        next_options = probe_ctas + next_options

    chart_url = validated.get("chart-builder", {}).get("chart_url")
    if chart_url:
        artefacts.append(chart_url)
        next_options.append({"label": "Open spend chart", "message": "Show spend profile chart"})

    # Benchmarking done, suggest value bridge
    benchmark_skills = {"peer-benchmarker", "internal-benchmarker", "heuristic-analyzer"}
    if all(s in validated for s in benchmark_skills) and "value-bridge-calculator" not in validated:
        next_options.append({"label": "Calculate value-at-the-table", "message": "Calculate the value-at-the-table matrix"})

    # Phase 2: Conflict-aware next options
    unresolved_conflicts = getattr(ctx, "unresolved_conflict_count", 0)
    multi_source = getattr(ctx, "multi_source_upload", False)
    has_ic = getattr(ctx, "has_intercompany_lines", False)

    if unresolved_conflicts > 0:
        next_options.append({
            "label": f"Resolve {unresolved_conflicts} data conflict{'s' if unresolved_conflicts != 1 else ''}",
            "message": "Show me all unresolved conflicts and resolution options",
        })
    elif multi_source and not unresolved_conflicts:
        # Multi-source upload detected but no conflict run yet — prompt user to trigger it
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

    # Phase 3: Gate-2 assumption quality check
    gate2_blocked, gate2_narrative = _run_gate2_check(validated, ctx)
    if gate2_blocked:
        next_options.append({
            "label": "Review assumption quality",
            "message": "Show me the assumption quality issues blocking Gate-2",
        })

    # Phase 3: Regulatory event watcher
    forced_reg_decision, reg_events, reg_prompt = _run_reg_watcher(validated, ctx)
    if forced_reg_decision:
        next_options.append({
            "label": "Review regulatory events",
            "message": "Show me the regulatory events requiring a decision",
        })

    # Phase 3: Narrative provenance — record if LLM synthesis was used
    provenance_tag: Dict[str, Any] | None = None
    if advisory_sections and advisory_sections.executive_takeaway:
        try:
            provenance_tag = record_llm_narrative(
                narrative=advisory_sections.executive_takeaway,
                engagement_id=getattr(ctx, "engagement_id", ctx.session_id),
                turn_id=ctx.turn_id,
                skill_outputs_used=list(validated.keys()),
                prompt_text=ctx.user_message,
                model_version="claude-sonnet-4-6",
                seed=0,
            )
        except Exception:
            provenance_tag = None

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
        used_llm_synthesis=bool(validated.get("analysis-synthesizer") or validated.get("executive-communication") or advisory_sections),
        thinking_text=thinking_text,
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


def _format_business_case_for_chat(bc: Dict[str, Any]) -> str:
    """Format business case dict for display in chat (no docx created)."""
    sections = bc.get("sections", {})
    lines = [f"**Business Case** (generated {bc.get('generated_on', '')})", ""]
    for key, value in sections.items():
        title = key.replace("_", " ").title()
        lines.append(f"**{title}**")
        if isinstance(value, str):
            lines.append(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict) and "deduped_mid_savings" in item:
                    cat = item.get("category_id", item.get("category_name", ""))
                    lines.append(f"• {cat}: ${item.get('deduped_mid_savings', 0):,.0f} savings")
                elif isinstance(item, dict):
                    lines.append(f"• {item}")
                else:
                    lines.append(f"• {item}")
        else:
            lines.append(str(value))
        lines.append("")
    return "\n".join(lines).strip()


# Set by reflect() before building any response text so all _format_currency
# calls use the session's actual reporting currency instead of a hardcoded $.
_REFLECT_CURRENCY: str = "INR"


def _format_currency(value: float) -> str:
    return format_money(float(value or 0), _REFLECT_CURRENCY)


def _business_lever_label(lever: str) -> str:
    mapping = {
        "internal_best_practice": "process standardization and operating model redesign",
        "process_standardization": "process standardization and operating model redesign",
        "supplier_consolidation": "supplier consolidation and lane/package rebundling",
        "contract_renegotiation": "commercial renegotiation with should-cost and volume commitments",
        "maverick_compliance": "guided buying and policy compliance enforcement",
        "demand_management": "demand challenge and specification-to-need control",
        "automation": "workflow automation and touchless processing",
        "payment_terms": "payment-term harmonization and DPO optimization",
        "insourcing": "insource where structural unit economics are favorable",
        "outsourcing": "outsource to scale providers for lower delivered unit cost",
    }
    if not lever:
        return "targeted procurement optimization"
    return mapping.get(lever, lever.replace("_", " "))


def _executive_callouts(validated: Dict[str, Dict[str, Any]]) -> List[str]:
    out: List[str] = []
    bva = validated.get("bva-analyzer", {})
    if isinstance(bva, dict) and bva.get("bva_available"):
        variances = bva.get("variances", [])
        over = next((v for v in variances if v.get("flag") == "over_budget"), None)
        if over:
            pct = over.get("variance_pct")
            pct_txt = f"{pct:.1f}%" if isinstance(pct, (int, float)) else "materially"
            out.append(
                f"{over.get('category_name', over.get('category_id', 'A major category'))} is {pct_txt} over budget "
                f"({_format_currency(over.get('actual_spend', 0))} actual vs {_format_currency(over.get('budget_spend', 0))} budget)."
            )

    internal = validated.get("internal-benchmarker", {})
    if isinstance(internal, dict):
        totals: Dict[str, float] = {}
        for row in internal.get("internal_variance", []):
            for seg in row.get("segments", []):
                name = str(seg.get("segment") or "Unknown segment")
                totals[name] = totals.get(name, 0.0) + float(seg.get("spend", 0.0))
        if totals:
            seg, amt = max(totals.items(), key=lambda x: x[1])
            out.append(f"{seg} is currently the largest internal spend footprint at {_format_currency(amt)}.")
    return out[:2]


def _recommendation_rows(validated: Dict[str, Dict[str, Any]], max_items: int = 3) -> List[Dict[str, Any]]:
    bridge = validated.get("value-bridge-calculator", {})
    matrix = bridge.get("value_matrix", [])
    if not matrix:
        return []

    peer_rows = {
        r.get("category_id"): r
        for r in validated.get("peer-benchmarker", {}).get("comparisons", [])
        if isinstance(r, dict) and r.get("category_id")
    }
    internal_rows = {
        r.get("category_id"): r
        for r in validated.get("internal-benchmarker", {}).get("internal_variance", [])
        if isinstance(r, dict) and r.get("category_id")
    }
    heuristic_rows = {
        r.get("category_id"): r
        for r in validated.get("heuristic-analyzer", {}).get("heuristic_findings", [])
        if isinstance(r, dict) and r.get("category_id")
    }
    root_rows = {
        r.get("category_id"): r
        for r in validated.get("root-cause-analyzer", {}).get("root_cause_findings", [])
        if isinstance(r, dict) and r.get("category_id")
    }
    modeled_rows = {
        r.get("category_id"): r
        for r in validated.get("savings-modeler", {}).get("initiatives", [])
        if isinstance(r, dict) and r.get("category_id")
    }
    constraints = validated.get("document-contextualizer", {}).get("constraints", [])
    top_constraint = constraints[0] if constraints else ""

    def _rank_key(item: Dict[str, Any]) -> tuple[float, float]:
        lever = str(item.get("lever") or "")
        penalty = 0.6 if lever == "internal_best_practice" else 1.0
        return (
            float(item.get("deduped_mid_savings", 0.0)) * penalty,
            float(item.get("deduped_mid_savings", 0.0)),
        )

    ranked = sorted(matrix, key=_rank_key, reverse=True)[:max_items]
    out: List[Dict[str, Any]] = []
    for item in ranked:
        cid = item.get("category_id")
        category = item.get("category_name") or cid or "Unknown category"
        lever = item.get("lever") or "optimization"
        lever_label = _business_lever_label(lever)
        dedup_mid = float(item.get("deduped_mid_savings", 0.0))
        npv = float(item.get("net_npv", 0.0))
        payback = int(item.get("payback_months", 0) or 0)
        confidence = item.get("confidence") or "medium"

        evidence: List[str] = []
        peer = peer_rows.get(cid, {})
        if peer:
            actual = float(peer.get("actual_pct_of_revenue", 0.0))
            p50 = float(peer.get("benchmark_p50_pct", 0.0))
            gap = max(actual - p50, 0.0)
            evidence.append(
                f"Peer gap: actual {actual:.2f}% of revenue vs P50 {p50:.2f}% (gap {gap:.2f} pts, band {peer.get('percentile_band', 'n/a')})."
            )

        internal = internal_rows.get(cid, {})
        if internal:
            spread = float(internal.get("internal_spread", 0.0)) * 100
            segments = internal.get("segments", []) if isinstance(internal.get("segments"), list) else []
            if segments:
                sorted_segments = sorted(
                    [s for s in segments if isinstance(s, dict)],
                    key=lambda x: float(x.get("spend", 0.0) or 0.0),
                    reverse=True,
                )
                best = sorted_segments[-1] if sorted_segments else {}
                worst = sorted_segments[0] if sorted_segments else {}
                evidence.append(
                    "Internal variance: "
                    f"{spread:.1f}% spread; highest spend segment "
                    f"{worst.get('segment', 'Unknown')} at {_format_currency(worst.get('spend', 0.0))} "
                    f"vs lowest spend segment {best.get('segment', 'Unknown')} at {_format_currency(best.get('spend', 0.0))}."
                )
            else:
                evidence.append(f"Internal variance: {spread:.1f}% spread between best and worst performing segments.")

        heur = heuristic_rows.get(cid, {})
        if heur:
            actual_h = float(heur.get("actual_pct_of_revenue", 0.0))
            target_h = float(heur.get("heuristic_target_pct", 0.0))
            gap_h = max(actual_h - target_h, 0.0)
            evidence.append(f"Heuristic gap: {actual_h:.2f}% vs target {target_h:.2f}% (gap {gap_h:.2f} pts).")

        root = root_rows.get(cid, {})
        if root.get("root_causes"):
            top_cause = root.get("root_causes", [{}])[0]
            diagnosis = top_cause.get("diagnosis", "No diagnosis available")
            addr = float(top_cause.get("addressable_spend", 0.0))
            evidence.append(f"Root-cause signal: {diagnosis}. Addressable spend estimate {_format_currency(addr)}.")

        modeled = modeled_rows.get(cid, {})
        if modeled:
            gross_3yr = float(modeled.get("gross_savings", {}).get("total_3yr", 0.0))
            cta_3yr = float(modeled.get("cost_to_achieve", {}).get("total_3yr", 0.0))
            evidence.append(
                f"Modeled economics: gross 3Y {_format_currency(gross_3yr)}, cost-to-achieve {_format_currency(cta_3yr)}."
            )

        if top_constraint:
            evidence.append(f"Execution constraint from documents: {top_constraint}.")

        out.append(
            {
                "category": category,
                "lever": lever,
                "lever_label": lever_label,
                "dedup_mid": dedup_mid,
                "npv": npv,
                "payback_months": payback,
                "confidence": confidence,
                "evidence": evidence[:4],
            }
        )
    return out


def _format_conflict_line(conflict: Dict[str, Any]) -> str:
    ctype = str(conflict.get("conflict_type") or "unknown")
    label = _CONFLICT_TYPE_LABELS.get(ctype, ctype.replace("_", " ").title())
    severity = str(conflict.get("severity") or "medium")
    source_a = conflict.get("source_a") or "source A"
    source_b = conflict.get("source_b") or "source B"
    parts = [f"**{label}** ({severity}): {source_a} vs {source_b}"]
    amount_a = conflict.get("amount_a")
    amount_b = conflict.get("amount_b")
    if amount_a is not None and amount_b is not None:
        parts.append(
            f"amounts {_format_currency(float(amount_a))} vs {_format_currency(float(amount_b))}"
        )
    delta = conflict.get("delta_pct")
    if delta is not None:
        try:
            parts.append(f"delta {float(delta):+.1f}%")
        except (TypeError, ValueError):
            pass
    notes = conflict.get("resolution_notes")
    if notes:
        parts.append(str(notes))
    return "- " + " — ".join(parts)


def _format_conflict_detection_response(conflict_data: Dict[str, Any]) -> str:
    total = int(conflict_data.get("conflict_count") or conflict_data.get("total") or 0)
    unresolved = int(conflict_data.get("unresolved") or 0)
    by_type = conflict_data.get("by_type") or {}
    conflicts = conflict_data.get("conflicts") or []

    if total <= 0:
        return (
            "**Cross-source check complete** — no TDS, GST, or vendor conflicts detected "
            "across the uploaded sources in this session."
        )

    lines = [
        f"**Cross-source conflicts: {total} found**"
        + (f" ({unresolved} unresolved)" if unresolved else ""),
    ]
    if by_type:
        type_bits = [
            f"{_CONFLICT_TYPE_LABELS.get(k, k.replace('_', ' '))}: {v}"
            for k, v in sorted(by_type.items(), key=lambda x: -x[1])
        ]
        lines.append("By type: " + "; ".join(type_bits) + ".")
    lines.append("")
    lines.append("**Findings**")
    for conflict in conflicts[:12]:
        if isinstance(conflict, dict):
            lines.append(_format_conflict_line(conflict))
    if len(conflicts) > 12:
        lines.append(f"- …and {len(conflicts) - 12} more (open Cost Room or ask to resolve).")
    auto = int(conflict_data.get("auto_resolvable") or 0)
    escalate = int(conflict_data.get("requires_escalation") or 0)
    if auto or escalate:
        lines.append("")
        lines.append(
            f"Resolution: {auto} auto-resolvable, {escalate} need controller/CFO review."
        )
    return "\n".join(lines)


def _build_response_text(
    validated: Dict[str, Dict],
    failed: Dict[str, str],
    plan: ExecutionPlan,
    ctx: ObserveContext | None = None,
) -> str:
    conflict_data = validated.get("conflict-detector")
    if conflict_data and isinstance(conflict_data, dict):
        conflict_text = _format_conflict_detection_response(conflict_data)
        if ctx and ctx.intent_class == "conflict_review":
            prefix_parts: list[str] = []
            profiler = validated.get("spend-profiler", {})
            if profiler:
                prefix_parts.append(
                    f"Scanned uploaded sources — {len(profiler.get('category_profile', []))} categories, "
                    f"total {_format_currency(profiler.get('total_spend', 0))}."
                )
            if failed:
                prefix_parts.append(
                    f"Errors: {', '.join(f'{k}: {v}' for k, v in failed.items())}."
                )
            if prefix_parts:
                return "\n\n".join(prefix_parts) + "\n\n" + conflict_text
            return conflict_text

    category_focused = _is_category_focused_request(ctx, validated)
    communication = validated.get("executive-communication", {})
    if communication and communication.get("message"):
        p = validated.get("spend-profiler", {})
        b = validated.get("value-bridge-calculator", {})
        peer = validated.get("peer-benchmarker", {})
        ds = peer.get("benchmark_dataset", {}) if isinstance(peer, dict) else {}
        bands = b.get("confidence_bands", {}) if isinstance(b, dict) else {}
        lines: list[str] = []
        if p:
            lines.append(
                f"Spend profile: {len(p.get('category_profile', []))} categories, total {_format_currency(p.get('total_spend', 0))}."
            )
        if bands:
            lines.append(
                f"Value bridge: mid-case savings {_format_currency(bands.get('mid', 0))} "
                f"(low: {_format_currency(bands.get('low', 0))}, high: {_format_currency(bands.get('high', 0))})."
            )
        if ds:
            source = ds.get("source") or "unknown"
            vintage = ds.get("vintage_date") or "unknown"
            specificity = ds.get("specificity_score")
            if specificity is None:
                lines.append(f"Benchmarked using {source} (vintage {vintage}).")
            else:
                try:
                    spec_pct = f"{float(specificity):.0%}"
                except Exception:
                    spec_pct = str(specificity)
                lines.append(f"Benchmarked using {source} (vintage {vintage}, specificity {spec_pct}).")
        if lines:
            lines.append("")
        callouts = _executive_callouts(validated)
        if callouts:
            lines.append("**CFO Call-outs**")
            for c in callouts:
                lines.append(f"- {c}")
            lines.append("")
        lines.append(communication.get("message", ""))
        if failed:
            lines.append("")
            lines.append(f"Validation/errors: {', '.join(f'{k}: {v}' for k, v in failed.items())}.")
        return "\n".join(lines).strip()

    synthesis = validated.get("analysis-synthesizer", {})
    if synthesis:
        p = validated.get("spend-profiler", {})
        b = validated.get("value-bridge-calculator", {})
        peer = validated.get("peer-benchmarker", {})
        ds = peer.get("benchmark_dataset", {}) if isinstance(peer, dict) else {}
        bands = b.get("confidence_bands", {}) if isinstance(b, dict) else {}
        executive_takeaway = synthesis.get("executive_takeaway", "")
        recs = synthesis.get("recommendations", [])
        assumptions = synthesis.get("assumptions", [])
        lines: list[str] = []
        if p:
            lines.append(
                f"Spend profile: {len(p.get('category_profile', []))} categories, total {_format_currency(p.get('total_spend', 0))}."
            )
        if bands:
            lines.append(
                f"Value bridge: mid-case savings {_format_currency(bands.get('mid', 0))} "
                f"(low: {_format_currency(bands.get('low', 0))}, high: {_format_currency(bands.get('high', 0))})."
            )
        if ds:
            source = ds.get("source") or "unknown"
            vintage = ds.get("vintage_date") or "unknown"
            specificity = ds.get("specificity_score")
            if specificity is None:
                lines.append(f"Benchmarked using {source} (vintage {vintage}).")
            else:
                try:
                    spec_pct = f"{float(specificity):.0%}"
                except Exception:
                    spec_pct = str(specificity)
                lines.append(f"Benchmarked using {source} (vintage {vintage}, specificity {spec_pct}).")
        if lines:
            lines.append("")
        if executive_takeaway and ctx and ctx.wants_executive_narrative:
            lines.append("**Executive Takeaway**")
            lines.append(executive_takeaway)
            lines.append("")
        if recs:
            lines.append(
                "**Focused category actions (LLM-Synthesized, Skill-Grounded)**"
                if category_focused
                else "**Top Recommendations (LLM-Synthesized, Skill-Grounded)**"
            )
            for rec in recs[:4]:
                fin = rec.get("financials", {})
                conf = rec.get("confidence", {})
                lever_raw = str(rec.get("lever", "optimization"))
                lever_label = _business_lever_label(lever_raw)
                if ctx and ctx.intent_class == "business_case":
                    impact_text = (
                        f"mid-case {_format_currency(fin.get('mid_case_savings', 0))}, "
                        f"NPV {_format_currency(fin.get('net_npv', 0))}, "
                        f"payback {int(fin.get('payback_months', 0) or 0)} months"
                    )
                else:
                    impact_text = (
                        f"modeled value release {_format_currency(fin.get('mid_case_savings', 0))} "
                        "(request business case for NPV/payback)"
                    )
                lines.append(
                    f"- **{rec.get('category_name', rec.get('category_id', 'Unknown'))}** via **{lever_label}**: "
                    f"{impact_text}, confidence {conf.get('level', 'mid')}."
                )
                for ev in rec.get("evidence", [])[:3]:
                    lines.append(f"  - [{ev.get('source', 'source')}] {ev.get('detail', '')}")
                for ex in rec.get("examples", [])[:2]:
                    supplier = ex.get("supplier", "Unknown supplier")
                    description = ex.get("description", "N/A")
                    amount = _format_currency(ex.get("amount", 0))
                    why = ex.get("why_relevant", "Supports this recommendation")
                    lines.append(f"  - Example: {supplier} | {description} | {amount} ({why})")
                decisions = rec.get("decisions_required", [])
                if decisions:
                    lines.append(f"  - Decision required: {decisions[0]}")
            lines.append("")
        if assumptions:
            lines.append("**Key Assumptions**")
            for a in assumptions[:4]:
                lines.append(f"- {a}")
        if lines:
            if failed:
                lines.append("")
                lines.append(f"Validation/errors: {', '.join(f'{k}: {v}' for k, v in failed.items())}.")
            return "\n".join(lines).strip()

    parts = []
    if conflict_data and isinstance(conflict_data, dict):
        parts.append(_format_conflict_detection_response(conflict_data))
    if validated.get("spend-profiler"):
        p = validated["spend-profiler"]
        parts.append(f"Spend profile: {len(p.get('category_profile', []))} categories, total {_format_currency(p.get('total_spend', 0))}.")
        chart = validated.get("chart-builder", {})
        if chart:
            chart_lines: list[str] = ["**Spend Profile Chart View**"]
            if chart.get("chart_url"):
                chart_lines.append(f"[Open chart view]({chart.get('chart_url')})")
            commentary = chart.get("commentary_points", [])
            if commentary:
                chart_lines.append("**Chart Commentary (FP&A Lens)**")
                for c in commentary[:5]:
                    chart_lines.append(f"- {c}")
            parts.append("\n".join(chart_lines))
    if validated.get("peer-benchmarker"):
        peer = validated["peer-benchmarker"]
        ds = peer.get("benchmark_dataset", {}) if isinstance(peer, dict) else {}
        source = ds.get("source") or "unknown"
        vintage = ds.get("vintage_date") or "unknown"
        specificity = ds.get("specificity_score")
        if specificity is None:
            parts.append(f"Benchmarked using {source} (vintage {vintage}).")
        else:
            try:
                spec_pct = f"{float(specificity):.0%}"
            except Exception:
                spec_pct = str(specificity)
            parts.append(f"Benchmarked using {source} (vintage {vintage}, specificity {spec_pct}).")
    bva = validated.get("bva-analyzer", {})
    if bva.get("bva_available"):
        variances = bva.get("variances", [])
        overruns = [v for v in variances if v.get("flag") == "over_budget" and v.get("variance_pct")]
        if overruns:
            over_text = ", ".join(
                f"{v['category_name']} ({v.get('variance_pct', 0):+.1f}%)"
                for v in sorted(overruns, key=lambda x: abs(x.get("variance_pct") or 0), reverse=True)[:3]
            )
            total_var = bva.get("total_variance", 0)
            total_var_pct = bva.get("total_variance_pct", 0) or 0
            parts.append(
                f"**Budget vs. Actuals:** {len(overruns)} {'category' if len(overruns) == 1 else 'categories'} over budget — "
                f"{over_text}. Total spend variance: {_format_currency(total_var)} ({total_var_pct:+.1f}% vs budget)."
            )

    msme = validated.get("msme-compliance-checker", {})
    if msme.get("msme_data_available") and msme.get("at_risk_count", 0) > 0:
        at_risk_count = msme["at_risk_count"]
        at_risk_spend = _format_currency(msme.get("at_risk_spend", 0))
        penalty = _format_currency(msme.get("penalty_exposure", 0))
        parts.append(
            f"**MSME Compliance Risk:** {at_risk_count} payment{'s' if at_risk_count > 1 else ''} to MSME vendors "
            f"at risk of breaching the 45-day payment limit (Section 15 MSMED Act). "
            f"At-risk spend: {at_risk_spend}. Estimated penalty exposure: {penalty}."
        )

    contracts = validated.get("contract-lifecycle-manager", {})
    renewal_alerts = contracts.get("renewal_alerts", [])
    if renewal_alerts:
        urgent = [a for a in renewal_alerts if (a.get("days_to_expiry") or 999) <= 60]
        if urgent:
            alert_text = ", ".join(
                f"{a['supplier']} ({a.get('days_to_expiry', '?')}d)"
                for a in urgent[:3]
            )
            penalty_exposure = _format_currency(contracts.get("exit_penalty_exposure", 0))
            parts.append(
                f"**Contract Renewal Alerts:** {len(urgent)} contract{'s' if len(urgent) > 1 else ''} expiring within 60 days — "
                f"{alert_text}. Exit penalty exposure: {penalty_exposure}."
            )

    if validated.get("value-bridge-calculator"):
        b = validated["value-bridge-calculator"]
        bands = b.get("confidence_bands", {})
        parts.append(
            f"Value bridge: mid-case savings {_format_currency(bands.get('mid', 0))} "
            f"(low: {_format_currency(bands.get('low', 0))}, high: {_format_currency(bands.get('high', 0))})."
        )
        if ctx:
            focused = _build_focus_category_section(ctx, validated)
            if focused:
                parts.append(focused)

        recs = _recommendation_rows(validated)
        if recs:
            total_mid = float(bands.get("mid", 0.0))
            top_mid = sum(r["dedup_mid"] for r in recs)
            concentration = (top_mid / total_mid * 100) if total_mid > 0 else 0.0
            focus_row = _match_focus_category(ctx, validated) if ctx else None
            if focus_row:
                focus_name = focus_row.get("category_name") or focus_row.get("category_id") or "the selected category"
                focus_mid = float(focus_row.get("deduped_mid_savings", 0.0) or 0.0)
                executive_takeaway = (
                    f"{focus_name} is the primary focus for this request, with modeled mid-case impact "
                    f"of {_format_currency(focus_mid)} and clear lever-driven actions to execute."
                )
            else:
                executive_takeaway = (
                    f"The top {len(recs)} initiatives represent {_format_currency(top_mid)} of modeled impact "
                    f"({concentration:.1f}% of mid-case opportunity)."
                )
            lines = []
            if ctx and ctx.wants_executive_narrative:
                lines.extend(
                    [
                        "**Executive Takeaway**",
                        executive_takeaway,
                        "",
                    ]
                )
            lines.append(
                "**Focused category actions (Data-Backed)**"
                if category_focused
                else "**Top Recommendations (Data-Backed)**"
            )
            callouts = _executive_callouts(validated)
            if callouts:
                lines.insert(3, "")
                lines.insert(3, callouts[0] if len(callouts) == 1 else f"CFO call-outs: {callouts[0]} {callouts[1]}")
            for i, r in enumerate(recs, 1):
                payback_text = f"{r['payback_months']} months" if r["payback_months"] > 0 else "not yet established"
                if ctx and ctx.intent_class == "business_case":
                    impact_line = (
                        f"mid-case {_format_currency(r['dedup_mid'])}, NPV {_format_currency(r['npv'])}, "
                        f"payback {payback_text}, confidence {r['confidence']}."
                    )
                else:
                    impact_line = (
                        f"modeled value release {_format_currency(r['dedup_mid'])}, confidence {r['confidence']}. "
                        "Ask for a business case to see NPV/payback economics."
                    )
                lines.append(
                    f"{i}. **{r['category']}** via **{r.get('lever_label', r['lever'])}** — "
                    f"{impact_line}"
                )
                evidence_preview = r["evidence"][0] if r["evidence"] else "Measured gap identified in benchmark and diagnostic signals."
                lines.append(
                    "   - Value-release logic: close the measured gap referenced below, codify the change in policy/commercial terms "
                    f"for this category, and convert recurring leakage into realized run-rate savings. ({evidence_preview})"
                )
                for ev in r["evidence"]:
                    lines.append(f"   - {ev}")
            parts.append("\n".join(lines))

        checks = validated.get("data-validator", {}).get("checks", {})
        if checks:
            failed_checks = [k for k, v in checks.items() if not v]
            if failed_checks:
                parts.append(f"Validation cautions: {', '.join(failed_checks)}.")
            else:
                parts.append("Validation checks passed: monotonic bands, non-negative values, non-empty matrix.")
    if validated.get("business-case-builder"):
        bc = validated["business-case-builder"].get("business_case", {})
        if bc:
            parts.append(_format_business_case_for_chat(bc))
        else:
            parts.append("Business case prepared.")
    if failed:
        parts.append(f"Errors: {', '.join(f'{k}: {v}' for k, v in failed.items())}.")
    return "\n\n".join(parts) if parts else plan.user_summary
