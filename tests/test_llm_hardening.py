"""LLM hardening: unverified-figure check, tolerant JSON extraction, truncation retry."""
from __future__ import annotations

import sys
import types

import pytest

from app.opar import claude_client
from app.opar.figure_check import find_unverified_figures


OUTPUTS = {"spend-profiler": {"total_spend": 124_300_000.0, "cats": [{"spend": 4_500_000.0}]}, "vb": {"mid": 8_750_000}}


def test_grounded_figures_pass_and_invented_ones_are_flagged():
    text = "Total ₹12.43 Cr, IT ₹45 L, savings ₹87.5 lakh, ₹4,500,000 exactly."
    assert find_unverified_figures(text, OUTPUTS) == []
    flagged = find_unverified_figures("We can save ₹9.9 Cr and $2.3M across 12 suppliers (15%).", OUTPUTS)
    assert flagged == ["₹9.9 Cr", "$2.3M"]


def test_figure_check_is_quiet_without_data():
    assert find_unverified_figures("₹5 Cr", {}) == []
    assert find_unverified_figures("", OUTPUTS) == []


def test_extract_json_tolerates_surrounding_prose():
    assert claude_client._extract_json('Here is the analysis: {"a": 1} Hope that helps.') == {"a": 1}
    assert claude_client._extract_json('```json\n{"b": 2}\n```') == {"b": 2}
    with pytest.raises(Exception):
        claude_client._extract_json("no json at all")


class _Resp:
    def __init__(self, text: str, stop: str):
        self.content = [types.SimpleNamespace(text=text)]
        self.stop_reason = stop
        self.usage = None


def _install_fake_anthropic(monkeypatch, responses, calls):
    class _Messages:
        def create(self, **kw):
            calls.append(kw)
            return responses.pop(0)

    class _Client:
        def __init__(self, **kw):
            self.messages = _Messages()

    monkeypatch.setitem(sys.modules, "anthropic", types.SimpleNamespace(Anthropic=_Client))
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setattr(claude_client, "ANTHROPIC_API_KEY", "k")
    monkeypatch.setattr(claude_client, "ANTHROPIC_ENABLED", True)


def test_truncated_response_is_retried_once_with_larger_budget(monkeypatch):
    calls: list = []
    _install_fake_anthropic(monkeypatch, [_Resp('{"a":', "max_tokens"), _Resp('{"a": 1}', "end_turn")], calls)
    out = claude_client._call_anthropic_native("sys", "user", max_tokens=1000, model="m")
    assert out == '{"a": 1}'
    assert [c["max_tokens"] for c in calls] == [1000, 2000]


def test_complete_response_is_not_retried(monkeypatch):
    calls: list = []
    _install_fake_anthropic(monkeypatch, [_Resp("ok", "end_turn")], calls)
    assert claude_client._call_anthropic_native("sys", "user", max_tokens=1000, model="m") == "ok"
    assert len(calls) == 1


def test_temperature_only_sent_when_configured(monkeypatch):
    calls: list = []
    _install_fake_anthropic(monkeypatch, [_Resp("a", "end_turn"), _Resp("b", "end_turn")], calls)
    claude_client._call_anthropic_native("s", "u", model="m")
    monkeypatch.setattr(claude_client, "LLM_TEMPERATURE", 0.2)
    claude_client._call_anthropic_native("s", "u", model="m")
    assert "temperature" not in calls[0]
    assert calls[1]["temperature"] == 0.2
