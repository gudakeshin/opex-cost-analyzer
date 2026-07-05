"""Tests for skill taxonomy, quality-gate attachment, output discovery, declarative runtime."""
from __future__ import annotations

from unittest.mock import patch

from app.opar.models import ObserveContext, SkillTask
from app.opar.plan import _attach_discovered_outputs, _attach_quality_gates, _expand
from app.skills.dispatch import SkillContext, _run_declarative_skill
from app.skills.taxonomy import classify_kind, classify_weight


def test_classify_kind_defaults() -> None:
    assert classify_kind("sme-critique") == "quality_gate"
    assert classify_kind("data-quality-gate") == "quality_gate"
    assert classify_kind("pii-stripper") == "security"
    assert classify_kind("document-contextualizer") == "ingestion"
    assert classify_kind("chart-builder") == "output"
    assert classify_kind("spend-profiler") == "analysis"


def test_classify_weight_defaults() -> None:
    assert classify_weight("export-formatter") == "heavy"
    assert classify_weight("analysis-synthesizer") == "light"


def test_attach_quality_gates_data_gate_on_benchmark_only() -> None:
    tasks = _expand(["spend-profiler", "peer-benchmarker", "internal-benchmarker"])
    _attach_quality_gates(tasks)
    names = {t.skill_name for t in tasks}
    assert "data-quality-gate" in names
    assert "sme-critique" not in names


def test_attach_quality_gates_sme_on_value_modeling() -> None:
    selected = [
        "spend-profiler", "peer-benchmarker", "internal-benchmarker",
        "heuristic-analyzer", "root-cause-analyzer", "savings-modeler",
        "value-bridge-calculator",
    ]
    tasks = _expand(selected)
    _attach_quality_gates(tasks)
    names = {t.skill_name for t in tasks}
    assert "data-quality-gate" in names
    assert "evidence-gatherer" in names
    assert "sme-critique" in names


def test_attach_discovered_outputs_heavy_board_deck() -> None:
    tasks = _expand(["spend-profiler", "peer-benchmarker"])
    ctx = ObserveContext(
        user_message="give me a board-ready summary of savings",
        session_id="sess-1",
        intent_class="benchmark",
        wants_executive_narrative=True,
    )
    with patch("app.skills.discovery.discover_relevant_skills", return_value=[]):
        suggestions = _attach_discovered_outputs(tasks, ctx)
    assert any(s.skill == "board-deck" for s in suggestions)
    assert not any(t.skill_name == "export-formatter" for t in tasks)


def test_attach_discovered_outputs_auto_runs_light_output() -> None:
    tasks = _expand(["spend-profiler", "value-bridge-calculator", "data-validator"])
    # intent_class deliberately avoids "value_bridge"/"benchmark"/"general_qa" — those
    # skip analysis-synthesizer/executive-communication because their narratives are
    # composed in reflect, not act-phase synthesis (see _attach_discovered_outputs).
    ctx = ObserveContext(
        user_message="synthesize executive summary for leadership",
        session_id="sess-2",
        intent_class="drill_down",
    )
    fake_hit = [{"name": "analysis-synthesizer", "description": "synth", "score": 0.9}]
    with patch("app.skills.discovery.discover_relevant_skills", return_value=fake_hit):
        suggestions = _attach_discovered_outputs(tasks, ctx)
    names = {t.skill_name for t in tasks}
    assert "analysis-synthesizer" in names
    assert not suggestions


def test_declarative_runtime_degrades_when_provider_down() -> None:
    from app.models import NormalizedSpendLine
    from app.skills.dispatch import _run_declarative_skill

    lines = [
        NormalizedSpendLine(
            row_id=1,
            supplier="Acme",
            description="SaaS",
            amount=1000.0,
            category_id="IT",
            category_name="IT",
        )
    ]
    ctx = SkillContext(
        lines=lines,
        docs_text=[],
        manifest={"company_name": "Test"},
        prior_results={"spend-profiler": {"total_spend": 1000.0}},
        user_message="analyze",
    )
    meta = {
        "name": "test-declarative",
        "runtime": "declarative",
        "inputs": ["spend-profiler"],
        "path": "",
    }
    with patch(
        "app.opar.claude_client.run_declarative_skill_claude_with_meta",
        return_value=(None, "provider_disabled"),
    ):
        out, reason = _run_declarative_skill("test-declarative", ctx, meta)
    assert out == {}
    assert reason == "provider_disabled"
