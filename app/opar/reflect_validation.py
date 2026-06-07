"""Reflect validation — 3-layer schema/coherence checks, confidence, quality signals."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Tuple

import pandas as pd

from app.opar.models import ConfidenceScore, ExecutionPlan, ObserveContext
from app.opar.quality import assumptions_from_initiative, check_gate2
from app.services.reg_watcher import surface_at_reflect_gate
from app.skills.contracts import (
    validate_analysis_synthesizer_output,
    validate_core_skill_outputs,
    validate_executive_communication_output,
    validate_peer_benchmarker_output,
)
from app.opar.reflect_synthesis import format_currency, match_focus_category


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

    focus_match = match_focus_category(ctx, validated)
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
        tokens.append(format_currency(total))
    for row in profile.get("category_profile", [])[:6]:
        name = str(row.get("category_name") or "").strip()
        if name:
            tokens.append(name)
    for row in validated.get("value-bridge-calculator", {}).get("value_matrix", [])[:6]:
        mid = float(row.get("deduped_mid_savings", 0.0) or 0.0)
        if mid > 0:
            tokens.append(format_currency(mid))
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
        level: Literal["low", "mid", "high"] = "mid"
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
