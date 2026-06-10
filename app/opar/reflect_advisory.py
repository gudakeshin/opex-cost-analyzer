"""Reflect LLM advisory — lazy Claude/Gemini synthesis for value-bridge responses."""
from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Tuple

from app.config import ANTHROPIC_ENABLED, GEMINI_ENABLED, logger
from app.services.llm_selection import get_resolved_llm_provider
from app.opar.models import AdvisorySections, ObserveContext

_LLM_TOKEN_LIMIT = 80_000
_CHARS_PER_TOKEN = 4

# Skills whose presence indicates a deep, category-level analysis ran (peer/
# internal benchmarking, root-cause, variance/trend, value modeling). When the
# user's question is category-focused and any of these ran, the answer should
# be an LLM narrative tailored to the question — not the generic value-bridge-
# only gate below, which would otherwise miss benchmark/drill_down/root-cause
# turns that don't happen to run value-bridge-calculator or savings-modeler.
_DEEP_ANALYSIS_SKILLS = frozenset({
    "peer-benchmarker",
    "internal-benchmarker",
    "root-cause-analyzer",
    "bva-analyzer",
    "temporal-analyzer",
    "savings-modeler",
    "value-bridge-calculator",
})

_ANALYSIS_INTENTS = frozenset({
    "benchmark",
    "value_bridge",
    "business_case",
    "savings_plan",
    "drill_down",
    "sensitivity",
})


def _has_spend_context(validated: Dict[str, Dict[str, Any]]) -> bool:
    profile = validated.get("spend-profiler")
    if not isinstance(profile, dict):
        return False
    if float(profile.get("total_spend", 0) or 0) > 0:
        return True
    cats = profile.get("category_profile")
    return isinstance(cats, list) and len(cats) > 0

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
    has_value_modeling = "value-bridge-calculator" in validated or "savings-modeler" in validated
    has_deep_analysis = any(skill in validated for skill in _DEEP_ANALYSIS_SKILLS)
    has_rich_context = has_value_modeling or has_deep_analysis or _has_spend_context(validated)
    if not has_rich_context:
        return False
    if ctx.wants_executive_narrative:
        return True
    if category_focused:
        return True
    if ctx.intent_class in _ANALYSIS_INTENTS:
        return True
    return bool(validated.get("value-bridge-calculator"))


def resolve_analysis_synthesizer() -> AnalysisSynthesizer | None:
    """Pick advisory synthesizer from LLM_PROVIDER with cross-provider fallback."""
    ordered = _iter_analysis_synthesizers()
    return ordered[0] if ordered else None


def _iter_analysis_synthesizers() -> list[AnalysisSynthesizer]:
    """Ordered advisory synthesizers: preferred provider first, then fallback."""
    from app.opar.claude_client import synthesize_analysis_claude
    from app.opar.gemini_client import is_gemini_quota_exhausted, synthesize_analysis_gemini

    prefer_gemini = get_resolved_llm_provider() == "gemini"
    gemini_available = GEMINI_ENABLED and not is_gemini_quota_exhausted()
    ordered: list[AnalysisSynthesizer] = []
    if prefer_gemini:
        if gemini_available:
            ordered.append(synthesize_analysis_gemini)
        if ANTHROPIC_ENABLED:
            ordered.append(synthesize_analysis_claude)
    else:
        if ANTHROPIC_ENABLED:
            ordered.append(synthesize_analysis_claude)
        if gemini_available:
            ordered.append(synthesize_analysis_gemini)
    return ordered


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


def _estimate_tokens(payload: Any) -> int:
    try:
        return len(json.dumps(payload, default=str)) // _CHARS_PER_TOKEN
    except Exception:
        return 0


def _drop_largest_to_budget(
    skill_outputs: Dict[str, Any], overshoot_tokens: int
) -> Tuple[Dict[str, Any], List[str]]:
    """Drop the largest skill payloads until ~overshoot_tokens are reclaimed.

    Degraded synthesis over the remaining skills beats no synthesis at all —
    the deterministic fallback is strictly worse than an LLM narrative built
    from a partial skill set.
    """
    sizes = sorted(
        ((skill, _estimate_tokens(output)) for skill, output in skill_outputs.items()),
        key=lambda kv: kv[1],
        reverse=True,
    )
    dropped: List[str] = []
    reclaimed = 0
    for skill, size in sizes:
        if reclaimed >= overshoot_tokens:
            break
        dropped.append(skill)
        reclaimed += size
    return {k: v for k, v in skill_outputs.items() if k not in dropped}, dropped


