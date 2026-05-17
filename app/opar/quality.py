"""AssumptionQualityScore — Gate-2 promotion gate for initiative assumptions.

Score components (each 0.0–1.0, weighted equally):
  source_class         — quality of the source behind the assumption
  validation_age       — how recently was the value validated
  owner_sign_off       — whether a named owner approved it
  range_plausibility   — P50 within 2 SD of peer dispersion

Composite score < 0.65 blocks Gate-2 promotion unless a CFO-level override
is recorded.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# --------------------------------------------------------------------------- #
# Source-class weight table                                                     #
# --------------------------------------------------------------------------- #

_SOURCE_CLASS_SCORE: Dict[str, float] = {
    "peer_validated": 1.00,       # published benchmark, confirmed by client
    "internal_validated": 0.90,   # client actuals, sign-off received
    "expert_estimate": 0.70,      # advisor or SME estimate, no client data
    "rule_of_thumb": 0.45,        # generic heuristic (e.g. "10–15% of spend")
    "unknown": 0.25,
}


@dataclass
class AssumptionRecord:
    """Single assumption attached to an initiative."""
    assumption_id: str
    initiative_id: str
    description: str
    source_class: str = "unknown"
    p10: float = 0.0
    p50: float = 0.0
    p90: float = 0.0
    validation_date: Optional[str] = None   # ISO-8601 date string
    owner_name: Optional[str] = None
    owner_sign_off: bool = False
    peer_p50: Optional[float] = None        # peer-sourced midpoint for plausibility check
    peer_std: Optional[float] = None        # peer distribution std-dev


@dataclass
class AssumptionQualityResult:
    """Per-assumption quality breakdown."""
    assumption_id: str
    source_score: float
    age_score: float
    sign_off_score: float
    plausibility_score: float
    composite_score: float
    blocks_gate2: bool
    detail: str


@dataclass
class GateCheckResult:
    """Aggregate Gate-2 check for a full initiative."""
    initiative_id: str
    assumption_scores: List[AssumptionQualityResult]
    mean_composite: float
    gate2_blocked: bool                      # True if mean < 0.65
    override_available: bool = True          # CFO override always available
    override_recorded: bool = False
    override_by: Optional[str] = None
    blocking_assumptions: List[str] = field(default_factory=list)
    narrative: str = ""


def _source_score(source_class: str) -> float:
    return _SOURCE_CLASS_SCORE.get(source_class, _SOURCE_CLASS_SCORE["unknown"])


def _age_score(validation_date: Optional[str], *, reference_date: Optional[datetime] = None) -> float:
    """Score decays from 1.0 (validated today) to 0.2 (validated ≥ 365 days ago)."""
    if not validation_date:
        return 0.20
    try:
        validated = datetime.fromisoformat(validation_date).replace(tzinfo=timezone.utc)
    except ValueError:
        return 0.20
    ref = reference_date or datetime.now(timezone.utc)
    age_days = max(0.0, (ref - validated).total_seconds() / 86400)
    # Linear decay: 0 days → 1.0; 365 days → 0.20
    score = 1.0 - (age_days / 365) * 0.80
    return max(0.20, min(1.0, round(score, 4)))


def _plausibility_score(assumption: AssumptionRecord) -> float:
    """Check P50 is within 2 SD of peer distribution; 1.0 if no peer data."""
    if assumption.peer_p50 is None or assumption.peer_std is None:
        return 0.85  # no peer data — neutral, slightly below full credit
    if assumption.peer_std <= 0:
        # Point estimate — check exact match
        return 1.0 if math.isclose(assumption.p50, assumption.peer_p50, rel_tol=0.1) else 0.40
    z_score = abs(assumption.p50 - assumption.peer_p50) / assumption.peer_std
    if z_score <= 1.0:
        return 1.00
    if z_score <= 2.0:
        return 0.75
    if z_score <= 3.0:
        return 0.45
    return 0.20


def score_assumption(
    assumption: AssumptionRecord,
    *,
    reference_date: Optional[datetime] = None,
) -> AssumptionQualityResult:
    """Compute the quality score for a single assumption."""
    src = _source_score(assumption.source_class)
    age = _age_score(assumption.validation_date, reference_date=reference_date)
    soff = 1.0 if assumption.owner_sign_off else 0.50
    plaus = _plausibility_score(assumption)

    composite = round((src + age + soff + plaus) / 4.0, 4)
    blocks = composite < 0.65

    detail_parts = [
        f"source={src:.2f} ({assumption.source_class})",
        f"age={age:.2f}",
        f"sign_off={soff:.2f}",
        f"plausibility={plaus:.2f}",
    ]
    return AssumptionQualityResult(
        assumption_id=assumption.assumption_id,
        source_score=src,
        age_score=age,
        sign_off_score=soff,
        plausibility_score=plaus,
        composite_score=composite,
        blocks_gate2=blocks,
        detail="; ".join(detail_parts),
    )


def check_gate2(
    initiative_id: str,
    assumptions: List[AssumptionRecord],
    *,
    reference_date: Optional[datetime] = None,
    override_by: Optional[str] = None,
) -> GateCheckResult:
    """Run Gate-2 check for an initiative's full assumption set.

    Args:
        initiative_id: Identifier for the savings initiative.
        assumptions: All assumptions associated with the initiative.
        reference_date: Reference date for age scoring (defaults to now).
        override_by: If non-None, marks a CFO override and clears the block.

    Returns:
        GateCheckResult with gate2_blocked flag and per-assumption scores.
    """
    if not assumptions:
        return GateCheckResult(
            initiative_id=initiative_id,
            assumption_scores=[],
            mean_composite=0.0,
            gate2_blocked=True,
            narrative="No assumptions recorded — Gate-2 blocked pending assumption register.",
        )

    scored = [score_assumption(a, reference_date=reference_date) for a in assumptions]
    mean = round(sum(s.composite_score for s in scored) / len(scored), 4)
    blocked_ids = [s.assumption_id for s in scored if s.blocks_gate2]
    gate2_blocked = mean < 0.65 and not override_by

    if override_by:
        narrative = (
            f"Gate-2 override recorded by {override_by}. "
            f"Mean score {mean:.2f} (threshold 0.65). "
            f"{len(blocked_ids)} assumption(s) below threshold but overridden."
        )
    elif gate2_blocked:
        narrative = (
            f"Gate-2 BLOCKED. Mean assumption quality {mean:.2f} < 0.65 threshold. "
            f"Blocking assumptions: {', '.join(blocked_ids) or 'none individually — low aggregate'}. "
            "Obtain CFO override or improve source/sign-off on flagged assumptions."
        )
    else:
        narrative = (
            f"Gate-2 CLEAR. Mean assumption quality {mean:.2f} ≥ 0.65. "
            f"{len(scored)} assumption(s) reviewed; {len(blocked_ids)} individually below threshold but aggregate passes."
        )

    return GateCheckResult(
        initiative_id=initiative_id,
        assumption_scores=scored,
        mean_composite=mean,
        gate2_blocked=gate2_blocked,
        override_available=True,
        override_recorded=bool(override_by),
        override_by=override_by,
        blocking_assumptions=blocked_ids,
        narrative=narrative,
    )


def assumptions_from_initiative(initiative: Dict[str, Any]) -> List[AssumptionRecord]:
    """Build AssumptionRecord list from a savings-modeler initiative dict."""
    raw = initiative.get("assumptions", [])
    if not isinstance(raw, list):
        raw = []
    initiative_id = str(initiative.get("category_id") or initiative.get("initiative_id") or "unknown")
    records: List[AssumptionRecord] = []
    for i, item in enumerate(raw):
        if isinstance(item, str):
            records.append(AssumptionRecord(
                assumption_id=f"{initiative_id}_a{i}",
                initiative_id=initiative_id,
                description=item,
                source_class="rule_of_thumb",
            ))
        elif isinstance(item, dict):
            records.append(AssumptionRecord(
                assumption_id=item.get("assumption_id") or f"{initiative_id}_a{i}",
                initiative_id=initiative_id,
                description=item.get("description", ""),
                source_class=item.get("source_class", "unknown"),
                p10=float(item.get("p10") or 0.0),
                p50=float(item.get("p50") or 0.0),
                p90=float(item.get("p90") or 0.0),
                validation_date=item.get("validation_date"),
                owner_name=item.get("owner_name"),
                owner_sign_off=bool(item.get("owner_sign_off", False)),
                peer_p50=item.get("peer_p50"),
                peer_std=item.get("peer_std"),
            ))
    if not records:
        # Synthetic fallback: one rule-of-thumb assumption so gate can score it
        records.append(AssumptionRecord(
            assumption_id=f"{initiative_id}_synthetic",
            initiative_id=initiative_id,
            description="Default assumption (no register provided)",
            source_class="rule_of_thumb",
        ))
    return records
