"""Aggregate band provenance and inference-risk scoring.

Provides:
- BandedAggregate — a wrapper that attaches a DataBand + provenance to any dict
- InferenceRiskScorer — estimates re-identification risk for an aggregate
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from app.security.classification import DataBand, classify_aggregate, classify_output_block

# k-anonymity threshold: aggregates derived from fewer rows are promoted to B3
K_ANONYMITY_THRESHOLD = 5


@dataclass
class BandedAggregate:
    """A skill-output block with attached band metadata."""

    payload: Dict[str, Any]
    band: DataBand
    source_row_count: int
    band_reason: str
    inference_risk_score: float  # 0.0 (no risk) – 1.0 (high re-identification risk)

    def is_safe_for_llm(self, mode: str = "M2") -> bool:
        """Return True if this aggregate may be included in LLM context for the given mode.

        M1: only B1 aggregates
        M2: B1, B2, B3 allowed; B4 rejected
        M3: B1, B2 allowed; B3/B4 rejected (on-prem is less trusted than managed cloud)
        """
        if mode == "M1":
            return self.band <= DataBand.B1
        if mode == "M2":
            return self.band <= DataBand.B3
        if mode == "M3":
            return self.band <= DataBand.B2
        return False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "band": self.band.value,
            "source_row_count": self.source_row_count,
            "band_reason": self.band_reason,
            "inference_risk_score": self.inference_risk_score,
            "payload": self.payload,
        }


def _inference_risk_score(band: DataBand, source_row_count: int) -> float:
    """Heuristic inference-risk score [0, 1].

    Higher = more likely to reveal individual company or person info.
    """
    band_base = {DataBand.B1: 0.05, DataBand.B2: 0.25, DataBand.B3: 0.60, DataBand.B4: 0.95}
    base = band_base.get(band, 0.5)
    # Low row count inflates risk
    row_penalty = max(0.0, (K_ANONYMITY_THRESHOLD - source_row_count) / K_ANONYMITY_THRESHOLD * 0.30)
    return min(1.0, base + row_penalty)


def wrap_aggregate(
    payload: Dict[str, Any],
    source_rows: List[Dict[str, Any]],
) -> BandedAggregate:
    """Classify and wrap a skill-output block with band provenance."""
    band, reason = classify_aggregate(source_rows, k_threshold=K_ANONYMITY_THRESHOLD)
    # Also check the payload itself for supplier-level detail
    block_band, block_reason = classify_output_block(
        payload,
        source_row_count=len(source_rows),
        k_threshold=K_ANONYMITY_THRESHOLD,
    )
    # Take the more restrictive of the two
    final_band = max(band, block_band, key=lambda b: list(DataBand).index(b))
    final_reason = f"row-based: {reason}; block-based: {block_reason}"
    risk = _inference_risk_score(final_band, len(source_rows))
    return BandedAggregate(
        payload=payload,
        band=final_band,
        source_row_count=len(source_rows),
        band_reason=final_reason,
        inference_risk_score=risk,
    )


def annotate_skill_output(
    skill_name: str,
    output: Dict[str, Any],
    source_rows: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Attach _security_metadata to a skill output dict in-place."""
    banded = wrap_aggregate(output, source_rows)
    output["_security_metadata"] = {
        "skill": skill_name,
        "band": banded.band.value,
        "source_row_count": banded.source_row_count,
        "inference_risk_score": round(banded.inference_risk_score, 3),
        "band_reason": banded.band_reason,
    }
    return output
