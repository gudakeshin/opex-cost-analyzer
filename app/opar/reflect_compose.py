"""Reflect response composition — advisory and deterministic response builders."""
from __future__ import annotations

from typing import Any, Dict, List

from app.opar.models import AdvisorySections, ExecutionPlan, ObserveContext
from app.opar.qa_lookup import answer_general_qa, build_sme_critique_section, is_interactive_savings_query
from app.opar.reflect_conflicts import format_conflict_detection_response
from app.opar.reflect_context import (
    build_analysis_context_lines,
    format_benchmark_attribution_line,
    format_spend_profile_line,
    format_value_bridge_line,
)
from app.opar.reflect_currency import format_currency, get_reflect_currency
from app.opar.reflect_focus import (
    build_focus_category_section,
    executive_callouts,
    is_category_focused_request,
    recommendation_rows,
)
from app.opar.reflect_recommendations import (
    append_validation_errors,
    build_data_backed_recommendation_lines,
    build_synthesizer_recommendation_lines,
)

def compose_response_from_advisory(
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
            f"Modeled value-release opportunity: mid-case {format_currency(bands.get('mid', 0))} "
            f"(low {format_currency(bands.get('low', 0))}, high {format_currency(bands.get('high', 0))})."
        )
        lines.append("")
    sme_narrative = (advisory.sme_qualification_narrative or "").strip()
    if sme_narrative:
        lines.append("**SME qualification**")
        lines.append(sme_narrative)
        lines.append("")
    else:
        sme_block = build_sme_critique_section(validated, get_reflect_currency())
        if sme_block:
            lines.append(sme_block)
            lines.append("")
    if include_executive_takeaway and advisory.executive_takeaway:
        lines.append("**Executive takeaway**")
        lines.append(advisory.executive_takeaway)
        # If the LLM takeaway is too short, enrich it with explicit value logic.
        if len((advisory.executive_takeaway or "").strip()) < 260:
            recs = recommendation_rows(validated, max_items=2)
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
                            f"{format_currency(rec['dedup_mid'])} modeled mid-case impact with {format_currency(rec['npv'])} NPV."
                        )
                    else:
                        lines.append(
                            f"- In **{rec['category']}**, the core mechanism is **{rec.get('lever_label', rec['lever'])}**: "
                            f"close the identified gap through concrete operating/commercial changes, translating to "
                            f"{format_currency(rec['dedup_mid'])} modeled value release."
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
def format_business_case_for_chat(bc: Dict[str, Any]) -> str:
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
                    lines.append(f"• {cat}: {format_currency(float(item.get('deduped_mid_savings', 0) or 0))} savings")
                elif isinstance(item, dict):
                    lines.append(f"• {item}")
                else:
                    lines.append(f"• {item}")
        else:
            lines.append(str(value))
        lines.append("")
    return "\n".join(lines).strip()


def build_response_text(
    validated: Dict[str, Dict],
    failed: Dict[str, str],
    plan: ExecutionPlan,
    ctx: ObserveContext | None = None,
) -> str:
    conflict_data = validated.get("conflict-detector")
    if conflict_data and isinstance(conflict_data, dict):
        conflict_text = format_conflict_detection_response(conflict_data)
        if ctx and ctx.intent_class == "conflict_review":
            prefix_parts: list[str] = []
            profiler = validated.get("spend-profiler", {})
            if profiler:
                prefix_parts.append(
                    f"Scanned uploaded sources — {len(profiler.get('category_profile', []))} categories, "
                    f"total {format_currency(profiler.get('total_spend', 0))}."
                )
            if failed:
                prefix_parts.append(
                    f"Errors: {', '.join(f'{k}: {v}' for k, v in failed.items())}."
                )
            if prefix_parts:
                return "\n\n".join(prefix_parts) + "\n\n" + conflict_text
            return conflict_text

    category_focused = is_category_focused_request(ctx, validated)
    communication = validated.get("executive-communication", {})
    if communication and communication.get("message"):
        lines: list[str] = build_analysis_context_lines(validated)
        if lines:
            lines.append("")
        callouts = executive_callouts(validated)
        if callouts:
            lines.append("**CFO Call-outs**")
            for c in callouts:
                lines.append(f"- {c}")
            lines.append("")
        lines.append(communication.get("message", ""))
        append_validation_errors(lines, failed)
        return "\n".join(lines).strip()

    synthesis = validated.get("analysis-synthesizer", {})
    if synthesis:
        executive_takeaway = synthesis.get("executive_takeaway", "")
        recs = synthesis.get("recommendations", [])
        assumptions = synthesis.get("assumptions", [])
        lines: list[str] = build_analysis_context_lines(validated)
        if lines:
            lines.append("")
        if executive_takeaway and ctx and ctx.wants_executive_narrative:
            lines.append("**Executive Takeaway**")
            lines.append(executive_takeaway)
            lines.append("")
        lines.extend(build_synthesizer_recommendation_lines(recs, ctx, category_focused=category_focused))
        if assumptions:
            lines.append("**Key Assumptions**")
            for a in assumptions[:4]:
                lines.append(f"- {a}")
        if lines:
            append_validation_errors(lines, failed)
            return "\n".join(lines).strip()

    parts = []
    if conflict_data and isinstance(conflict_data, dict):
        parts.append(format_conflict_detection_response(conflict_data))
    spend_line = format_spend_profile_line(validated)
    if spend_line:
        parts.append(spend_line)
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
    bench_line = format_benchmark_attribution_line(validated)
    if bench_line:
        parts.append(bench_line)
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
                f"{over_text}. Total spend variance: {format_currency(total_var)} ({total_var_pct:+.1f}% vs budget)."
            )

    msme = validated.get("msme-compliance-checker", {})
    if msme.get("msme_data_available") and msme.get("at_risk_count", 0) > 0:
        at_risk_count = msme["at_risk_count"]
        at_risk_spend = format_currency(msme.get("at_risk_spend", 0))
        penalty = format_currency(msme.get("penalty_exposure", 0))
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
            penalty_exposure = format_currency(contracts.get("exit_penalty_exposure", 0))
            parts.append(
                f"**Contract Renewal Alerts:** {len(urgent)} contract{'s' if len(urgent) > 1 else ''} expiring within 60 days — "
                f"{alert_text}. Exit penalty exposure: {penalty_exposure}."
            )

    if validated.get("value-bridge-calculator"):
        b = validated["value-bridge-calculator"]
        bands = b.get("confidence_bands", {})
        vb_line = format_value_bridge_line(validated)
        if vb_line:
            parts.append(vb_line)
        if ctx:
            focused = build_focus_category_section(ctx, validated)
            if focused:
                parts.append(focused)

        recs = recommendation_rows(validated)
        if recs:
            rec_lines = build_data_backed_recommendation_lines(
                recs,
                validated,
                ctx,
                category_focused=category_focused,
                bands=bands,
            )
            parts.append("\n".join(rec_lines))

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
            parts.append(format_business_case_for_chat(bc))
        else:
            parts.append("Business case prepared.")
    if failed:
        parts.append(f"Errors: {', '.join(f'{k}: {v}' for k, v in failed.items())}.")
    sme_block = build_sme_critique_section(validated, get_reflect_currency())
    if sme_block:
        parts.append(sme_block)
    if parts:
        return "\n\n".join(parts)
    if ctx and is_interactive_savings_query(ctx.user_message, getattr(ctx, "query_capabilities", None)):
        savings_fallback = answer_general_qa(ctx.user_message, validated, currency=get_reflect_currency())
        if savings_fallback:
            return savings_fallback
    return plan.user_summary
