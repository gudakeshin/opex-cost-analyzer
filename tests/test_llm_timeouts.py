"""Tests for LLM synthesis timeout budgeting."""
from __future__ import annotations

import json

from app.config import (
    LLM_SYNTHESIS_TIMEOUT_SECONDS,
    OPAR_TIMEOUT_SECONDS,
    llm_synthesis_timeout_seconds,
    llm_thinking_timeout_seconds,
)
from app.opar.claude_client import _timeout_budget_seconds


def test_llm_synthesis_timeout_scales_with_payload() -> None:
    small = llm_synthesis_timeout_seconds(10_000)
    large = llm_synthesis_timeout_seconds(120_000)
    assert small >= 30
    assert large >= small
    assert large <= OPAR_TIMEOUT_SECONDS


def test_llm_thinking_timeout_respects_opar_cap() -> None:
    assert llm_thinking_timeout_seconds() <= OPAR_TIMEOUT_SECONDS
    assert llm_thinking_timeout_seconds() >= 90


def test_timeout_budget_uses_synthesis_config() -> None:
    payload = {"user_message": "x", "skill_outputs": {"spend-profiler": {"total_spend": 1}}}
    budget = _timeout_budget_seconds(payload, strict_mode=False)
    assert budget >= LLM_SYNTHESIS_TIMEOUT_SECONDS
    strict = _timeout_budget_seconds(payload, strict_mode=True)
    assert strict >= budget


def test_timeout_budget_grows_with_payload_size() -> None:
    small = {"a": "x" * 1000}
    large = {"a": "x" * 120_000}
    assert _timeout_budget_seconds(large) >= _timeout_budget_seconds(small)