def generate_llm_advisory_sections(
    ctx: ObserveContext,
    manifest: Dict[str, Any],
    validated: Dict[str, Dict[str, Any]],
    *,
    thinking_enabled: bool = False,
    thinking_budget_tokens: int = 8000,
    category_focused: bool | None = None,
    thinking_callback: Callable[[str], None] | None = None,
) -> Tuple[AdvisorySections | None, str | None, str | None]:
    if not needs_llm_advisory(ctx, validated, category_focused=bool(category_focused)):
        return None, None, None

    synthesizers = _iter_analysis_synthesizers()
    if not synthesizers:
        return None, None, "provider_unavailable"

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

    from app.opar.claude_client import _slim_skill_outputs, _truncate_doc_chunks

    slim_skill_outputs = _slim_skill_outputs(validated)
    doc_chunks = retrieved_context if retrieved_context else _truncate_doc_chunks(docs, max_chunks=2)

    def _payload_estimate(outputs: Dict[str, Any]) -> int:
        return _estimate_tokens({
            "user_message": ctx.user_message,
            "session_context": {
                "company_name": manifest.get("company_name"),
                "industry": manifest.get("industry"),
                "annual_revenue": manifest.get("annual_revenue"),
                "currency": manifest.get("currency"),
            },
            "skill_outputs": outputs,
            "document_chunks": doc_chunks,
            "transaction_examples": tx_examples,
        })

    estimated_tokens = _payload_estimate(slim_skill_outputs)
    logger.info("llm_token_budget estimated_tokens=%d limit=%d", estimated_tokens, _LLM_TOKEN_LIMIT)
    if estimated_tokens > _LLM_TOKEN_LIMIT:
        slim_skill_outputs, dropped = _drop_largest_to_budget(
            slim_skill_outputs, estimated_tokens - _LLM_TOKEN_LIMIT
        )
        estimated_tokens = _payload_estimate(slim_skill_outputs)
        if estimated_tokens > _LLM_TOKEN_LIMIT or not slim_skill_outputs:
            logger.warning(
                "llm_token_budget_exceeded estimated_tokens=%d limit=%d; skipping LLM synthesis",
                estimated_tokens,
                _LLM_TOKEN_LIMIT,
            )
            return None, None, "token_budget_exceeded"
        logger.warning(
            "llm_token_budget_degraded dropped=%s estimated_tokens=%d limit=%d",
            ",".join(dropped),
            estimated_tokens,
            _LLM_TOKEN_LIMIT,
        )

    if category_focused is None:
        category_focused = bool(
            validated.get("savings-modeler") or validated.get("value-bridge-calculator")
        )

    best_effort: AdvisorySections | None = None
    captured_thinking: str | None = None
    # Extended-thinking calls are slow — one quality pass avoids doubling wall-clock time.
    mode_order: tuple[bool, ...]
    if thinking_enabled:
        mode_order = (True,) if category_focused else (False,)
    else:
        mode_order = (True, False) if category_focused else (False, True)
    synth_kwargs = {
        "manifest": manifest,
        "model_manifest": ctx.model_manifest,
        "skill_outputs": slim_skill_outputs,
        "docs_text": docs,
        "transaction_examples": tx_examples,
        "thinking_enabled": thinking_enabled,
        "thinking_budget_tokens": thinking_budget_tokens,
        "deep_research_summary": ctx.deep_research_summary,
        "retrieved_context": retrieved_context,
    }
    had_any_raw = False
    for synthesize in synthesizers:
        for strict_mode in mode_order:
            try:
                raw, thinking_text = synthesize(
                    ctx.user_message,
                    **synth_kwargs,
                    strict_mode=strict_mode,
                )
            except Exception as exc:
                logger.warning("llm_advisory_synthesizer_error error=%s", exc)
                raw, thinking_text = None, None
            if raw is not None:
                had_any_raw = True
            if thinking_text:
                if not captured_thinking:
                    captured_thinking = thinking_text
                if thinking_callback:
                    thinking_callback(thinking_text)
            advisory = normalize_advisory_sections(raw or {})
            if not advisory:
                continue
            if advisory_quality_ok(advisory, category_focused=category_focused):
                return advisory, captured_thinking, None
            if (
                len((advisory.executive_takeaway or "").strip()) >= 60
                and len(advisory.business_levers) >= (2 if category_focused else 1)
            ):
                best_effort = advisory
        if best_effort is not None:
            break
    if best_effort is not None:
        return best_effort, captured_thinking, None
    # Extended thinking on large contexts often exceeds the wall-clock budget — retry fast path.
    if not had_any_raw and thinking_enabled:
        synth_kwargs["thinking_enabled"] = False
        for synthesize in synthesizers:
            for strict_mode in mode_order:
                try:
                    raw, thinking_text = synthesize(
                        ctx.user_message,
                        **synth_kwargs,
                        strict_mode=strict_mode,
                    )
                except Exception as exc:
                    logger.warning("llm_advisory_synthesizer_error error=%s", exc)
                    raw, thinking_text = None, None
                if raw is not None:
                    had_any_raw = True
                advisory = normalize_advisory_sections(raw or {})
                if not advisory:
                    continue
                if advisory_quality_ok(advisory, category_focused=category_focused):
                    return advisory, captured_thinking, None
                if (
                    len((advisory.executive_takeaway or "").strip()) >= 60
                    and len(advisory.business_levers) >= (2 if category_focused else 1)
                ):
                    best_effort = advisory
            if best_effort is not None:
                break
        if best_effort is not None:
            return best_effort, captured_thinking, None
    if not had_any_raw and best_effort is None:
        return None, captured_thinking, "provider_failed"
    return None, captured_thinking, "synthesis_quality_low"
