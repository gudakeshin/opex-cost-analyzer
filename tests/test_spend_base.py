"""Tests for unified spend-base loading and refresh."""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from app.memory import MemoryStore
from app.models import NormalizedSpendLine
from app.opar.models import ActResult, ExecutionPlan, ObserveContext, SkillTask
from app.opar.reflect import reflect
from app.services.spend_base import (
    assert_spend_base_consistent,
    load_authoritative_spend_lines,
    refresh_spend_base,
    session_has_line_adjustments,
)


def _line(
    *,
    amount: float = 1_000_000,
    supplier: str = "CloudCo",
    eliminated: bool = False,
    row_id: int = 1,
) -> NormalizedSpendLine:
    return NormalizedSpendLine(
        row_id=row_id,
        supplier=supplier,
        description="Cloud platform services",
        amount=amount,
        category_id="IT_SOFTWARE",
        category_name="IT Software & Licenses",
        consolidation_eliminated=eliminated,
    )


def test_session_has_line_adjustments() -> None:
    assert not session_has_line_adjustments([_line()])
    assert session_has_line_adjustments([_line(eliminated=True)])


def test_load_authoritative_prefers_session_with_adjustments() -> None:
    session_id = str(uuid.uuid4())
    adjusted = [_line(amount=500_000), _line(amount=300_000, row_id=2, eliminated=True)]
    MemoryStore().put(
        "session",
        session_id,
        {
            "session_id": session_id,
            "normalized_spend": [l.model_dump(mode="json") for l in adjusted],
            "conflict_user_actions": {"fp1": {"status": "applied"}},
        },
    )

    with patch("app.services.engagement_corpus.load_analysis_corpus") as load_corpus:
        load_corpus.return_value = (
            [_line(amount=800_000), _line(amount=300_000, row_id=2)],
            [],
            [],
            [],
            {"session_id": session_id},
        )
        lines, _, manifest = load_authoritative_spend_lines(session_id)

    assert len(lines) == 2
    assert lines[1].consolidation_eliminated is True
    assert manifest.get("conflict_user_actions") == {"fp1": {"status": "applied"}}


def test_refresh_spend_base_increments_revision_and_matches_lines() -> None:
    session_id = str(uuid.uuid4())
    lines = [_line(amount=600_000), _line(amount=400_000, row_id=2, eliminated=True)]
    existing = {
        "session_id": session_id,
        "spend_base_revision": 2,
        "normalized_spend": [l.model_dump(mode="json") for l in lines],
        "skill_outputs": {"spend-profiler": {"total_spend": 1_000_000, "category_profile": []}},
    }
    MemoryStore().put("session", session_id, existing)

    impact = refresh_spend_base(session_id, reason="test", lines=lines, existing=existing)

    saved = MemoryStore().get("session", session_id)
    assert impact["spend_base_revision"] == 3
    assert saved["spend_base_revision"] == 3
    assert impact["new_total_spend"] == 600_000
    assert impact["spend_delta"] == -400_000
    assert_spend_base_consistent(saved)


def test_reflect_repair_preserves_reduced_spend_after_stale_profiler() -> None:
    """Chat turn with raw-corpus profiler output must not inflate spend after conflict fix."""
    session_id = str(uuid.uuid4())
    adjusted_lines = [_line(amount=700_000), _line(amount=300_000, row_id=2, eliminated=True)]
    existing = {
        "session_id": session_id,
        "spend_base_revision": 1,
        "normalized_spend": [l.model_dump(mode="json") for l in adjusted_lines],
        "skill_outputs": {
            "spend-profiler": {"total_spend": 700_000, "category_profile": []},
            "peer-benchmarker": {"comparisons": []},
        },
    }
    MemoryStore().put("session", session_id, existing)

    reflect(
        ActResult(skill_outputs={"spend-profiler": {"total_spend": 1_000_000, "category_profile": []}}, errors={}),
        ExecutionPlan(tasks=[SkillTask(skill_name="spend-profiler")]),
        ObserveContext(
            user_message="what is my total spend?",
            intent_class="general_qa",
            session_id=session_id,
            user_id="user-1",
        ),
    )

    saved = MemoryStore().get("session", session_id)
    assert float(saved["skill_outputs"]["spend-profiler"]["total_spend"]) == 700_000
    assert_spend_base_consistent(saved)


def test_assert_spend_base_consistent_raises_on_drift() -> None:
    lines = [_line(amount=500_000)]
    session = {
        "normalized_spend": [l.model_dump(mode="json") for l in lines],
        "skill_outputs": {"spend-profiler": {"total_spend": 999_000}},
    }
    with pytest.raises(AssertionError):
        assert_spend_base_consistent(session)
