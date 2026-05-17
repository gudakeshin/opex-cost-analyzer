from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.skills.contracts import validate_core_skill_outputs


def test_contract_validation_accepts_valid_shapes() -> None:
    validate_core_skill_outputs(
        profile={"total_spend": 100.0, "category_profile": [{"category_id": "IT", "category_name": "IT", "spend": 100.0, "line_count": 1, "share_of_total": 1.0}]},
        context={"context_summary": "ok", "constraints": []},
        peer={"industry": "technology", "comparisons": [{"category_id": "IT", "category_name": "IT", "actual_pct_of_revenue": 1.0, "benchmark_target_pct": 0.4, "benchmark_p50_pct": 0.5, "percentile_band": "P50-P75", "estimated_saving_amount": 10.0, "source": "test"}]},
        internal={"internal_variance": [{"category_id": "IT", "max_spend": 100.0, "min_spend": 90.0, "median_spend": 95.0, "internal_spread": 0.1, "flagged_gt_20pct": False, "segments": [{"segment": "BU1", "spend": 100.0}]}]},
        heuristic={"heuristic_findings": [{"category_id": "IT", "actual_pct_of_revenue": 1.0, "heuristic_target_pct": 0.5, "estimated_saving_amount": 5.0}]},
        bridge={"value_matrix": [{"category_id": "IT", "peer_savings": 10.0, "internal_savings": 5.0, "heuristic_savings": 5.0, "deduped_mid_savings": 15.0}], "confidence_bands": {"low": 10.0, "mid": 15.0, "high": 20.0}, "addressable_pct_of_total_spend": 0.15},
        validator={"checks": {"bands_monotonic": True}, "passed": True},
    )


def test_contract_validation_rejects_invalid_shapes() -> None:
    with pytest.raises(ValidationError):
        validate_core_skill_outputs(
            profile={"category_profile": []},
            context={"context_summary": "ok", "constraints": []},
            peer={"industry": "technology", "comparisons": []},
            internal={"internal_variance": []},
            heuristic={"heuristic_findings": []},
            bridge={"value_matrix": [], "confidence_bands": {"low": 0, "mid": 0, "high": 0}, "addressable_pct_of_total_spend": 0},
            validator={"checks": {}, "passed": True},
        )


def test_contract_validation_accepts_modeled_value_bridge_shape() -> None:
    validate_core_skill_outputs(
        profile={"total_spend": 100.0, "category_profile": [{"category_id": "IT", "category_name": "IT", "spend": 100.0, "line_count": 1, "share_of_total": 1.0}]},
        context={"context_summary": "ok", "constraints": []},
        peer={"industry": "technology", "comparisons": [{"category_id": "IT", "category_name": "IT", "actual_pct_of_revenue": 1.0, "benchmark_target_pct": 0.4, "benchmark_p50_pct": 0.5, "percentile_band": "P50-P75", "estimated_saving_amount": 10.0, "source": "test"}]},
        internal={"internal_variance": [{"category_id": "IT", "max_spend": 100.0, "min_spend": 90.0, "median_spend": 95.0, "internal_spread": 0.1, "flagged_gt_20pct": False, "segments": [{"segment": "BU1", "spend": 100.0}]}]},
        heuristic={"heuristic_findings": [{"category_id": "IT", "actual_pct_of_revenue": 1.0, "heuristic_target_pct": 0.5, "estimated_saving_amount": 5.0}]},
        bridge={
            "value_matrix": [
                {
                    "category_id": "IT",
                    "category_name": "IT & Technology",
                    "lever": "supplier_consolidation",
                    "root_cause": "Fragmented supplier base",
                    "gross_3yr": 30.0,
                    "cost_to_achieve_3yr": 5.0,
                    "net_npv": 20.0,
                    "payback_months": 12,
                    "confidence": "high",
                    "deduped_mid_savings": 25.0,
                }
            ],
            "confidence_bands": {"low": 20.0, "mid": 25.0, "high": 30.0},
            "addressable_pct_of_total_spend": 0.25,
        },
        validator={"checks": {"bands_monotonic": True}, "passed": True},
    )

