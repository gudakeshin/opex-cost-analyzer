"""Tests for LLM numeric provenance tagging."""
from __future__ import annotations

from app.opar.numeric_provenance import apply_bounded_adjustment, tag_deterministic, tag_llm_numeric


def test_tag_deterministic_anchor() -> None:
    tagged = tag_deterministic(100_000.0, field="mid_case_savings")
    assert tagged["source"] == "deterministic"
    assert tagged["value"] == 100_000.0
    assert tagged["deterministic_anchor"] == 100_000.0


def test_tag_llm_numeric_within_bound() -> None:
    tagged = tag_llm_numeric(
        110_000.0,
        field="mid_case_savings",
        deterministic_anchor=100_000.0,
        rationale="Contract renewal window supports higher addressability.",
    )
    assert tagged["source"] == "llm_estimate"
    assert tagged["within_bound"] is True


def test_apply_bounded_adjustment_clamps() -> None:
    tagged = apply_bounded_adjustment(
        100_000.0,
        200_000.0,
        field="mid_case_savings",
        rationale="Aggressive estimate",
    )
    assert tagged["value"] <= 125_000.0
    assert tagged["source"] == "llm_estimate"
    assert "clamped" in tagged["rationale"].lower()
