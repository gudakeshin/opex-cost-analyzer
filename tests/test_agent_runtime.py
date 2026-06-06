"""Tests for provider-agnostic agent tool loop."""
from __future__ import annotations

import json

from app.opar.agent_runtime import (
    ScriptedTransport,
    ToolDefinition,
    make_tool_call,
    run_tool_loop,
)


def test_tool_loop_runs_dispatch_and_completes() -> None:
    calls_log: list[str] = []

    def dispatch(call):
        calls_log.append(call.name)
        return {"skill": call.name, "args": call.arguments}

    transport = ScriptedTransport([
        (None, [make_tool_call("find_skills", {"query": "benchmark spend"})]),
        (None, [make_tool_call("run_skill", {"name": "spend-profiler"})]),
        ("Analysis complete.", []),
    ])

    result = run_tool_loop(
        system="test",
        messages=[{"role": "user", "content": "benchmark my IT spend"}],
        tools=[
            ToolDefinition(
                name="find_skills",
                description="find",
                input_schema={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
            ),
            ToolDefinition(
                name="run_skill",
                description="run",
                input_schema={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
            ),
        ],
        dispatch=dispatch,
        transport=transport,
        thinking=False,
        max_iters=5,
    )

    assert result.final_text == "Analysis complete."
    assert result.stopped_reason == "no_tool_calls"
    assert calls_log == ["find_skills", "run_skill"]
    assert len(result.steps) == 2


def test_tool_loop_caches_identical_calls() -> None:
    counter = {"n": 0}

    def dispatch(call):
        counter["n"] += 1
        return {"ok": True}

    transport = ScriptedTransport([
        (None, [make_tool_call("query_spend", {}), make_tool_call("query_spend", {})]),
        ("done", []),
    ])

    run_tool_loop(
        system="test",
        messages=[{"role": "user", "content": "spend?"}],
        tools=[
            ToolDefinition(name="query_spend", description="q", input_schema={"type": "object", "properties": {}}),
        ],
        dispatch=dispatch,
        transport=transport,
        max_iters=3,
    )
    assert counter["n"] == 1


def test_tool_loop_handles_dispatch_error() -> None:
    def dispatch(call):
        raise RuntimeError("boom")

    transport = ScriptedTransport([
        (None, [make_tool_call("run_skill", {"name": "x"})]),
        ("recovered", []),
    ])

    result = run_tool_loop(
        system="test",
        messages=[{"role": "user", "content": "go"}],
        tools=[
            ToolDefinition(
                name="run_skill",
                description="run",
                input_schema={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
            ),
        ],
        dispatch=dispatch,
        transport=transport,
        max_iters=3,
    )
    assert result.steps[0].tool_results[0]["ok"] is False
    assert "boom" in result.steps[0].tool_results[0]["error"]
