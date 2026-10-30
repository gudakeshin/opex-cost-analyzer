"""Tests for select_relevant_outputs — relevance-filtered synthesis context.

Validates that query_capabilities correctly filter which skill outputs enter
the LLM synthesis prompt, with conservative bypasses for deliverable intents
and agent-path turns, and that excluded skills are exposed as an
available_analyses manifest rather than silently dropped.
"""
from __future__ import annotations

import pytest

from app.opar.models import ObserveContext
from app.opar.reflect_advisory import (
    _CAPABILITY_SKILL_MAP,
    _CORE_SYNTHESIS_SKILLS,
    _DELIVERABLE_INTENTS,
    _manifest_headline,
    select_relevant_outputs,
)


# ── fixtures ─────────────────────────────────────────────────────────────────


def _ctx(**kwargs) -> ObserveContext:
    defaults: dict = {"user_message": "test", "intent_class": "general_qa"}
    defaults.update(kwargs)
    return ObserveContext(**defaults)


def _validated(*skill_names: str) -> dict:
    """Minimal validated outputs keyed by skill name."""
    return {name: {"_test": True} for name in skill_names}


# ── core-set always present ───────────────────────────────────────────────────


def test_core_skills_always_included_when_filtering() -> None:
    """Core skills must survive relevance filtering regardless of capabilities."""
    ctx = _ctx(query_capabilities=["temporal_trend"])
    validated = _validated(
        "spend-profiler",
        "savings-modeler",
        "value-bridge-calculator",
        "sme-critique",
        "evidence-gatherer",
        "temporal-analyzer",
        "bva-analyzer",   # should be excluded — not in temporal_trend map
    )
    selected, excluded = select_relevant_outputs(ctx, validated)
    for core in _CORE_SYNTHESIS_SKILLS:
        assert core in selected, f"core skill {core} was excluded"
    assert "temporal-analyzer" in selected
    assert "bva-analyzer" not in selected
    assert any(e["skill"] == "bva-analyzer" for e in excluded)


def test_capability_mapping_benchmarking() -> None:
    ctx = _ctx(query_capabilities=["benchmarking"])
    validated = _validated(
        "spend-profiler",
        "peer-benchmarker",
        "internal-benchmarker",
        "temporal-analyzer",  # irrelevant — should be excluded
    )
    selected, excluded = select_relevant_outputs(ctx, validated)
    assert "peer-benchmarker" in selected
    assert "internal-benchmarker" in selected
    assert "temporal-analyzer" not in selected
    assert any(e["skill"] == "temporal-analyzer" for e in excluded)


def test_capability_mapping_variance_analysis() -> None:
    ctx = _ctx(query_capabilities=["variance_analysis"])
    validated = _validated("spend-profiler", "bva-analyzer", "peer-benchmarker")
    selected, excluded = select_relevant_outputs(ctx, validated)
    assert "bva-analyzer" in selected
    assert "peer-benchmarker" not in selected


def test_capability_mapping_working_capital() -> None:
    ctx = _ctx(query_capabilities=["working_capital"])
    validated = _validated(
        "spend-profiler",
        "payment-terms-optimizer",
        "indian-tax-optimizer",
        "peer-benchmarker",
    )
    selected, excluded = select_relevant_outputs(ctx, validated)
    assert "payment-terms-optimizer" in selected
    assert "indian-tax-optimizer" in selected
    assert "peer-benchmarker" not in selected


def test_explicit_category_adds_root_cause() -> None:
    """When a category is targeted, root-cause-analyzer should always enter context."""
    ctx = _ctx(
        query_capabilities=["temporal_trend"],
        explicit_category="IT & Technology",
    )
    validated = _validated("spend-profiler", "temporal-analyzer", "root-cause-analyzer")
    selected, _ = select_relevant_outputs(ctx, validated)
    assert "root-cause-analyzer" in selected


def test_no_explicit_category_root_cause_excluded() -> None:
    ctx = _ctx(query_capabilities=["temporal_trend"], explicit_category=None)
    validated = _validated("spend-profiler", "temporal-analyzer", "root-cause-analyzer")
    selected, excluded = select_relevant_outputs(ctx, validated)
    assert "root-cause-analyzer" not in selected
    assert any(e["skill"] == "root-cause-analyzer" for e in excluded)


def test_multiple_capabilities_union() -> None:
    """Multiple capabilities should union their skill sets."""
    ctx = _ctx(query_capabilities=["temporal_trend", "benchmarking"])
    validated = _validated(
        "spend-profiler",
        "temporal-analyzer",
        "peer-benchmarker",
        "bva-analyzer",  # only in variance_analysis — should be excluded
    )
    selected, excluded = select_relevant_outputs(ctx, validated)
    assert "temporal-analyzer" in selected
    assert "peer-benchmarker" in selected
    assert "bva-analyzer" not in selected


# ── bypass conditions ─────────────────────────────────────────────────────────


