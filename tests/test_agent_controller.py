"""Tests for agent controller with mocked transport."""
from __future__ import annotations

from unittest.mock import patch

from app.opar.agent_controller import run_agent_controller
from app.opar.agent_runtime import ScriptedTransport, make_tool_call
from app.opar.models import ObserveContext


def test_agent_controller_runs_skills_via_tools() -> None:
    ctx = ObserveContext(
        user_message="Benchmark my IT spend",
        session_id="agent-ctrl-1",
        has_tabular_spend=True,
        intent_class="benchmark",
    )
    transport = ScriptedTransport([
        (None, [make_tool_call("run_skill", {"name": "spend-profiler"})]),
        ("IT spend is elevated vs peers.", []),
    ])

    with patch("app.opar.agent_controller.agent_loop_available", return_value=True):
        with patch("app.opar.act._load_session_data") as load:
            from app.models import NormalizedSpendLine

            load.return_value = (
                [
                    NormalizedSpendLine(
                        row_id=1,
                        supplier="Oracle",
                        description="License",
                        amount=500_000.0,
                        category_id="IT_TECH",
                        category_name="IT & Technology",
                    )
                ],
                [],
                {"industry": "tech", "annual_revenue": 10_000_000.0, "currency": "USD"},
            )
            result = run_agent_controller(ctx, transport=transport)

    assert result.success is True
    assert result.act_result is not None
    assert "spend-profiler" in result.act_result.skill_outputs
    assert result.agent_summary == "IT spend is elevated vs peers."
