"""Gemini-primary conversational QA composer for general_qa chat turns."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal

from app.opar.category_resolver import match_category_from_query
from app.opar.gemini_client import synthesize_chat_response_gemini
from app.opar.models import ObserveContext
from app.opar.qa_lookup import aggregate_portfolio_suppliers, answer_general_qa, _parse_top_limit

BreakdownDimension = Literal["supplier", "geo", "category", "payment_terms", "none"]


@dataclass
class QueryDimensions:
    focus_category: str | None = None
    focus_category_id: str | None = None
    breakdown_dimension: BreakdownDimension = "none"


@dataclass
class ChatSynthesisResult:
    response_text: str
    response_metadata: Dict[str, Any] = field(default_factory=dict)
    thinking_text: str | None = None
    used_llm: bool = False


def extract_query_dimensions(msg: str, categories: List[Dict[str, Any]]) -> QueryDimensions:
    """Rule-based detection of category focus and breakdown dimension."""
    lowered = (msg or "").lower()
    matched = match_category_from_query(msg, categories) if categories else None
    focus_name = None
    focus_id = None
    if matched:
        focus_name = str(matched.get("category_name") or matched.get("category_id") or "")
        focus_id = str(matched.get("category_id") or "")

    dimension: BreakdownDimension = "none"
    if any(t in lowered for t in ("supplier", "vendor", "by supplier", "by vendor", "payee")):
        dimension = "supplier"
    elif any(t in lowered for t in ("geo", "geograph", "region", "country", "by country", "by region")):
        dimension = "geo"
    elif any(t in lowered for t in ("payment term", "dpo", "days payable", "net 30", "net 45")):
        dimension = "payment_terms"
    elif any(
        t in lowered
        for t in ("break down", "breakdown", "split by", "drill", "by category", "categor")
    ):
        dimension = "category"

    return QueryDimensions(
        focus_category=focus_name or None,
        focus_category_id=focus_id or None,
        breakdown_dimension=dimension,
    )


def _slim_category_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "category_id": row.get("category_id"),
        "category_name": row.get("category_name"),
        "spend": row.get("spend"),
        "line_count": row.get("line_count"),
        "share_of_total": row.get("share_of_total"),
        "addressable_spend": row.get("addressable_spend"),
        "supplier_count": row.get("supplier_count"),
        "top_suppliers": row.get("top_suppliers", [])[:10],
        "top_geos": row.get("top_geos", [])[:8],
        "hhi": row.get("hhi"),
        "concentration_flag": row.get("concentration_flag"),
    }


def _portfolio_summary(profile: Dict[str, Any]) -> Dict[str, Any]:
    categories = profile.get("category_profile", []) or []
    top = sorted(categories, key=lambda c: float(c.get("spend", 0) or 0), reverse=True)[:5]
    return {
        "total_spend": profile.get("total_spend", 0.0),
        "category_count": len(categories),
        "top_categories": [
            {
                "category_name": c.get("category_name"),
                "spend": c.get("spend"),
                "share_of_total": (
                    float(c.get("spend", 0) or 0) / float(profile.get("total_spend", 1) or 1) * 100
                    if profile.get("total_spend")
                    else 0
                ),
            }
            for c in top
        ],
    }


def _fetch_document_excerpts(engagement_id: str, query: str, limit: int = 2) -> List[str]:
    if not engagement_id:
        return []
    try:
        from app.services.document_index import retrieve_context

        blocks = retrieve_context(engagement_id, query)
        return blocks[:limit] if blocks else []
    except Exception:
        return []


def build_chat_context(
    ctx: ObserveContext,
    manifest: Dict[str, Any],
    skill_outputs: Dict[str, Any],
    *,
    chat_history: List[Dict[str, str]] | None = None,
    currency: str = "INR",
) -> Dict[str, Any]:
    """Assemble structured context for Gemini chat synthesis."""
    profile = skill_outputs.get("spend-profiler", {})
    categories = profile.get("category_profile", []) if isinstance(profile, dict) else []
    dims = extract_query_dimensions(ctx.user_message, categories)

    matched_row: Dict[str, Any] | None = None
    if dims.focus_category_id:
        matched_row = next(
            (c for c in categories if str(c.get("category_id")) == dims.focus_category_id),
            None,
        )
    if not matched_row and dims.focus_category:
        matched_row = match_category_from_query(ctx.user_message, categories)

    relevant_data: Dict[str, Any] = {}
    if matched_row:
        relevant_data = _slim_category_row(matched_row)
    elif dims.breakdown_dimension == "supplier" and categories:
        total_spend = float(profile.get("total_spend", 0) or 0) if isinstance(profile, dict) else 0.0
        limit = _parse_top_limit(ctx.user_message)
        relevant_data = {
            "top_suppliers_portfolio": aggregate_portfolio_suppliers(
                categories,
                limit=limit,
                total_spend=total_spend,
            )
        }
    elif dims.breakdown_dimension == "category" and categories:
        relevant_data = {"all_categories": [_slim_category_row(c) for c in categories[:12]]}

    recent_turns = []
    if chat_history:
        for turn in chat_history[-6:]:
            role = str(turn.get("role") or "")
            content = str(turn.get("content") or "")[:800]
            if role and content:
                recent_turns.append({"role": role, "content": content})

    engagement_id = ctx.engagement_id or str(manifest.get("engagement_id") or "")
    doc_excerpts = _fetch_document_excerpts(engagement_id, ctx.user_message)

    sme = skill_outputs.get("sme-critique", {}) if isinstance(skill_outputs, dict) else {}
    portfolio_probes: List[Dict[str, Any]] = []
    if isinstance(sme, dict):
        raw_probes = sme.get("portfolio_probes") or sme.get("top_probes") or []
        if isinstance(raw_probes, list):
            portfolio_probes = [p for p in raw_probes if isinstance(p, dict)][:5]
    probe_answers = manifest.get("probe_answers") if isinstance(manifest.get("probe_answers"), list) else []
    if not probe_answers and getattr(ctx, "probe_answers", None):
        probe_answers = ctx.probe_answers

    return {
        "user_message": ctx.user_message,
        "session_context": {
            "company_name": manifest.get("company_name"),
            "industry": manifest.get("industry"),
            "annual_revenue": manifest.get("annual_revenue"),
            "currency": currency or manifest.get("currency") or "INR",
            "audience": manifest.get("audience") or "cfo",
            "engagement_week": ctx.engagement_week,
            "decision_gate": ctx.decision_gate,
        },
        "data_readiness": {
            "has_tabular_spend": ctx.has_tabular_spend,
            "spend_profile_ready": ctx.spend_profile_ready,
            "data_quality_score": ctx.data_quality_score,
            "file_count": len(manifest.get("files", []) or []),
        },
        "query_analysis": {
            "focus_category": dims.focus_category,
            "focus_category_id": dims.focus_category_id,
            "breakdown_dimension": dims.breakdown_dimension,
            "intent_class": ctx.intent_class,
        },
        "relevant_data": relevant_data,
        "portfolio_summary": _portfolio_summary(profile) if isinstance(profile, dict) else {},
        "deep_research_summary": manifest.get("deep_research_summary"),
        "business_override_note": manifest.get("business_override_note") or ctx.business_override_note,
        "probe_context": {
            "portfolio_probes": portfolio_probes,
            "probe_answers": probe_answers[:10] if isinstance(probe_answers, list) else [],
        },
        "recent_turns": recent_turns,
        "document_excerpts": doc_excerpts,
    }


def _response_metadata_from_context(context: Dict[str, Any]) -> Dict[str, Any]:
    qa = context.get("query_analysis") or {}
    dim = qa.get("breakdown_dimension") or "none"
    meta: Dict[str, Any] = {"insight_dimension": dim}
    if qa.get("focus_category"):
        meta["focus_category"] = qa["focus_category"]
    return meta


def synthesize_chat_response(
    ctx: ObserveContext,
    manifest: Dict[str, Any],
    skill_outputs: Dict[str, Any],
    *,
    chat_history: List[Dict[str, str]] | None = None,
    currency: str = "INR",
    thinking_enabled: bool = False,
) -> ChatSynthesisResult:
    """Build context, call Gemini, fall back to deterministic QA on failure."""
    context = build_chat_context(
        ctx, manifest, skill_outputs, chat_history=chat_history, currency=currency
    )
    metadata = _response_metadata_from_context(context)

    text, thinking = synthesize_chat_response_gemini(context, thinking_enabled=thinking_enabled)
    if text:
        return ChatSynthesisResult(
            response_text=text,
            response_metadata=metadata,
            thinking_text=thinking,
            used_llm=True,
        )

    fallback = answer_general_qa(ctx.user_message, skill_outputs, currency=currency)
    return ChatSynthesisResult(
        response_text=fallback,
        response_metadata=metadata,
        used_llm=False,
    )
