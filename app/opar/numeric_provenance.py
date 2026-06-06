"""Provenance tagging for LLM-adjusted financial figures.

Deterministic skill outputs remain the audit anchor; LLM adjustments carry
``source``, ``deterministic_anchor``, and ``rationale`` for CFO traceability.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from app.config import AGENT_LLM_NUMERIC_ADJUSTMENT_PCT
from app.services.audit_log import append_event


def tag_llm_numeric(
    value: float,
    *,
    field: str,
    deterministic_anchor: float,
    rationale: str,
    category_id: str | None = None,
    lever: str | None = None,
) -> Dict[str, Any]:
    """Wrap an LLM-adjusted number with provenance metadata."""
    pct_delta = 0.0
    if deterministic_anchor:
        pct_delta = abs(value - deterministic_anchor) / abs(deterministic_anchor)
    bounded = pct_delta <= AGENT_LLM_NUMERIC_ADJUSTMENT_PCT
    return {
        "value": value,
        "source": "llm_estimate",
        "deterministic_anchor": deterministic_anchor,
        "rationale": rationale,
        "field": field,
        "category_id": category_id,
        "lever": lever,
        "within_bound": bounded,
        "pct_delta_from_anchor": round(pct_delta, 4),
    }


def tag_deterministic(value: float, *, field: str) -> Dict[str, Any]:
    return {
        "value": value,
        "source": "deterministic",
        "deterministic_anchor": value,
        "field": field,
    }


def audit_llm_numeric_adjustment(
    *,
    session_id: str,
    engagement_id: Optional[str],
    adjustments: list[Dict[str, Any]],
    context: str = "",
) -> None:
    if not adjustments:
        return
    append_event(
        "llm_numeric_adjustment",
        detail={"adjustments": adjustments, "context": context},
        session_id=session_id,
        engagement_id=engagement_id,
        severity="MEDIUM",
    )


def apply_bounded_adjustment(
    anchor: float,
    proposed: float,
    *,
    field: str,
    rationale: str,
    category_id: str | None = None,
    lever: str | None = None,
) -> Dict[str, Any]:
    """Clamp proposed value to ±AGENT_LLM_NUMERIC_ADJUSTMENT_PCT of anchor."""
    if anchor == 0:
        clamped = proposed
    else:
        lo = anchor * (1 - AGENT_LLM_NUMERIC_ADJUSTMENT_PCT)
        hi = anchor * (1 + AGENT_LLM_NUMERIC_ADJUSTMENT_PCT)
        clamped = max(lo, min(hi, proposed))
    tagged = tag_llm_numeric(
        clamped,
        field=field,
        deterministic_anchor=anchor,
        rationale=rationale,
        category_id=category_id,
        lever=lever,
    )
    if clamped != proposed:
        tagged["rationale"] = f"{rationale} (clamped from {proposed:.2f} to bound ±{AGENT_LLM_NUMERIC_ADJUSTMENT_PCT:.0%})"
    return tagged
