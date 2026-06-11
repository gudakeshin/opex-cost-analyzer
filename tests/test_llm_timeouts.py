"""Tests for LLM synthesis timeout budgeting."""
from __future__ import annotations

import json
from concurrent.futures import TimeoutError as FuturesTimeoutError
from unittest.mock import MagicMock, patch

from app.config import (
    LLM_SYNTHESIS_TIMEOUT_SECONDS,
    OPAR_TIMEOUT_SECONDS,
    llm_synthesis_timeout_seconds,
    llm_thinking_timeout_seconds,
)
from app.opar.claude_client import _scale_thinking_budget, _timeout_budget_seconds, synthesize_analysis_claude


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


def test_scale_thinking_budget_reduces_for_large_payload() -> None:
    small = {"a": "x" * 1_000}
    medium = {"a": "x" * 45_000}
    huge = {"a": "x" * 60_000}
    assert _scale_thinking_budget(small, 8000) == 8000
    assert _scale_thinking_budget(medium, 8000) == 5000
    assert _scale_thinking_budget(huge, 8000) == 3500


def test_synthesize_analysis_claude_falls_back_after_thinking_timeout() -> None:
    advisory = {
        "executive_takeaway": "Savings focus on vendor consolidation.",
        "business_levers": [{"title": "Consolidate", "detail": "Reduce tail spend."}],
    }
    future_thinking = MagicMock()
    future_thinking.result.side_effect = FuturesTimeoutError()
    future_standard = MagicMock()
    future_standard.result.return_value = json.dumps(advisory)

    with patch("app.opar.claude_client.ANTHROPIC_ENABLED", True), patch(
        "app.opar.claude_client.GEMINI_ENABLED", False
    ), patch("app.opar.claude_client.ThreadPoolExecutor") as executor_cls, patch(
        "app.opar.claude_client.submit_with_context"
    ) as submit:
        executor = MagicMock()
        executor_cls.return_value = executor
        submit.side_effect = [future_thinking, future_standard]

        data, thinking = synthesize_analysis_claude(
            "What are top savings?",
            {"company_name": "Test Co", "industry": "bfsi_banks"},
            {},
            {"value-bridge-calculator": {"confidence_bands": {"mid": 1_000_000}}},
            [],
            thinking_enabled=True,
        )

    assert data == advisory
    assert thinking is None
    assert submit.call_count == 2