def test_deliverable_intent_business_case_bypasses_filter() -> None:
    """business_case is a deliverable — full context must pass through."""
    ctx = _ctx(intent_class="business_case", query_capabilities=["temporal_trend"])
    validated = _validated(
        "spend-profiler", "temporal-analyzer", "bva-analyzer", "peer-benchmarker"
    )
    selected, excluded = select_relevant_outputs(ctx, validated)
    assert set(selected) == set(validated)
    assert excluded == []


def test_deliverable_intent_export_business_case_bypasses() -> None:
    ctx = _ctx(intent_class="export_business_case", query_capabilities=["benchmarking"])
    validated = _validated("spend-profiler", "bva-analyzer", "temporal-analyzer")
    selected, excluded = select_relevant_outputs(ctx, validated)
    assert set(selected) == set(validated)
    assert excluded == []


def test_empty_capabilities_bypasses_filter() -> None:
    """Unknown or empty capabilities — include everything (conservative)."""
    ctx = _ctx(query_capabilities=[])
    validated = _validated("spend-profiler", "bva-analyzer", "temporal-analyzer")
    selected, excluded = select_relevant_outputs(ctx, validated)
    assert set(selected) == set(validated)
    assert excluded == []


def test_unknown_capability_values_ignored() -> None:
    """Unrecognised capability strings should be silently ignored (full bypass)."""
    ctx = _ctx(query_capabilities=["made_up_capability"])
    validated = _validated("spend-profiler", "bva-analyzer")
    selected, excluded = select_relevant_outputs(ctx, validated)
    assert set(selected) == set(validated)
    assert excluded == []


def test_agent_path_bypasses_filter() -> None:
    """Agent tool-loop already selected skills progressively — don't re-filter."""
    ctx = _ctx(intent_class="benchmark", query_capabilities=["benchmarking"])
    validated = _validated(
        "spend-profiler", "bva-analyzer", "temporal-analyzer", "peer-benchmarker"
    )
    selected, excluded = select_relevant_outputs(ctx, validated, agent_path=True)
    assert set(selected) == set(validated)
    assert excluded == []


# ── available_analyses manifest ───────────────────────────────────────────────


def test_excluded_skills_appear_in_manifest() -> None:
    ctx = _ctx(query_capabilities=["temporal_trend"])
    validated = {
        "spend-profiler": {"_test": True},
        "temporal-analyzer": {"period_trends": [1, 2, 3]},
        "bva-analyzer": {"variances": [{"cat": "IT"}, {"cat": "HR"}]},
    }
    selected, excluded = select_relevant_outputs(ctx, validated)
    assert len(excluded) == 1
    entry = excluded[0]
    assert entry["skill"] == "bva-analyzer"
    assert "headline" in entry
    assert entry["headline"]  # non-empty


def test_manifest_headline_temporal() -> None:
    output = {"period_trends": [1, 2, 3, 4, 5, 6]}
    h = _manifest_headline("temporal-analyzer", output)
    assert "6" in h
    assert "period" in h.lower()


def test_manifest_headline_bva() -> None:
    output = {"variances": [{"cat": "IT"}, {"cat": "HR"}, {"cat": "Mktg"}]}
    h = _manifest_headline("bva-analyzer", output)
    assert "3" in h


def test_manifest_headline_empty_output() -> None:
    h = _manifest_headline("some-skill", "not a dict")
    assert h == "output available"


def test_manifest_headline_generic_list_fallback() -> None:
    output = {"opportunities": [{"x": 1}, {"x": 2}]}
    h = _manifest_headline("unknown-skill", output)
    assert "2" in h
    assert "opportunities" in h


# ── skip_skills not surfaced in manifest ──────────────────────────────────────


def test_skip_skills_not_in_manifest() -> None:
    """Internal routing skills (_SKIP_SKILLS) must not appear in available_analyses."""
    from app.opar.claude_client import _SKIP_SKILLS

    ctx = _ctx(query_capabilities=["temporal_trend"])
    skip_skill = next(iter(_SKIP_SKILLS)) if _SKIP_SKILLS else None
    if skip_skill is None:
        pytest.skip("_SKIP_SKILLS is empty")
    validated = _validated("spend-profiler", "temporal-analyzer", skip_skill)
    _, excluded = select_relevant_outputs(ctx, validated)
    assert not any(e["skill"] == skip_skill for e in excluded)


# ── determinism ───────────────────────────────────────────────────────────────


def test_select_is_deterministic_for_same_inputs() -> None:
    ctx = _ctx(query_capabilities=["benchmarking", "temporal_trend"])
    validated = _validated(
        "spend-profiler", "peer-benchmarker", "temporal-analyzer",
        "bva-analyzer", "payment-terms-optimizer",
    )
    s1, e1 = select_relevant_outputs(ctx, validated)
    s2, e2 = select_relevant_outputs(ctx, validated)
    assert set(s1) == set(s2)
    assert {e["skill"] for e in e1} == {e["skill"] for e in e2}
