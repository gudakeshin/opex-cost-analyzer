"""Provenance records which models actually ran, including a provider fallback."""
from __future__ import annotations

from app.metrics import record_llm_usage
from app.opar.provenance import record_llm_narrative
from app.services import llm_trace


def test_trace_collects_distinct_models_and_flags_a_fallback():
    with llm_trace.trace_scope():
        record_llm_usage("anthropic", "claude-sonnet-4-6", 10, 10)
        record_llm_usage("anthropic", "claude-sonnet-4-6", 10, 10)  # duplicates collapse
        assert llm_trace.summary() == {"llm_models_used": ["anthropic:claude-sonnet-4-6"], "provider_fallback": False}
        record_llm_usage("gemini", "gemini-2.5-flash", 10, 10)
        s = llm_trace.summary()
        assert s["provider_fallback"] is True and "gemini:gemini-2.5-flash" in s["llm_models_used"]


def test_narrative_provenance_includes_the_models_that_ran():
    with llm_trace.trace_scope():
        record_llm_usage("gemini", "gemini-2.5-flash", 10, 10)
        tag = record_llm_narrative(
            "takeaway",
            engagement_id="e-trace",
            turn_id="t-trace",
            skill_outputs_used=["a"],
            prompt_text="p",
            model_version="claude-sonnet-4-6",
        )
    assert tag["model_version"] == "claude-sonnet-4-6"  # configured
    assert tag["llm_models_used"] == ["gemini:gemini-2.5-flash"]  # actual
    assert tag["provider_fallback"] is False  # only one provider ran here
