"""Provider-agnostic conversational QA composer for general_qa chat turns.

The LLM reads the question against the *full* spend context and writes the answer
(Claude default, Gemini fallback, routed by ``LLM_PROVIDER`` — mirrors
``reflect_advisory.resolve_analysis_synthesizer``). The deterministic keyword
composer (``qa_lookup.answer_general_qa``) is the offline / timeout / pytest fallback.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Literal, Optional, Tuple

from app.config import (
    ANTHROPIC_ENABLED,
    GEMINI_ENABLED,
    LLM_CHAT_SYNTHESIS_ENABLED,
)
from app.services.llm_selection import get_resolved_llm_provider
from app.opar.category_resolver import match_category_from_query
from app.opar.gemini_client import synthesize_chat_response_gemini
from app.opar.models import ObserveContext
from app.opar.qa_lookup import aggregate_portfolio_suppliers, answer_general_qa, _parse_top_limit

BreakdownDimension = Literal["supplier", "geo", "category", "payment_terms", "none"]

# A chat synthesizer takes the structured context dict and returns (text, thinking).
ChatSynthesizer = Callable[..., Tuple[Optional[str], Optional[str]]]


def resolve_chat_synthesizer() -> ChatSynthesizer | None:
    """Pick the chat QA synthesizer from ``LLM_PROVIDER`` with cross-provider fallback.

    Mirrors :func:`app.opar.reflect_advisory.resolve_analysis_synthesizer`: Gemini only
    when it is the preferred provider, otherwise Claude (the default), falling across to
    whichever provider is configured. Returns ``None`` when no provider is available.
    """
    prefer_gemini = get_resolved_llm_provider() == "gemini"
    if prefer_gemini and GEMINI_ENABLED:
        return synthesize_chat_response_gemini
    if ANTHROPIC_ENABLED:
        from app.opar.claude_client import synthesize_chat_response_claude

        return synthesize_chat_response_claude
    if GEMINI_ENABLED:
        return synthesize_chat_response_gemini
    return None


def _iter_chat_synthesizers() -> list[ChatSynthesizer]:
    """Ordered chat synthesizers: preferred provider first, then cross-provider fallback."""
    from app.opar.claude_client import synthesize_chat_response_claude
    from app.opar.gemini_client import is_gemini_quota_exhausted

    prefer_gemini = get_resolved_llm_provider() == "gemini"
    gemini_available = GEMINI_ENABLED and not is_gemini_quota_exhausted()
    ordered: list[ChatSynthesizer] = []
    if prefer_gemini:
        if gemini_available:
            ordered.append(synthesize_chat_response_gemini)
        if ANTHROPIC_ENABLED:
            ordered.append(synthesize_chat_response_claude)
    else:
        if ANTHROPIC_ENABLED:
            ordered.append(synthesize_chat_response_claude)
        if gemini_available:
            ordered.append(synthesize_chat_response_gemini)
    return ordered


def _synthesize_via_llm(
    context: Dict[str, Any],
    *,
    thinking_enabled: bool = False,
    thinking_callback: Callable[[str], None] | None = None,
) -> Tuple[str | None, str | None]:
    """Run chat synthesis across providers; ``(None, None)`` when all miss."""
    if not LLM_CHAT_SYNTHESIS_ENABLED:
        return None, None
    for synth in _iter_chat_synthesizers():
        try:
            text, thinking = synth(context, thinking_enabled=thinking_enabled)
            if thinking and thinking_callback:
                thinking_callback(thinking)
            if text:
                return text, thinking
        except Exception:
            continue
    return None, None


def synthesize_reference_answer(
    user_message: str,
    reference: Dict[str, Any],
    *,
    session_context: Dict[str, Any] | None = None,
) -> str | None:
    """LLM answer for turns with no spend profile (onboarding, capabilities, schema).

    ``reference`` is factual material (capability overview, file-format guide, schema
    summary) the model rephrases into a tailored reply. Returns ``None`` when no
    provider is available / offline / pytest, so the caller uses its canned fallback.
    """
    context = {
        "user_message": user_message,
        "session_context": session_context or {},
        "reference": reference,
    }
    text, _ = _synthesize_via_llm(context)
    return text


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


def _slim_initiative_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "category_id": row.get("category_id"),
        "category_name": row.get("category_name"),
        "lever": row.get("lever"),
        "lever_name": row.get("lever_name"),
        "confidence": row.get("confidence"),
        "annualized_run_rate_savings": row.get("annualized_run_rate_savings"),
        "net_savings": row.get("net_savings"),
        "horizon": row.get("horizon"),
        "execution_probability": row.get("execution_probability"),
    }


def _slim_value_matrix_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "category_id": row.get("category_id"),
        "category_name": row.get("category_name"),
        "lever": row.get("lever"),
        "deduped_mid_savings": row.get("deduped_mid_savings"),
        "net_npv": row.get("net_npv"),
        "payback_months": row.get("payback_months"),
        "confidence": row.get("confidence"),
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
    """Assemble structured context for chat synthesis.

    Gives the model the *full* (slimmed) spend picture — every category with its
    suppliers/geos, the portfolio-wide supplier ranking, and payment-terms
    opportunities — rather than a single keyword-selected slice. The model reads
    the question and picks the relevant dimension itself; ``query_analysis`` is a
    non-binding hint, not a gate on what data is visible. (Pre-filtering by
    keyword was the main cause of "answer doesn't match the question".)
    """
    profile = skill_outputs.get("spend-profiler", {})
    categories = profile.get("category_profile", []) if isinstance(profile, dict) else []
    dims = extract_query_dimensions(ctx.user_message, categories)
    total_spend = float(profile.get("total_spend", 0) or 0) if isinstance(profile, dict) else 0.0

    matched_row: Dict[str, Any] | None = None
    if dims.focus_category_id:
        matched_row = next(
            (c for c in categories if str(c.get("category_id")) == dims.focus_category_id),
            None,
        )
    if not matched_row and dims.focus_category:
        matched_row = match_category_from_query(ctx.user_message, categories)

    # Full context — not a single pre-selected slice.
    all_categories = [_slim_category_row(c) for c in categories[:12]]
    portfolio_top_suppliers = (
        aggregate_portfolio_suppliers(
            categories,
            limit=_parse_top_limit(ctx.user_message),
            total_spend=total_spend,
        )
        if categories
        else []
    )
    focus_category_detail = _slim_category_row(matched_row) if matched_row else {}
    pt_skill = skill_outputs.get("payment-terms-optimizer", {}) if isinstance(skill_outputs, dict) else {}
    payment_terms_opportunities = (
        pt_skill.get("opportunities", [])[:5] if isinstance(pt_skill, dict) else []
    )

    recent_turns = []
    if chat_history:
        for turn in chat_history[-6:]:
            role = str(turn.get("role") or "")
            content = str(turn.get("content") or "")[:800]
            if role and content:
                recent_turns.append({"role": role, "content": content})

    engagement_id = ctx.engagement_id or str(manifest.get("engagement_id") or "")
    doc_limit = 4 if "contract" in (ctx.user_message or "").lower() else 2
    doc_excerpts = _fetch_document_excerpts(engagement_id, ctx.user_message, limit=doc_limit)

    savings_model = skill_outputs.get("savings-modeler", {}) if isinstance(skill_outputs, dict) else {}
    initiatives = (
        savings_model.get("initiatives", [])[:12]
        if isinstance(savings_model, dict) and isinstance(savings_model.get("initiatives"), list)
        else []
    )
    value_bridge = skill_outputs.get("value-bridge-calculator", {}) if isinstance(skill_outputs, dict) else {}
    value_matrix = (
        value_bridge.get("value_matrix", [])[:12]
        if isinstance(value_bridge, dict) and isinstance(value_bridge.get("value_matrix"), list)
        else []
    )
    confidence_bands = (
        value_bridge.get("confidence_bands", {})
        if isinstance(value_bridge, dict) and isinstance(value_bridge.get("confidence_bands"), dict)
        else {}
    )
    root_cause = skill_outputs.get("root-cause-analyzer", {}) if isinstance(skill_outputs, dict) else {}
    root_findings = (
        root_cause.get("root_cause_findings", [])[:8]
        if isinstance(root_cause, dict) and isinstance(root_cause.get("root_cause_findings"), list)
        else []
    )
    doc_ctx_skill = skill_outputs.get("document-contextualizer", {}) if isinstance(skill_outputs, dict) else {}
    document_context = {}
    if isinstance(doc_ctx_skill, dict):
        document_context = {
            "context_summary": str(doc_ctx_skill.get("context_summary") or "")[:1200],
            "constraints": (doc_ctx_skill.get("constraints") or [])[:8]
            if isinstance(doc_ctx_skill.get("constraints"), list)
            else [],
        }
    contract_skill = skill_outputs.get("contract-lifecycle-manager", {}) if isinstance(skill_outputs, dict) else {}
    contract_renewals = (
        contract_skill.get("renewal_alerts", [])[:8]
        if isinstance(contract_skill, dict) and isinstance(contract_skill.get("renewal_alerts"), list)
        else []
    )

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
            "note": "Hint only — answer the dimension the user actually asked for; all data below is available.",
        },
        "spend_data": {
            "total_spend": total_spend,
            "category_count": len(categories),
            "categories": all_categories,
            "portfolio_top_suppliers": portfolio_top_suppliers,
            "focus_category_detail": focus_category_detail,
            "payment_terms_opportunities": payment_terms_opportunities,
        },
        "portfolio_summary": _portfolio_summary(profile) if isinstance(profile, dict) else {},
        "deep_research_summary": manifest.get("deep_research_summary"),
        "business_override_note": manifest.get("business_override_note") or ctx.business_override_note,
        "probe_context": {
            "portfolio_probes": portfolio_probes,
            "probe_answers": probe_answers[:10] if isinstance(probe_answers, list) else [],
        },
        "recent_turns": recent_turns,
        "document_excerpts": doc_excerpts,
        "document_context": document_context,
        "modeled_initiatives": [_slim_initiative_row(i) for i in initiatives if isinstance(i, dict)],
        "value_matrix_rows": [_slim_value_matrix_row(r) for r in value_matrix if isinstance(r, dict)],
        "confidence_bands": confidence_bands,
        "root_cause_findings": root_findings,
        "contract_renewals": contract_renewals,
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
    thinking_callback: Callable[[str], None] | None = None,
) -> ChatSynthesisResult:
    """Build context, run the resolved LLM, fall back to deterministic QA on failure."""
    context = build_chat_context(
        ctx, manifest, skill_outputs, chat_history=chat_history, currency=currency
    )
    metadata = _response_metadata_from_context(context)

    text, thinking = _synthesize_via_llm(
        context,
        thinking_enabled=thinking_enabled,
        thinking_callback=thinking_callback,
    )
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
