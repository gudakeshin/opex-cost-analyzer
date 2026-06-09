"""Tests for reflect context headers and LLM advisory routing."""
from __future__ import annotations

from unittest.mock import patch

from app.opar.models import ObserveContext
from app.opar.reflect_advisory import generate_llm_advisory_sections, needs_llm_advisory, resolve_analysis_synthesizer
from app.opar.reflect_context import (
    build_analysis_context_lines,
    format_benchmark_attribution_line,
    format_spend_profile_line,
    format_value_bridge_line,
)
from app.opar.reflect_synthesis import generate_llm_advisory_sections as barrel_generate


def test_needs_llm_advisory_false_for_empty_validated() -> None:
    ctx = ObserveContext(user_message="hello", intent_class="general_qa")
    assert needs_llm_advisory(ctx, {}) is False


def test_needs_llm_advisory_true_for_value_bridge_intent() -> None:
    ctx = ObserveContext(user_message="value bridge", intent_class="value_bridge")
    validated = {"value-bridge-calculator": {"confidence_bands": {"mid": 1_000_000}}}
    with patch("app.opar.reflect_advisory.GEMINI_ENABLED", True):
        assert needs_llm_advisory(ctx, validated) is True


def test_needs_llm_advisory_true_for_category_focused_root_cause_without_value_bridge() -> None:
    """A "what drives spend in <category>" turn runs root-cause-analyzer/peer-benchmarker
    but not necessarily value-bridge-calculator/savings-modeler — it still warrants an
    LLM narrative when the question is category-focused, so it isn't left to the generic
    whole-portfolio build_response_text fallback."""
    ctx = ObserveContext(
        user_message="What drives spend in HR & Recruitment?",
        intent_class="value_bridge",
        explicit_category="HR & Recruitment",
        query_capabilities=["root_cause", "value_modeling"],
    )
    validated = {
        "spend-profiler": {"category_profile": [], "total_spend": 1_000_000},
        "root-cause-analyzer": {"root_cause_findings": []},
        "peer-benchmarker": {"comparisons": []},
    }
    with patch("app.opar.reflect_advisory.GEMINI_ENABLED", True):
        assert needs_llm_advisory(ctx, validated, category_focused=True) is True
        # Without category focus, the narrower value-bridge/savings-modeler gate still applies.
        assert needs_llm_advisory(ctx, validated, category_focused=False) is False


def test_generate_skipped_when_not_needed() -> None:
    ctx = ObserveContext(user_message="hello", intent_class="general_qa")
    advisory, thinking, _skip = generate_llm_advisory_sections(ctx, {}, {}, category_focused=False)
    assert advisory is None
    assert thinking is None


def test_resolve_analysis_synthesizer_prefers_gemini_when_configured() -> None:
    with patch("app.opar.reflect_advisory.get_resolved_llm_provider", return_value="gemini"), patch(
        "app.opar.reflect_advisory.GEMINI_ENABLED", True
    ):
        fn = resolve_analysis_synthesizer()
    assert fn is not None
    assert fn.__name__ == "synthesize_analysis_gemini"


def test_resolve_analysis_synthesizer_falls_back_to_claude() -> None:
    with patch("app.opar.reflect_advisory.get_resolved_llm_provider", return_value="anthropic"), patch(
        "app.opar.reflect_advisory.ANTHROPIC_ENABLED", True
    ), patch("app.opar.reflect_advisory.GEMINI_ENABLED", False):
        fn = resolve_analysis_synthesizer()
    assert fn is not None
    assert fn.__name__ == "synthesize_analysis_claude"


def test_build_analysis_context_lines_includes_spend_bridge_and_benchmark() -> None:
    validated = {
        "spend-profiler": {"category_profile": [{}, {}], "total_spend": 500_000},
        "value-bridge-calculator": {"confidence_bands": {"low": 1, "mid": 2, "high": 3}},
        "peer-benchmarker": {
            "benchmark_dataset": {"source": "PeerSet", "vintage_date": "2024-Q4", "specificity_score": 0.8}
        },
    }
    lines = build_analysis_context_lines(validated)
    assert len(lines) == 3
    assert "2 categories" in lines[0]
    assert "Value bridge" in lines[1]
    assert "PeerSet" in lines[2]


def test_format_helpers_return_none_when_data_missing() -> None:
    assert format_spend_profile_line({}) is None
    assert format_value_bridge_line({}) is None
    assert format_benchmark_attribution_line({}) is None


def test_barrel_reexports_advisory_entry_points() -> None:
    ctx = ObserveContext(user_message="hello", intent_class="general_qa")
    advisory, thinking, _skip = barrel_generate(ctx, {}, {}, category_focused=False)
    assert advisory is None
    assert thinking is None
