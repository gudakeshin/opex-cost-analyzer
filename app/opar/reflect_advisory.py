"""Reflect LLM advisory — lazy Claude/Gemini synthesis for value-bridge responses."""
from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Tuple

from app.config import ANTHROPIC_ENABLED, GEMINI_ENABLED, LLM_PROVIDER, logger
from app.opar.models import AdvisorySections, ObserveContext

_LLM_TOKEN_LIMIT = 80_000
_CHARS_PER_TOKEN = 4

# The concrete synthesizers (claude/gemini) accept several optional keyword
# arguments (strict_mode, thinking_enabled, transaction_examples, …) on top of
# the positional payload. Use an open (...) parameter list so callers may pass
# them without fighting the alias; the return shape is what we rely on.
AnalysisSynthesizer = Callable[
    ...,
    Tuple[Dict[str, Any] | None, str | None],
]


def needs_llm_advisory(
    ctx: ObserveContext,
    validated: Dict[str, Dict[str, Any]],
    *,
    category_focused: bool = False,
) -> bool:
    """True when Claude/Gemini advisory synthesis should run (not QA lookup)."""
    if not GEMINI_ENABLED and not ANTHROPIC_ENABLED:
        return False
    if "value-bridge-calculator" not in validated and "savings-modeler" not in validated:
        return False
    if ctx.wants_executive_narrative:
        return True
    if category_focused:
        return True
    if ctx.intent_class in {
        "benchmark", "value_bridge", "business_case", "savings_plan",
        "drill_down", "sensitivity",
    }:
        return True
    return bool(validated.get("value-bridge-calculator"))


def resolve_analysis_synthesizer() -> AnalysisSynthesizer | None:
    """Pick advisory synthesizer from LLM_PROVIDER with cross-provider fallback."""
    prefer_gemini = LLM_PROVIDER == "gemini"
    if prefer_gemini and GEMINI_ENABLED:
        from app.opar.gemini_client import synthesize_analysis_gemini

        return synthesize_analysis_gemini
    if ANTHROPIC_ENABLED:
        from app.opar.claude_client import synthesize_analysis_claude

        return synthesize_analysis_claude
    if GEMINI_ENABLED:
        from app.opar.gemini_client import synthesize_analysis_gemini

        return synthesize_analysis_gemini
    return None


def build_transaction_examples_for_llm(validated: Dict[str, Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
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


def normalize_advisory_sections(raw: Dict[str, Any]) -> AdvisorySections | None:
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


def advisory_quality_ok(advisory: AdvisorySections, category_focused: bool = False) -> bool:
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
    if category_focused and len((advisory.category_focus_section or "").strip()) < 150:
        return False
    return True


def _estimate_tokens(payload: Dict[str, Any]) -> int:
    try:
        return len(json.dumps(payload, default=str)) // _CHARS_PER_TOKEN
    except Exception:
        return 0


def generate_llm_advisory_sections(
    ctx: ObserveContext,
    manifest: Dict[str, Any],
    validated: Dict[str, Dict[str, Any]],
    *,
    thinking_enabled: bool = False,
    thinking_budget_tokens: int = 8000,
    category_focused: bool | None = None,
) -> Tuple[AdvisorySections | None, str | None]:
    if not needs_llm_advisory(ctx, validated, category_focused=bool(category_focused)):
        return None, None

    synthesize = resolve_analysis_synthesizer()
    if synthesize is None:
        return None, None

    docs = []
    doc_summary = str(validated.get("document-contextualizer", {}).get("context_summary", "")).strip()
    if doc_summary:
        docs = [doc_summary]
    tx_examples = build_transaction_examples_for_llm(validated)

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
    logger.info("llm_token_budget estimated_tokens=%d limit=%d", estimated_tokens, _LLM_TOKEN_LIMIT)
    if estimated_tokens > _LLM_TOKEN_LIMIT:
        logger.warning(
            "llm_token_budget_exceeded estimated_tokens=%d limit=%d; skipping LLM synthesis",
            estimated_tokens,
            _LLM_TOKEN_LIMIT,
        )
        return None, None

    if category_focused is None:
        category_focused = bool(
            validated.get("savings-modeler") or validated.get("value-bridge-calculator")
        )

    best_effort: AdvisorySections | None = None
    captured_thinking: str | None = None
    mode_order = (True, False) if category_focused else (False, True)
    for strict_mode in mode_order:
        try:
            raw, thinking_text = synthesize(
                ctx.user_message,
                manifest,
                ctx.model_manifest,
                validated,
                docs,
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
        advisory = normalize_advisory_sections(raw or {})
        if not advisory:
            continue
        if advisory_quality_ok(advisory, category_focused=category_focused):
            return advisory, captured_thinking
        if (
            len((advisory.executive_takeaway or "").strip()) >= 60
            and len(advisory.business_levers) >= (2 if category_focused else 1)
        ):
            best_effort = advisory
    return best_effort, captured_thinking
