"""Tests for per-request LLM model selection."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from app.services.llm_selection import (
    get_resolved_llm_model,
    get_resolved_llm_provider,
    llm_selection_context,
    model_for_provider,
    normalize_model_id,
    provider_for_model,
    submit_with_context,
)


def test_provider_for_model():
    assert provider_for_model("claude-sonnet-4-6") == "anthropic"
    assert provider_for_model("gemini-2.5-flash") == "gemini"


def test_llm_selection_context_overrides_provider_and_model(monkeypatch):
    monkeypatch.setattr("app.services.llm_selection.ANTHROPIC_ENABLED", True)
    monkeypatch.setattr("app.services.llm_selection.GEMINI_ENABLED", True)
    monkeypatch.setattr(
        "app.services.llm_selection.available_models",
        lambda: [
            {"id": "claude-sonnet-4-6", "label": "Claude", "provider": "anthropic"},
            {"id": "gemini-2.5-flash", "label": "Gemini", "provider": "gemini"},
        ],
    )
    with llm_selection_context("claude-sonnet-4-6"):
        assert get_resolved_llm_provider() == "anthropic"
        assert get_resolved_llm_model() == "claude-sonnet-4-6"
    with llm_selection_context("gemini-2.5-flash"):
        assert get_resolved_llm_provider() == "gemini"
        assert get_resolved_llm_model() == "gemini-2.5-flash"


def test_model_for_provider_ignores_mismatched_override(monkeypatch):
    monkeypatch.setattr("app.services.llm_selection.ANTHROPIC_ENABLED", True)
    monkeypatch.setattr("app.services.llm_selection.GEMINI_ENABLED", True)
    monkeypatch.setattr(
        "app.services.llm_selection.available_models",
        lambda: [
            {"id": "claude-sonnet-4-6", "label": "Claude", "provider": "anthropic"},
            {"id": "gemini-2.5-flash", "label": "Gemini", "provider": "gemini"},
        ],
    )
    with llm_selection_context("claude-sonnet-4-6"):
        assert model_for_provider("gemini") == "gemini-2.5-flash"
        assert model_for_provider("anthropic") == "claude-sonnet-4-6"


def test_submit_with_context_propagates_llm_override(monkeypatch):
    monkeypatch.setattr("app.services.llm_selection.ANTHROPIC_ENABLED", True)
    monkeypatch.setattr("app.services.llm_selection.GEMINI_ENABLED", True)
    monkeypatch.setattr(
        "app.services.llm_selection.available_models",
        lambda: [
            {"id": "claude-sonnet-4-6", "label": "Claude", "provider": "anthropic"},
            {"id": "gemini-2.5-flash", "label": "Gemini", "provider": "gemini"},
        ],
    )

    def worker():
        return get_resolved_llm_provider(), get_resolved_llm_model()

    with llm_selection_context("gemini-2.5-flash"):
        with ThreadPoolExecutor(max_workers=1) as executor:
            assert submit_with_context(executor, worker).result() == ("gemini", "gemini-2.5-flash")


def test_normalize_model_id_rejects_unknown(monkeypatch):
    monkeypatch.setattr(
        "app.services.llm_selection.available_models",
        lambda: [{"id": "claude-sonnet-4-6", "label": "Claude", "provider": "anthropic"}],
    )
    assert normalize_model_id("claude-sonnet-4-6") == "claude-sonnet-4-6"
    assert normalize_model_id("not-a-real-model") is None
