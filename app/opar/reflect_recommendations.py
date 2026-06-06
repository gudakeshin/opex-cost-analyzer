"""Recommendation section formatters for reflect response composition."""
from __future__ import annotations

from typing import Any, Dict, List, Literal

from app.opar.models import ObserveContext
from app.opar.reflect_currency import format_currency
from app.opar.reflect_focus import business_lever_label, executive_callouts, match_focus_category

RecommendationSource = Literal["llm", "data"]


def recommendations_section_title(category_focused: bool, source: RecommendationSource) -> str:
    if source == "llm":
        return (
            "**Focused category actions (LLM-Synthesized, Skill-Grounded)**"
            if category_focused
            else "**Top Recommendations (LLM-Synthesized, Skill-Grounded)**"
        )
    return (
        "**Focused category actions (Data-Backed)**"
        if category_focused
        else "**Top Recommendations (Data-Backed)**"
    )


def format_synthesizer_impact(
    fin: Dict[str, Any],
    *,
    business_case: bool,
) -> str:
    if business_case:
        return (
            f"mid-case {format_currency(fin.get('mid_case_savings', 0))}, "
            f"NPV {format_currency(fin.get('net_npv', 0))}, "
            f"payback {int(fin.get('payback_months', 0) or 0)} months"
        )
    return (
        f"modeled value release {format_currency(fin.get('mid_case_savings', 0))} "
        "(request business case for NPV/payback)"
    )


def format_data_backed_impact(
    rec: Dict[str, Any],
    *,
    business_case: bool,
) -> str:
    payback_text = (
        f"{rec['payback_months']} months"
        if rec.get("payback_months", 0) > 0
        else "not yet established"
    )
    if business_case:
        return (
            f"mid-case {format_currency(rec['dedup_mid'])}, NPV {format_currency(rec['npv'])}, "
            f"payback {payback_text}, confidence {rec['confidence']}."
        )
    return (
        f"modeled value release {format_currency(rec['dedup_mid'])}, confidence {rec['confidence']}. "
        "Ask for a business case to see NPV/payback economics."
    )


def build_synthesizer_recommendation_lines(
    recs: List[Dict[str, Any]],
    ctx: ObserveContext | None,
    *,
    category_focused: bool,
    max_items: int = 4,
) -> List[str]:
    if not recs:
        return []
    business_case = bool(ctx and ctx.intent_class == "business_case")
    lines = [recommendations_section_title(category_focused, "llm")]
    for rec in recs[:max_items]:
        fin = rec.get("financials", {})
        conf = rec.get("confidence", {})
        lever_label = business_lever_label(str(rec.get("lever", "optimization")))
        impact_text = format_synthesizer_impact(fin, business_case=business_case)
        lines.append(
            f"- **{rec.get('category_name', rec.get('category_id', 'Unknown'))}** via **{lever_label}**: "
            f"{impact_text}, confidence {conf.get('level', 'mid')}."
        )
        for ev in rec.get("evidence", [])[:3]:
            lines.append(f"  - [{ev.get('source', 'source')}] {ev.get('detail', '')}")
        for ex in rec.get("examples", [])[:2]:
            supplier = ex.get("supplier", "Unknown supplier")
            description = ex.get("description", "N/A")
            amount = format_currency(ex.get("amount", 0))
            why = ex.get("why_relevant", "Supports this recommendation")
            lines.append(f"  - Example: {supplier} | {description} | {amount} ({why})")
        decisions = rec.get("decisions_required", [])
        if decisions:
            lines.append(f"  - Decision required: {decisions[0]}")
    lines.append("")
    return lines


def build_data_backed_executive_takeaway(
    recs: List[Dict[str, Any]],
    ctx: ObserveContext | None,
    validated: Dict[str, Dict[str, Any]],
    bands: Dict[str, Any],
) -> str:
    total_mid = float(bands.get("mid", 0.0))
    top_mid = sum(r["dedup_mid"] for r in recs)
    concentration = (top_mid / total_mid * 100) if total_mid > 0 else 0.0
    focus_row = match_focus_category(ctx, validated) if ctx else None
    if focus_row:
        focus_name = focus_row.get("category_name") or focus_row.get("category_id") or "the selected category"
        focus_mid = float(focus_row.get("deduped_mid_savings", 0.0) or 0.0)
        return (
            f"{focus_name} is the primary focus for this request, with modeled mid-case impact "
            f"of {format_currency(focus_mid)} and clear lever-driven actions to execute."
        )
    return (
        f"The top {len(recs)} initiatives represent {format_currency(top_mid)} of modeled impact "
        f"({concentration:.1f}% of mid-case opportunity)."
    )


def build_data_backed_recommendation_lines(
    recs: List[Dict[str, Any]],
    validated: Dict[str, Dict[str, Any]],
    ctx: ObserveContext | None,
    *,
    category_focused: bool,
    bands: Dict[str, Any],
    max_items: int = 3,
) -> List[str]:
    if not recs:
        return []
    business_case = bool(ctx and ctx.intent_class == "business_case")
    lines: List[str] = []
    if ctx and ctx.wants_executive_narrative:
        lines.extend(
            [
                "**Executive Takeaway**",
                build_data_backed_executive_takeaway(recs, ctx, validated, bands),
                "",
            ]
        )
    lines.append(recommendations_section_title(category_focused, "data"))
    callouts = executive_callouts(validated)
    if callouts and ctx and ctx.wants_executive_narrative:
        lines.insert(3, "")
        lines.insert(
            3,
            callouts[0] if len(callouts) == 1 else f"CFO call-outs: {callouts[0]} {callouts[1]}",
        )
    for i, rec in enumerate(recs[:max_items], 1):
        impact_line = format_data_backed_impact(rec, business_case=business_case)
        lines.append(
            f"{i}. **{rec['category']}** via **{rec.get('lever_label', rec['lever'])}** — "
            f"{impact_line}"
        )
        evidence_preview = (
            rec["evidence"][0]
            if rec.get("evidence")
            else "Measured gap identified in benchmark and diagnostic signals."
        )
        lines.append(
            "   - Value-release logic: close the measured gap referenced below, codify the change in policy/commercial terms "
            f"for this category, and convert recurring leakage into realized run-rate savings. ({evidence_preview})"
        )
        for ev in rec.get("evidence", []):
            lines.append(f"   - {ev}")
    return lines


def append_validation_errors(lines: List[str], failed: Dict[str, str]) -> None:
    if failed:
        lines.append("")
        lines.append(f"Validation/errors: {', '.join(f'{k}: {v}' for k, v in failed.items())}.")
