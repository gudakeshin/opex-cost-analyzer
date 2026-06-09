"""Smoke-style integration tests for OPAR agent and advisory paths."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.opar.agent_controller import AgentRunResult
from app.opar.models import ActResult, ExecutionPlan, ObserveContext, ReflectOutput, SkillTask
from app.opar.orchestrator import run_opar_loop
from app.opar.reflect_advisory import generate_llm_advisory_sections
from app.routers._shared import write_manifest


def _minimal_value_bridge_outputs() -> dict:
    return {
        "spend-profiler": {
            "total_spend": 1_000_000,
            "category_profile": [{"category_id": "IT", "category_name": "IT & Technology", "spend": 600_000}],
        },
        "value-bridge-calculator": {
            "confidence_bands": {"low": 50_000, "mid": 100_000, "high": 150_000},
            "value_matrix": [
                {
                    "category_id": "IT",
                    "category_name": "IT & Technology",
                    "deduped_mid_savings": 80_000,
                    "net_npv": 200_000,
                    "payback_months": 8,
                    "confidence": "high",
                    "lever": "supplier_consolidation",
                }
            ],
        },
    }


@pytest.mark.asyncio
async def test_orchestrator_agent_path_sets_response_metadata(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.opar.orchestrator.UPLOAD_DIR", tmp_path)
    session_id = str(uuid.uuid4())
    (tmp_path / session_id).mkdir(parents=True)
    write_manifest(
        session_id,
        {
            "session_id": session_id,
            "files": [{"name": "spend.csv", "path": str(tmp_path / session_id / "spend.csv")}],
            "industry": "technology",
            "annual_revenue": 1_000_000_000,
            "currency": "INR",
        },
    )

    act_result = ActResult(
        skill_outputs=_minimal_value_bridge_outputs(),
        duration_ms=120.0,
    )
    exec_plan = ExecutionPlan(
        tasks=[SkillTask(skill_name="spend-profiler", inputs={}), SkillTask(skill_name="value-bridge-calculator", inputs={})],
        total_skills=2,
        parallel_groups=1,
        user_summary="Agent investigation complete.",
    )
    agent_result = AgentRunResult(
        success=True,
        act_result=act_result,
        exec_plan=exec_plan,
        agent_summary="IT spend shows consolidation upside.",
        agent_trace=[{"tool": "run_skill", "arguments": {"name": "spend-profiler"}, "ok": True}],
    )

    with patch("app.opar.orchestrator._should_use_agent_path", return_value=True), patch(
        "app.opar.agent_controller.try_agent_run", return_value=agent_result
    ), patch("app.opar.orchestrator.observe") as mock_observe:
        mock_observe.return_value = ObserveContext(
            user_message="Benchmark my IT spend",
            session_id=session_id,
            user_id="smoke-user",
            intent_class="benchmark",
            has_tabular_spend=True,
        )
        result = await run_opar_loop("Benchmark my IT spend", session_id, "smoke-user")

    assert result.response_metadata.get("agent_path") is True
    assert result.response_metadata.get("agent_summary") == "IT spend shows consolidation upside."
    assert result.response_metadata.get("agent_trace")
    assert "value-bridge-calculator" in str(result.response_text) or "IT" in result.response_text


def test_gemini_advisory_smoke_mocked() -> None:
    """Advisory quality gate with mocked Gemini synthesizer (no live API)."""
    ctx = ObserveContext(user_message="value bridge for IT", intent_class="value_bridge")
    validated = _minimal_value_bridge_outputs()
    raw = {
        "executive_takeaway": "IT category shows the largest modeled savings pool with supplier consolidation as the primary lever.",
        "category_focus_section": "",
        "quick_wins_from_data": ["Renegotiate top cloud vendor", "Consolidate SaaS subscriptions"],
        "business_levers": [
            {
                "lever_name": "Supplier consolidation",
                "what_changes": "Reduce vendor count from 12 to 5 strategic partners",
                "why_it_works": "Volume concentration unlocks tiered pricing",
                "evidence": ["Top 3 vendors are 68% of spend", "Peer median is 4 vendors"],
            },
            {
                "lever_name": "Contract renegotiation",
                "what_changes": "Reset maintenance uplift at renewal",
                "why_it_works": "Benchmark gap is contract-driven not usage-driven",
                "evidence": ["Gap vs P75 is 2.1 pts of revenue", "Largest vendor is 31% of category"],
            },
            {
                "lever_name": "Maverick compliance",
                "what_changes": "Route card spend through approved PO workflow",
                "why_it_works": "Off-contract buying inflates unit cost materially",
                "evidence": ["Express-like lines are 14% of category", "Policy exists but is not enforced"],
            },
        ],
        "executive_callouts": ["IT is 0.7 pts above peer P50"],
        "priority_actions_30_60_90": [],
        "sme_qualification_narrative": "",
    }
    mock_synth = MagicMock(return_value=(raw, None))
    with patch("app.opar.reflect_advisory.GEMINI_ENABLED", True), patch(
        "app.opar.reflect_advisory.resolve_analysis_synthesizer", return_value=mock_synth
    ):
        advisory, thinking, _skip = generate_llm_advisory_sections(ctx, {"currency": "INR"}, validated)
    assert advisory is not None
    assert thinking is None
    mock_synth.assert_called()


@pytest.mark.smoke
@pytest.mark.asyncio
async def test_value_bridge_chat_reflect_path(tmp_path, monkeypatch) -> None:
    """Deterministic value-bridge reflect path through plan→act→reflect."""
    monkeypatch.setattr("app.opar.orchestrator.UPLOAD_DIR", tmp_path)
    session_id = str(uuid.uuid4())
    (tmp_path / session_id).mkdir(parents=True)
    write_manifest(
        session_id,
        {
            "session_id": session_id,
            "files": [],
            "industry": "technology",
            "annual_revenue": 1_000_000_000,
            "currency": "INR",
        },
    )

    act_result = ActResult(skill_outputs=_minimal_value_bridge_outputs(), duration_ms=50.0)
    exec_plan = ExecutionPlan(
        tasks=[SkillTask(skill_name="value-bridge-calculator", inputs={})],
        total_skills=1,
        parallel_groups=1,
        user_summary="Value bridge analysis.",
    )

    with patch("app.opar.orchestrator._should_use_agent_path", return_value=False), patch(
        "app.opar.orchestrator.plan", return_value=exec_plan
    ), patch("app.opar.orchestrator.act", new_callable=AsyncMock, return_value=act_result), patch(
        "app.opar.orchestrator.observe"
    ) as mock_observe:
        mock_observe.return_value = ObserveContext(
            user_message="Calculate value bridge",
            session_id=session_id,
            user_id="smoke-user",
            intent_class="value_bridge",
            has_tabular_spend=True,
        )
        result = await run_opar_loop("Calculate value bridge", session_id, "smoke-user")

    assert "Value bridge" in result.response_text or "Top Recommendations" in result.response_text
    assert result.response_metadata.get("agent_path") is not True
