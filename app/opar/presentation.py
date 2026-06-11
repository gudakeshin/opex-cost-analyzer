"""Hybrid presentation layer — structured fact blocks + markdown narrative for chat responses."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Tuple

from pydantic import BaseModel, Field

from app.opar.category_resolver import match_category_from_query
from app.opar.models import AdvisorySections, ObserveContext
from app.opar.reflect_currency import format_currency
from app.opar.reflect_focus import is_category_focused_request, match_focus_category

BlockKind = Literal[
    "metric_strip",
    "category_insight",
    "lever_list",
    "action_timeline",
    "markdown_narrative",
    "callout_list",
    "quick_wins",
]

_MAX_CATEGORY_INSIGHTS = 5
_MAX_SUPPLIERS = 4


class SupplierRow(BaseModel):
    supplier: str
    spend: float | None = None
    share_of_category: float | None = None
    note: str | None = None


class CategoryInsightData(BaseModel):
    category_id: str
    category_name: str
    spend: float | None = None
    spend_pct_revenue: float | None = None
    benchmark_gap: str | None = None
    addressable_gap: float | None = None
    top_suppliers: List[SupplierRow] = Field(default_factory=list)
    concentration_hhi: float | None = None
    suggested_actions: List[str] = Field(default_factory=list)


class PresentationBlock(BaseModel):
    kind: BlockKind
    title: str = ""
    data: Dict[str, Any] = Field(default_factory=dict)


class AssistantPayload(BaseModel):
    blocks: List[PresentationBlock] = Field(default_factory=list)
    narrative_markdown: str = ""


def _peer_gap_label(peer_row: Dict[str, Any]) -> str | None:
    if not peer_row:
        return None
    actual = peer_row.get("actual_pct_of_revenue")
    p50 = peer_row.get("benchmark_p50_pct")
    if actual is None or p50 is None:
        gap_pct = peer_row.get("benchmark_gap_pct")
        if gap_pct is not None:
            return f"{float(gap_pct):.1f} pts above peer median"
        return None
    gap = float(actual) - float(p50)
    if gap <= 0:
        return f"{abs(gap):.1f} pts below peer median"
    return f"{gap:.1f} pts above peer median (actual {float(actual):.2f}% vs P50 {float(p50):.2f}%)"


def _suggested_actions_for_category(
    cid: str, validated: Dict[str, Dict[str, Any]], max_items: int = 3
) -> List[str]:
    actions: List[str] = []
    for init in validated.get("savings-modeler", {}).get("initiatives", []) or []:
        if not isinstance(init, dict):
            continue
        if str(init.get("category_id") or "") != cid:
            continue
        lever = init.get("lever_name") or init.get("lever") or "optimization"
        mid = (init.get("net_savings") or {}).get("mid") if isinstance(init.get("net_savings"), dict) else None
        if mid is not None:
            actions.append(f"{lever}: {format_currency(float(mid))} modeled mid-case")
        else:
            actions.append(str(lever))
        if len(actions) >= max_items:
            break
    for finding in validated.get("root-cause-analyzer", {}).get("root_cause_findings", []) or []:
        if not isinstance(finding, dict) or str(finding.get("category_id") or "") != cid:
            continue
        text = str(finding.get("finding") or finding.get("root_cause") or "").strip()
        if text:
            actions.append(text[:200])
        if len(actions) >= max_items:
            break
    return actions[:max_items]


def _category_insight_from_row(
    row: Dict[str, Any],
    validated: Dict[str, Dict[str, Any]],
    peer_by_id: Dict[str, Dict[str, Any]],
) -> CategoryInsightData:
    cid = str(row.get("category_id") or "")
    suppliers: List[SupplierRow] = []
    for sup in (row.get("top_suppliers") or [])[:_MAX_SUPPLIERS]:
        if not isinstance(sup, dict):
            continue
        suppliers.append(SupplierRow(
            supplier=str(sup.get("supplier") or "Unknown"),
            spend=float(sup["spend"]) if sup.get("spend") is not None else None,
            share_of_category=float(sup["share_of_category"]) if sup.get("share_of_category") is not None else None,
            note=str(sup.get("note") or "")[:120] or None,
        ))
    peer = peer_by_id.get(cid, {})
    spend = float(row.get("spend", 0) or 0)
    addressable = row.get("addressable_spend")
    return CategoryInsightData(
        category_id=cid,
        category_name=str(row.get("category_name") or cid),
        spend=spend if spend else None,
        spend_pct_revenue=float(row["spend_pct"]) if row.get("spend_pct") is not None else None,
        benchmark_gap=_peer_gap_label(peer),
        addressable_gap=float(addressable) if addressable is not None else None,
        top_suppliers=suppliers,
        concentration_hhi=float(row["hhi"]) if row.get("hhi") is not None else None,
        suggested_actions=_suggested_actions_for_category(cid, validated),
    )


def _rank_categories_for_insights(
    categories: List[Dict[str, Any]],
    peer_by_id: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    def sort_key(row: Dict[str, Any]) -> float:
        cid = str(row.get("category_id") or "")
        peer = peer_by_id.get(cid, {})
        actual = float(peer.get("actual_pct_of_revenue", 0) or 0)
        p50 = float(peer.get("benchmark_p50_pct", 0) or 0)
        gap = max(actual - p50, 0.0)
        if gap > 0:
            return gap * 1_000_000 + float(row.get("spend", 0) or 0)
        return float(row.get("addressable_spend", 0) or row.get("spend", 0) or 0)

    return sorted(categories, key=sort_key, reverse=True)


def build_insight_blocks(
    ctx: ObserveContext,
    validated: Dict[str, Dict[str, Any]],
    *,
    max_categories: int = _MAX_CATEGORY_INSIGHTS,
) -> List[PresentationBlock]:
    """Deterministic category insight cards from skill outputs."""
    profile = validated.get("spend-profiler", {})
    if not isinstance(profile, dict):
        return []
    categories = profile.get("category_profile") or []
    if not isinstance(categories, list) or not categories:
        return []

    peer_by_id = {
        str(r.get("category_id")): r
        for r in validated.get("peer-benchmarker", {}).get("comparisons", []) or []
        if isinstance(r, dict) and r.get("category_id")
    }

    selected: List[Dict[str, Any]] = []
    if is_category_focused_request(ctx, validated):
        focus = match_focus_category(ctx, validated)
        if focus:
            cid = str(focus.get("category_id") or "")
            selected = [c for c in categories if isinstance(c, dict) and str(c.get("category_id")) == cid]
        if not selected:
            matched = match_category_from_query(ctx.user_message, categories)
            if matched:
                selected = [matched]
    if not selected:
        selected = _rank_categories_for_insights(
            [c for c in categories if isinstance(c, dict)],
            peer_by_id,
        )[:max_categories]

    blocks: List[PresentationBlock] = []
    total_spend = float(profile.get("total_spend", 0) or 0)
    if total_spend > 0:
        blocks.append(PresentationBlock(
            kind="metric_strip",
            title="Portfolio snapshot",
            data={
                "total_spend": total_spend,
                "category_count": len(categories),
                "currency_note": "amounts in session reporting currency",
            },
        ))

    for row in selected[:max_categories]:
        insight = _category_insight_from_row(row, validated, peer_by_id)
        blocks.append(PresentationBlock(
            kind="category_insight",
            title=insight.category_name,
            data=insight.model_dump(),
        ))
    return blocks


def _narrative_from_advisory(advisory: AdvisorySections) -> str:
    """Top-of-message brief — causal depth lives in a dedicated block after fact cards."""
    return (advisory.executive_takeaway or "").strip()


def _causal_narrative_block(advisory: AdvisorySections) -> PresentationBlock | None:
    focus = (advisory.category_focus_section or "").strip()
    if not focus:
        return None
    return PresentationBlock(
        kind="markdown_narrative",
        title="Why it matters — causal analysis",
        data={"markdown": focus, "variant": "causal_prose"},
    )


def _blocks_from_advisory(advisory: AdvisorySections) -> List[PresentationBlock]:
    blocks: List[PresentationBlock] = []
    if advisory.quick_wins_from_data:
        blocks.append(PresentationBlock(
            kind="quick_wins",
            title="Quick wins from data",
            data={"items": advisory.quick_wins_from_data[:5]},
        ))
    if advisory.executive_callouts:
        blocks.append(PresentationBlock(
            kind="callout_list",
            title="Executive call-outs",
            data={"items": advisory.executive_callouts[:3]},
        ))
    if advisory.business_levers:
        blocks.append(PresentationBlock(
            kind="lever_list",
            title="Business levers",
            data={"levers": [lv.model_dump() for lv in advisory.business_levers[:4]]},
        ))
    if advisory.priority_actions_30_60_90:
        blocks.append(PresentationBlock(
            kind="action_timeline",
            title="30 / 60 / 90 day actions",
            data={"actions": [a.model_dump() for a in advisory.priority_actions_30_60_90[:5]]},
        ))
    if advisory.recommendations:
        rec_summaries = []
        for rec in advisory.recommendations[:4]:
            fin = rec.financials or {}
            mid = fin.get("mid_case_savings")
            line = f"**{rec.category_name or rec.category_id}** — {rec.lever}"
            if mid is not None:
                line += f" ({format_currency(float(mid))} mid-case)"
            rec_summaries.append(line)
        if rec_summaries:
            blocks.append(PresentationBlock(
                kind="markdown_narrative",
                title="Recommendations",
                data={"markdown": "\n".join(f"- {s}" for s in rec_summaries)},
            ))
    sme = (advisory.sme_qualification_narrative or "").strip()
    if sme:
        blocks.append(PresentationBlock(
            kind="markdown_narrative",
            title="SME qualification",
            data={"markdown": sme},
        ))
    return blocks


def assemble_assistant_payload(
    advisory: AdvisorySections | None,
    validated: Dict[str, Dict[str, Any]],
    ctx: ObserveContext,
) -> AssistantPayload:
    """Merge deterministic insight blocks with advisory narrative and structured sections."""
    blocks = build_insight_blocks(ctx, validated)
    if advisory:
        causal = _causal_narrative_block(advisory)
        if causal:
            blocks.append(causal)
        blocks.extend(_blocks_from_advisory(advisory))
        narrative = _narrative_from_advisory(advisory)
    else:
        narrative = ""
    return AssistantPayload(blocks=blocks, narrative_markdown=narrative)


def presentation_structure_score(payload: AssistantPayload) -> Tuple[float, Dict[str, Any]]:
    """Structural readability checks for eval harnesses (0–10)."""
    score = 10.0
    evidence: Dict[str, Any] = {}
    category_blocks = [b for b in payload.blocks if b.kind == "category_insight"]
    evidence["category_insight_count"] = len(category_blocks)
    if not category_blocks:
        score -= 3.0
        evidence["missing_category_blocks"] = True

    causal_blocks = [
        b for b in payload.blocks
        if b.kind == "markdown_narrative" and b.data.get("variant") == "causal_prose"
    ]
    evidence["causal_narrative_count"] = len(causal_blocks)
    if category_blocks and not causal_blocks:
        score -= 2.0
        evidence["missing_causal_narrative"] = True
    elif causal_blocks:
        md = str(causal_blocks[0].data.get("markdown") or "")
        if md and "##" not in md:
            score -= 1.5
            evidence["causal_missing_headings"] = True

    focus = payload.narrative_markdown
    if focus and len(focus) > 600 and "\n\n" not in focus:
        score -= 2.0
        evidence["narrative_wall_of_text"] = True
    if focus and len(focus) > 1200:
        score -= 1.0
        evidence["narrative_long"] = len(focus)

    return max(0.0, min(10.0, score)), evidence
