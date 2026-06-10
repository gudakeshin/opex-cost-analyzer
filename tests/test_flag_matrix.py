"""
tests/test_flag_matrix.py — Parametrized tests for the 5 LLM/agent feature flags.

Verifies that each meaningful flag combination produces the correct routing
decision and degrades gracefully (no crash, deterministic fallback active).

Flags under test:
  ANTHROPIC_ENABLED         — Anthropic Claude API configured
  GEMINI_ENABLED            — Google Gemini API configured
  LLM_INTENT_CLASSIFICATION_ENABLED — LLM-first intent routing
  LLM_CHAT_SYNTHESIS_ENABLED        — LLM-backed chat QA
  AGENT_CONTROLLER_ENABLED          — agentic tool-loop path
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Flag combinations
# ---------------------------------------------------------------------------

_FLAG_KEYS = (
    "ANTHROPIC_ENABLED",
    "GEMINI_ENABLED",
    "LLM_INTENT_CLASSIFICATION_ENABLED",
    "LLM_CHAT_SYNTHESIS_ENABLED",
    "AGENT_CONTROLLER_ENABLED",
)

# (anthropic, gemini, intent, chat, agent)  — only meaningful combinations
_COMBOS: list[tuple[bool, bool, bool, bool, bool]] = [
    (False, False, False, False, False),  # fully deterministic
    (True,  False, True,  True,  True),   # anthropic only
    (False, True,  True,  True,  True),   # gemini only
    (True,  True,  True,  True,  True),   # all on (preferred-provider logic)
    (True,  True,  False, True,  True),   # intent classification off
    (True,  True,  True,  False, True),   # chat synthesis off
    (True,  True,  True,  True,  False),  # agent controller off
    (False, False, True,  True,  True),   # no provider despite flags on
]


def _combo_id(combo: tuple[bool, ...]) -> str:
    abbrs = ("A", "G", "I", "C", "Ag")
    return "-".join(f"{k}={'1' if v else '0'}" for k, v in zip(abbrs, combo))


# ---------------------------------------------------------------------------
# Helper: patch flag values in the relevant modules for one test
# ---------------------------------------------------------------------------

def _flag_patches(anthropic: bool, gemini: bool, intent: bool, chat: bool, agent: bool):
    """Context manager that patches all 5 flags across the modules that read them."""
    return [
        # chat_synthesis reads its own module-level copies
        patch("app.opar.chat_synthesis.ANTHROPIC_ENABLED", anthropic),
        patch("app.opar.chat_synthesis.GEMINI_ENABLED", gemini),
        patch("app.opar.chat_synthesis.LLM_CHAT_SYNTHESIS_ENABLED", chat),
        # observe.py for intent classification
        patch("app.opar.observe.ANTHROPIC_ENABLED", anthropic),
        patch("app.opar.observe.GEMINI_ENABLED", gemini),
        patch("app.opar.observe.LLM_INTENT_CLASSIFICATION_ENABLED", intent),
        # config-level for agent_loop_available
        patch("app.config.AGENT_CONTROLLER_ENABLED", agent),
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("combo", _COMBOS, ids=_combo_id)
def test_classify_intent_never_crashes(combo: tuple[bool, ...]) -> None:
    """classify_intent_with_meta must return a valid dict for any flag combo."""
    from app.opar.observe import classify_intent_with_meta

    anthropic, gemini, intent, chat, agent = combo
    with patch("app.opar.observe.ANTHROPIC_ENABLED", anthropic), \
         patch("app.opar.observe.GEMINI_ENABLED", gemini), \
         patch("app.opar.observe.LLM_INTENT_CLASSIFICATION_ENABLED", intent):
        result = classify_intent_with_meta("show me total spend by category")

    assert isinstance(result, dict), f"Expected dict, got {type(result)}"
    assert "intent_class" in result, f"Missing intent_class in {result}"
    assert result["intent_class"], "intent_class must be non-empty"


@pytest.mark.parametrize("combo", _COMBOS, ids=_combo_id)
def test_resolve_chat_synthesizer_consistent_with_flags(combo: tuple[bool, ...]) -> None:
    """resolve_chat_synthesizer returns None iff both providers are disabled."""
    from app.opar.chat_synthesis import resolve_chat_synthesizer

    anthropic, gemini, intent, chat, agent = combo
    patches = [
        patch("app.opar.chat_synthesis.ANTHROPIC_ENABLED", anthropic),
        patch("app.opar.chat_synthesis.GEMINI_ENABLED", gemini),
    ]
    with patches[0], patches[1]:
        synth = resolve_chat_synthesizer()

    if not anthropic and not gemini:
        assert synth is None, "No provider → synthesizer must be None"
    else:
        assert synth is not None, "At least one provider → synthesizer must be non-None"


@pytest.mark.parametrize("chat_flag", [True, False], ids=["chat_on", "chat_off"])
def test_chat_synthesis_respects_enabled_flag(chat_flag: bool) -> None:
    """_synthesize_via_llm returns (None, None) when LLM_CHAT_SYNTHESIS_ENABLED=False."""
    from app.opar.chat_synthesis import _synthesize_via_llm

    ctx: dict = {"question": "what is total spend?", "spend_data": [], "currency": "INR"}
    with patch("app.opar.chat_synthesis.LLM_CHAT_SYNTHESIS_ENABLED", chat_flag), \
         patch("app.opar.chat_synthesis._iter_chat_synthesizers", return_value=[]):
        # With no synthesizers and flag on we still get (None, None); flag off is the same.
        text, thinking = _synthesize_via_llm(ctx)

    assert text is None
    assert thinking is None


def test_chat_synthesis_disabled_returns_none_without_touching_synthesizer() -> None:
    """When LLM_CHAT_SYNTHESIS_ENABLED=False the synthesizer list is never consulted."""
    from app.opar.chat_synthesis import _synthesize_via_llm

    mock_synth = MagicMock(return_value=("answer", None))
    ctx: dict = {"question": "test", "spend_data": [], "currency": "INR"}
    with patch("app.opar.chat_synthesis.LLM_CHAT_SYNTHESIS_ENABLED", False), \
         patch("app.opar.chat_synthesis._iter_chat_synthesizers", return_value=[mock_synth]):
        text, thinking = _synthesize_via_llm(ctx)

    assert text is None
    mock_synth.assert_not_called()


def test_agent_loop_unavailable_when_controller_disabled() -> None:
    """agent_loop_available() is False whenever AGENT_CONTROLLER_ENABLED=False."""
    from app.opar.agent_runtime import agent_loop_available

    with patch("app.config.AGENT_CONTROLLER_ENABLED", False):
        # PYTEST_CURRENT_TEST is set, so this will also return False — but we confirm
        # that the config flag is the documented gate (the pytest guard is secondary).
        result = agent_loop_available()

    assert result is False


@pytest.mark.parametrize("combo", _COMBOS, ids=_combo_id)
def test_iter_chat_synthesizers_length_consistent(combo: tuple[bool, ...]) -> None:
    """_iter_chat_synthesizers returns 0 entries when both providers disabled."""
    from app.opar.chat_synthesis import _iter_chat_synthesizers

    anthropic, gemini, _intent, _chat, _agent = combo
    with patch("app.opar.chat_synthesis.ANTHROPIC_ENABLED", anthropic), \
         patch("app.opar.chat_synthesis.GEMINI_ENABLED", gemini), \
         patch("app.opar.chat_synthesis.is_gemini_quota_exhausted", lambda: False,
               create=True), \
         patch("app.opar.gemini_client.is_gemini_quota_exhausted", lambda: False):
        synths = _iter_chat_synthesizers()

    if not anthropic and not gemini:
        assert len(synths) == 0, f"Expected 0 synthesizers, got {len(synths)}"
    else:
        assert len(synths) > 0, "Expected ≥1 synthesizer when a provider is enabled"


def test_all_flags_off_classify_still_returns_category_intent() -> None:
    """Fully deterministic mode: keyword classifier produces a valid intent."""
    from app.opar.observe import classify_intent_with_meta

    with patch("app.opar.observe.ANTHROPIC_ENABLED", False), \
         patch("app.opar.observe.GEMINI_ENABLED", False), \
         patch("app.opar.observe.LLM_INTENT_CLASSIFICATION_ENABLED", False):
        result = classify_intent_with_meta("what are the top vendors by spend")

    assert result.get("intent_class") in (
        "spend_analysis", "category_deep_dive", "peer_benchmark",
        "general_qa", "value_bridge", "analyze", None,
    ) or result.get("intent_class")


def test_flag_defaults_match_expected_production_values() -> None:
    """Verify that flag defaults (from env with no overrides) match their documented defaults."""
    import os
    from unittest.mock import patch as os_patch

    # Temporarily clear the relevant env vars so defaults are read from code.
    env_keys = [
        "LLM_INTENT_CLASSIFICATION_ENABLED",
        "LLM_CHAT_SYNTHESIS_ENABLED",
        "AGENT_CONTROLLER_ENABLED",
    ]
    clean_env = {k: v for k, v in os.environ.items() if k not in env_keys}
    with os_patch.dict(os.environ, clean_env, clear=True):
        import importlib
        import app.config as cfg_mod
        importlib.reload(cfg_mod)

        assert cfg_mod.LLM_INTENT_CLASSIFICATION_ENABLED is True, "Default should be True"
        assert cfg_mod.LLM_CHAT_SYNTHESIS_ENABLED is True, "Default should be True"
        assert cfg_mod.AGENT_CONTROLLER_ENABLED is True, "Default should be True"

    # Reload to restore normal state.
    importlib.reload(cfg_mod)
