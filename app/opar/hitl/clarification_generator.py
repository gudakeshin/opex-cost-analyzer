"""Generate structured business clarification payloads via Gemini or fallback."""

from __future__ import annotations

import json
import os
import re
from typing import TYPE_CHECKING, Any

from app.config import GEMINI_ENABLED
from app.opar.gemini_client import call_gemini
from app.opar.hitl.clarification_tool import BusinessClarificationPayload

if TYPE_CHECKING:
    # Imported lazily to avoid a circular import: app.opar.models imports the
    # hitl package at module load, which would otherwise re-enter models before
    # ObserveContext is defined. Only needed for type hints (annotations are
    # strings under `from __future__ import annotations`).
    from app.opar.models import ObserveContext

_CLARIFICATION_SYSTEM = """You are an FP&A advisor preparing a human-in-the-loop clarification probe.
Return ONLY valid JSON with this schema (no markdown, no prose outside JSON):
{
  "question": "string — clear business question",
  "options": ["string", "string"] — 2 to 4 analytical paths or accounting treatments,
  "reasoning": "string — why human judgment is needed"
}

Rules:
- Frame options as business decisions (e.g. "Use industry median proxy (indicative only)")
- Never phrase options as code or system instructions
- Always include at least one path to provide missing data AND one path to proceed with caveats when data is missing
- Keep option labels concise (under 80 characters each)
"""

_INTENT_LABELS = {
    "benchmark": "peer benchmarking",
    "value_bridge": "value-at-the-table modeling",
    "business_case": "business case generation",
}


def _missing_field_labels(missing_fields: list[str]) -> list[str]:
    labels: list[str] = []
    if "spend_data" in missing_fields:
        labels.append("spend data file")
    if "annual_revenue" in missing_fields:
        labels.append("annual revenue")
    if "industry" in missing_fields:
        labels.append("industry classification")
    return labels


def _fallback_clarification(ctx: ObserveContext, company_name: str = "") -> BusinessClarificationPayload:
    """Deterministic payload when LLM is unavailable."""
    intent_label = _INTENT_LABELS.get(ctx.intent_class, ctx.intent_class.replace("_", " "))
    missing = _missing_field_labels(ctx.missing_fields)
    missing_text = ", ".join(missing) if missing else "required session inputs"

    question = (
        f"How should we proceed with {intent_label}"
        + (f" for {company_name}" if company_name else "")
        + f" given missing {missing_text}?"
    )

    options: list[str] = []
    if "spend_data" in ctx.missing_fields:
        options.append("Upload spend file now")
        options.append("Use industry median proxy (indicative only)")
    if "annual_revenue" in ctx.missing_fields:
        options.append("Enter annual revenue in session settings")
    if "industry" in ctx.missing_fields:
        options.append("Select industry in session settings")
    if len(options) < 2:
        options.append("Defer analysis until data is available")
    if len(options) < 2:
        options.append("Proceed with limited data (lower confidence)")

    options = options[:4]
    while len(options) < 2:
        options.append("Defer analysis until data is available")

    reasoning = (
        f"{intent_label.title()} requires {missing_text} to produce defensible outputs. "
        "Human input is needed to choose the analytical treatment before skills execute."
    )
    return BusinessClarificationPayload(question=question, options=options[:4], reasoning=reasoning)


def _parse_json_payload(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return json.loads(cleaned)


def _call_clarification_gemini(user_content: str) -> BusinessClarificationPayload:
    if os.getenv("PYTEST_CURRENT_TEST"):
        raise RuntimeError("Clarification LLM calls disabled during pytest runs")
    if not GEMINI_ENABLED:
        raise RuntimeError("Gemini not configured")
    raw = call_gemini(_CLARIFICATION_SYSTEM, user_content, max_tokens=512)
    data = _parse_json_payload(raw)
    return BusinessClarificationPayload.model_validate(data)


def _build_prompt(ctx: ObserveContext, company_name: str, industry: str) -> str:
    missing = _missing_field_labels(ctx.missing_fields)
    return json.dumps(
        {
            "intent": ctx.intent_class,
            "company_name": company_name or "unknown",
            "industry": industry or "not set",
            "missing_fields": missing,
            "data_quality_score": round(ctx.data_quality_score, 2),
            "user_message": ctx.user_message[:500],
        },
        indent=2,
    )


def generate_business_clarification(
    ctx: ObserveContext,
    *,
    company_name: str = "",
    industry: str = "",
) -> BusinessClarificationPayload:
    """Return a validated clarification payload; falls back to templates offline."""
    try:
        prompt = _build_prompt(ctx, company_name, industry)
        return _call_clarification_gemini(prompt)
    except Exception:
        return _fallback_clarification(ctx, company_name=company_name)
