"""Tests for Anthropic prompt caching (Phase 2)."""

from __future__ import annotations

from app.metrics import llm_tokens_total, record_llm_usage
from app.opar.anthropic_api import (
    CACHE_CONTROL_EPHEMERAL,
    anthropic_usage_fields,
    apply_tool_cache_breakpoint,
    build_chat_user_content_blocks,
    cached_system_blocks,
    record_anthropic_usage,
)
from app.opar.chat_synthesis import (
    build_chat_context,
    build_chat_user_content_blocks as chat_blocks_from_context,
    split_chat_context_for_caching,
)
from app.opar.models import ObserveContext


def test_split_chat_context_separates_stable_and_turn_fields() -> None:
    context = {
        "session_context": {"company_name": "Acme"},
        "spend_data": {"total_spend": 100.0, "categories": []},
        "portfolio_summary": {"category_count": 1},
        "user_message": "top suppliers?",
        "query_analysis": {"breakdown_dimension": "supplier"},
        "recent_turns": [{"role": "user", "content": "hi"}],
        "document_excerpts": ["contract excerpt"],
    }
    cached, turn = split_chat_context_for_caching(context)
    assert cached["session_context"]["company_name"] == "Acme"
    assert "spend_data" in cached
    assert turn["user_message"] == "top suppliers?"
    assert turn["recent_turns"][0]["content"] == "hi"
    assert "user_message" not in cached
    assert "spend_data" not in turn


def test_build_chat_user_content_blocks_marks_stable_prefix() -> None:
    blocks = build_chat_user_content_blocks('{"a": 1}', '{"user_message": "q"}')
    assert len(blocks) == 2
    assert blocks[0]["cache_control"] == CACHE_CONTROL_EPHEMERAL
    assert "cache_control" not in blocks[1]
    assert "Current turn" in blocks[1]["text"]


def test_cached_system_blocks_ephemeral() -> None:
    blocks = cached_system_blocks("system prompt")
    assert blocks[0]["cache_control"] == CACHE_CONTROL_EPHEMERAL


def test_apply_tool_cache_breakpoint_on_last_tool() -> None:
    tools = [{"name": "a"}, {"name": "b"}]
    out = apply_tool_cache_breakpoint(tools)
    assert "cache_control" not in out[0]
    assert out[1]["cache_control"] == CACHE_CONTROL_EPHEMERAL


def test_build_chat_context_produces_cacheable_blocks() -> None:
    ctx = ObserveContext(
        user_message="Show top suppliers",
        intent_class="general_qa",
        session_id="s1",
        has_tabular_spend=True,
    )
    manifest = {"company_name": "Acme", "currency": "INR"}
    skill_outputs = {
        "spend-profiler": {
            "total_spend": 1_000_000,
            "category_profile": [
                {"category_id": "IT", "category_name": "IT", "spend": 500_000, "line_count": 1}
            ],
        }
    }
    context = build_chat_context(ctx, manifest, skill_outputs, currency="INR")
    blocks = chat_blocks_from_context(context)
    assert blocks[0]["cache_control"] == CACHE_CONTROL_EPHEMERAL
    assert "Show top suppliers" in blocks[1]["text"]


def test_record_llm_usage_tracks_cache_read_tokens() -> None:
    before = llm_tokens_total.labels(provider="anthropic", model="claude-sonnet-5", token_type="cache_read")._value.get()
    record_llm_usage(
        "anthropic",
        "claude-sonnet-5",
        input_tokens=100,
        output_tokens=50,
        cache_read_input_tokens=900,
        cache_creation_input_tokens=0,
    )
    after = llm_tokens_total.labels(provider="anthropic", model="claude-sonnet-5", token_type="cache_read")._value.get()
    assert after - before == 900


def test_anthropic_usage_fields_reads_cache_counters() -> None:
    class _Usage:
        input_tokens = 10
        output_tokens = 5
        cache_read_input_tokens = 200
        cache_creation_input_tokens = 50

    assert anthropic_usage_fields(_Usage()) == (10, 5, 200, 50)


def test_record_anthropic_usage_delegates_cache_fields() -> None:
    class _Usage:
        input_tokens = 1
        output_tokens = 2
        cache_read_input_tokens = 3
        cache_creation_input_tokens = 4

    before = llm_tokens_total.labels(
        provider="anthropic", model="claude-sonnet-4-6", token_type="cache_creation"
    )._value.get()
    record_anthropic_usage(_Usage(), "claude-sonnet-4-6")
    after = llm_tokens_total.labels(
        provider="anthropic", model="claude-sonnet-4-6", token_type="cache_creation"
    )._value.get()
    assert after - before == 4
