from __future__ import annotations

import uuid

from app.memory import MemoryStore
from app.models import NormalizedSpendLine
from app.opar.models import ActResult, ExecutionPlan, ObserveContext, SkillTask
from app.opar.plan import plan
from app.opar.reflect import reflect
from app.skills.dispatch import SkillContext, invoke_skill, registered_skills


def _line() -> NormalizedSpendLine:
    return NormalizedSpendLine(
        row_id=1,
        supplier="CloudCo",
        description="Cloud platform services",
        amount=1_000_000,
        category_id="IT_SOFTWARE",
        category_name="IT Software & Licenses",
    )


def test_savings_modeler_dispatch_uses_rich_context(monkeypatch) -> None:
    captured = {}

    def fake_savings_modeler(value_bridge_raw, root_cause_outputs, **kwargs):
        captured["value_bridge_raw"] = value_bridge_raw
        captured["root_cause_outputs"] = root_cause_outputs
        captured["kwargs"] = kwargs
        return {"initiatives": [{"category_id": "IT_SOFTWARE"}]}

    monkeypatch.setattr("app.skills.dispatch._engine.savings_modeler", fake_savings_modeler)

    ctx = SkillContext(
        lines=[_line()],
        docs_text=["contract limits cloud migration timing"],
        manifest={
            "industry": "technology",
            "annual_revenue": 50_000_000,
            "wacc": 0.13,
            "effective_tax_rate": 0.22,
        },
        prior_results={
            "spend-profiler": {"total_spend": 1_000_000, "category_profile": []},
            "document-contextualizer": {"constraints": ["contract limit"]},
            "peer-benchmarker": {"comparisons": []},
            "internal-benchmarker": {},
            "heuristic-analyzer": {},
            "root-cause-analyzer": {"root_cause_findings": []},
        },
        headcount=25,
        reporting_currency="INR",
    )

    out, degraded = invoke_skill("savings-modeler", ctx)

    assert degraded is None
    assert out["initiatives"]
    assert captured["kwargs"]["discount_rate"] == 0.13
    assert captured["kwargs"]["effective_tax_rate"] == 0.22
    assert captured["kwargs"]["industry"] == "technology"
    assert captured["kwargs"]["headcount"] == 25
    assert captured["kwargs"]["annual_revenue"] == 50_000_000
    assert captured["kwargs"]["document_context"] == {"constraints": ["contract limit"]}
    assert captured["kwargs"]["spend_lines"] == [_line()]


def test_sme_critique_is_registered() -> None:
    assert "sme-critique" in registered_skills()
    assert "evidence-gatherer" in registered_skills()


def test_value_modeled_plan_includes_sme_critique() -> None:
    exec_plan = plan(
        ObserveContext(
            user_message="calculate value at the table",
            intent_class="value_bridge",
            has_tabular_spend=True,
            spend_profile_ready=True,
            has_annual_revenue=True,
            data_quality_score=0.9,
            query_capabilities=["value_modeling", "root_cause"],
        )
    )

    skills = [task.skill_name for task in exec_plan.tasks]
    assert "savings-modeler" in skills
    assert "evidence-gatherer" in skills
    assert "sme-critique" in skills
    assert skills.index("evidence-gatherer") < skills.index("sme-critique")


def test_reflect_preserves_full_session_state_when_merging_chat_outputs() -> None:
    session_id = str(uuid.uuid4())
    existing = {
        "session_id": session_id,
        "company_name": "Test Co",
        "industry": "technology",
        "annual_revenue": 10_000_000,
        "reporting_currency": "INR",
        "normalized_spend": [_line().model_dump(mode="json")],
        "analysis_trace": [{"step": 1, "title": "Read spend data"}],
        "skill_outputs": {"peer-benchmarker": {"comparisons": []}},
    }
    MemoryStore().put("session", session_id, existing)

    reflect(
        ActResult(skill_outputs={"spend-profiler": {"total_spend": 1_000_000}}, errors={}),
        ExecutionPlan(tasks=[SkillTask(skill_name="spend-profiler")]),
        ObserveContext(
            user_message="what is my spend?",
            intent_class="general_qa",
            session_id=session_id,
            user_id="user-1",
        ),
    )

    saved = MemoryStore().get("session", session_id)
    assert saved["normalized_spend"] == existing["normalized_spend"]
    assert saved["analysis_trace"] == existing["analysis_trace"]
    assert saved["skill_outputs"]["peer-benchmarker"] == {"comparisons": []}
    assert saved["skill_outputs"]["spend-profiler"] == {"total_spend": 1_000_000}
    assert saved["last_run_intent"] == "general_qa"


def test_reflect_populates_spend_and_trace_for_chat_only_session() -> None:
    """Chat-only session (no prior /api/analyze) gains normalized_spend + a trace
    from the turn's ActResult, matching the batch SessionAnalysisState shape."""
    session_id = str(uuid.uuid4())  # no prior snapshot in memory
    reflect(
        ActResult(
            skill_outputs={
                "spend-profiler": {"total_spend": 1_000_000, "category_profile": [{"category_id": "IT", "spend": 1_000_000}]},
            },
            errors={},
            normalized_spend=[_line()],
        ),
        ExecutionPlan(tasks=[SkillTask(skill_name="spend-profiler")]),
        ObserveContext(
            user_message="what is my spend?",
            intent_class="general_qa",
            session_id=session_id,
            user_id="user-1",
        ),
    )

    saved = MemoryStore().get("session", session_id)
    assert saved["normalized_spend"] == [_line().model_dump(mode="json")]
    assert saved["analysis_trace"], "expected a non-empty lightweight trace for chat-only session"
    assert saved["analysis_trace"][0]["phase"] == "ingest"
    assert saved["skills_run_this_turn"] == ["spend-profiler"]
    assert saved["updated_at"]


def test_reflect_surfaces_replanner_log_for_value_quality_gap() -> None:
    session_id = str(uuid.uuid4())
    out = reflect(
        ActResult(skill_outputs={"spend-profiler": {"total_spend": 1_000_000}}, errors={}),
        ExecutionPlan(
            tasks=[
                SkillTask(skill_name="spend-profiler"),
                SkillTask(skill_name="peer-benchmarker"),
                SkillTask(skill_name="savings-modeler"),
            ]
        ),
        ObserveContext(
            user_message="calculate value bridge",
            intent_class="value_bridge",
            session_id=session_id,
            user_id="user-1",
            has_tabular_spend=True,
        ),
    )

    assert out.replanner_log
