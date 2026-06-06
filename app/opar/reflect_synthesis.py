"""Reflect synthesis — barrel re-exports for backward compatibility."""
from __future__ import annotations

from app.config import ANTHROPIC_ENABLED, GEMINI_ENABLED
from app.opar.reflect_advisory import (
    advisory_quality_ok,
    build_transaction_examples_for_llm,
    generate_llm_advisory_sections,
    needs_llm_advisory,
    normalize_advisory_sections,
)
from app.opar.reflect_compose import (
    build_response_text,
    compose_response_from_advisory,
    format_business_case_for_chat,
)
from app.opar.reflect_conflicts import format_conflict_detection_response, format_conflict_line
from app.opar.reflect_currency import format_currency, set_reflect_currency
from app.opar.reflect_focus import (
    build_focus_category_section,
    business_lever_label,
    executive_callouts,
    is_category_focused_request,
    is_qa_lookup,
    match_focus_category,
    recommendation_rows,
)

__all__ = [
    "ANTHROPIC_ENABLED",
    "GEMINI_ENABLED",
    "advisory_quality_ok",
    "build_focus_category_section",
    "build_response_text",
    "build_transaction_examples_for_llm",
    "business_lever_label",
    "compose_response_from_advisory",
    "executive_callouts",
    "format_business_case_for_chat",
    "format_conflict_detection_response",
    "format_conflict_line",
    "format_currency",
    "generate_llm_advisory_sections",
    "is_category_focused_request",
    "is_qa_lookup",
    "match_focus_category",
    "needs_llm_advisory",
    "normalize_advisory_sections",
    "recommendation_rows",
    "set_reflect_currency",
]
