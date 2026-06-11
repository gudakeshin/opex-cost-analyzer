"""Tests for agent controller with mocked transport."""
from __future__ import annotations

from unittest.mock import MagicMock, call, patch

from app.opar.agent_controller import _BC_REQUIRED_SKILLS, run_agent_controller, try_agent_run
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


def _make_spend_load():
    from app.models import NormalizedSpendLine

    return (
        [
            NormalizedSpendLine(
                row_id=1,
                supplier="Acme",
                description="Services",
                amount=1_000_000.0,
                category_id="IT_TECH",
                category_name="IT & Technology",
            )
        ],
        [],
        {"industry": "tech", "annual_revenue": 50_000_000.0, "currency": "INR"},
    )


def test_bc_backstop_fills_missing_required_skills() -> None:
    """When business_case agent run misses required closure skills, backstop runs them."""
    ctx = ObserveContext(
        user_message="Build a business case",
        session_id="bc-backstop-1",
        has_tabular_spend=True,
        intent_class="business_case",
    )
    # Agent only runs spend-profiler; backstop must add the rest
    transport = ScriptedTransport([
        (None, [make_tool_call("run_skill", {"name": "spend-profiler"})]),
        ("Business case assembled.", []),
    ])

    with patch("app.opar.agent_controller.agent_loop_available", return_value=True):
        with patch("app.opar.act._load_session_data", return_value=_make_spend_load()):
            result = run_agent_controller(ctx, transport=transport)

    assert result.success is True
    assert result.backstop_skills is not None
    # savings-modeler, value-bridge-calculator, business-case-builder not run by agent
    for required in _BC_REQUIRED_SKILLS:
        if required != "spend-profiler":
            assert required in result.backstop_skills or required in (result.act_result.skill_outputs if result.act_result else {})


def test_bc_backstop_skips_already_run_skills() -> None:
    """If agent ran all required skills, backstop should not double-invoke any."""
    ctx = ObserveContext(
        user_message="Build a business case",
        session_id="bc-backstop-2",
        has_tabular_spend=True,
        intent_class="business_case",
    )
    # Agent invokes all four required skills
    tool_calls = [make_tool_call("run_skill", {"name": sk}) for sk in _BC_REQUIRED_SKILLS]
    transport = ScriptedTransport([
        (None, tool_calls),
        ("Full business case complete.", []),
    ])

    with patch("app.opar.agent_controller.agent_loop_available", return_value=True):
        with patch("app.opar.act._load_session_data", return_value=_make_spend_load()):
            result = run_agent_controller(ctx, transport=transport)

    assert result.success is True
    # backstop should not have run any skills (all were already in skill_outputs)
    assert not result.backstop_skills


def test_try_agent_run_returns_result_on_failure() -> None:
    """try_agent_run must return the failed result (not None) so fallback_reason is preserved."""
    ctx = ObserveContext(
        user_message="Business case",
        session_id="bc-fail-1",
        intent_class="business_case",
    )
    with patch("app.opar.agent_controller.agent_loop_available", return_value=False):
        result = try_agent_run(ctx)

    assert result is not None
    assert result.success is False
    assert result.fallback_reason == "agent_loop_unavailable"


def test_plan_preview_returns_agentic_mode_for_bc() -> None:
    """run_opar_plan_preview returns execution_mode='agentic' when agent path is active.

    Patches observe() so the HITL gate (missing spend data) doesn't fire,
    and patches _should_use_agent_path to force the agentic branch.
    """
    from app.opar.models import ObserveContext
    from app.opar.orchestrator import run_opar_plan_preview

    fake_ctx = ObserveContext(
        user_message="Create a business case for my spend",
        session_id="preview-bc-1",
        intent_class="business_case",
        has_tabular_spend=True,
        spend_profile_ready=True,
        clarification_required=False,
    )

    with patch("app.opar.orchestrator.observe", return_value=fake_ctx), \
         patch("app.opar.orchestrator._should_use_agent_path", return_value=True), \
         patch("app.skills.discovery.discover_relevant_skills", return_value=[
             {"name": "spend-profiler"}, {"name": "savings-modeler"},
         ]):
        preview = run_opar_plan_preview(
            "Create a business case for my spend",
            "preview-bc-1",
            "test_user",
        )

    assert preview.get("execution_mode") == "agentic", f"got: {preview.get('execution_mode')}"
    assert "planned_skills" in preview
    summary = preview.get("user_summary", "").lower()
    assert "adaptive" in summary or "agent" in summary
