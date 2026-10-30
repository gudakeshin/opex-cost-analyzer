"""Model-capability gating for Anthropic request construction.

Haiku 4.5 and Sonnet 4.5 reject ``output_config.effort`` and adaptive thinking
(verified via the Models API capabilities endpoint); sending either returns a
400 and silently degrades LLM routing to the rule-based fallback.
"""

from __future__ import annotations

from app.opar.anthropic_api import (
    anthropic_max_tokens_for_thinking,
    anthropic_output_config,
    anthropic_thinking_kwargs,
)
from app.opar.claude_client import INTENT_CLASSIFY_MODEL
from app.opar.llm_schemas import INTENT_CLASSIFY_SCHEMA

ADAPTIVE_MODELS = ("claude-sonnet-4-6", "claude-sonnet-5")
LEGACY_MODELS = ("claude-haiku-4-5-20251001", "claude-sonnet-4-5-20250929")


def test_output_config_includes_effort_on_adaptive_models() -> None:
    for model in ADAPTIVE_MODELS:
        cfg = anthropic_output_config(model=model, budget_tokens=8000)
        assert cfg["output_config"]["effort"] == "high", model


def test_output_config_omits_effort_on_legacy_models() -> None:
    for model in LEGACY_MODELS:
        cfg = anthropic_output_config(model=model, budget_tokens=8000)
        assert "effort" not in cfg.get("output_config", {}), model


def test_output_config_empty_when_nothing_applies() -> None:
    assert anthropic_output_config(model="claude-haiku-4-5-20251001") == {}


def test_output_config_keeps_schema_on_legacy_models() -> None:
    cfg = anthropic_output_config(
        model="claude-haiku-4-5-20251001", schema={"type": "object"}
    )
    assert cfg["output_config"]["format"]["type"] == "json_schema"
    assert "effort" not in cfg["output_config"]


def test_intent_classify_request_shape_is_valid_for_pinned_model() -> None:
    """Regression: intent classification is pinned to Haiku, which rejects effort."""
    cfg = anthropic_output_config(model=INTENT_CLASSIFY_MODEL, schema=INTENT_CLASSIFY_SCHEMA)
    assert "effort" not in cfg["output_config"]
    assert cfg["output_config"]["format"]["schema"] is INTENT_CLASSIFY_SCHEMA


def test_thinking_kwargs_adaptive_on_current_models() -> None:
    for model in ADAPTIVE_MODELS:
        assert anthropic_thinking_kwargs(model=model) == {"thinking": {"type": "adaptive"}}, model


def test_thinking_kwargs_budget_tokens_on_legacy_models() -> None:
    for model in LEGACY_MODELS:
        kwargs = anthropic_thinking_kwargs(model=model, budget_tokens=6000)
        assert kwargs == {"thinking": {"type": "enabled", "budget_tokens": 6000}}, model


def test_max_tokens_headroom_only_for_legacy_thinking() -> None:
    assert (
        anthropic_max_tokens_for_thinking(1800, model="claude-sonnet-4-6", budget_tokens=8000)
        == 1800
    )
    assert (
        anthropic_max_tokens_for_thinking(
            1800, model="claude-haiku-4-5-20251001", budget_tokens=8000
        )
        == 10048
    )
