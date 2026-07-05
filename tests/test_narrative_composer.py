"""Tests for deterministic narrative composer (CXO-grade fallback)."""
from __future__ import annotations

from app.opar.reflect_advisory import advisory_quality_ok
from app.services.narrative_composer import (
    build_citations,
    compose_deterministic_advisory,
    provenance_banner_text,
)


def _rich_outputs() -> dict:
    return {
        "spend-profiler": {
            "total_spend": 12_000_000.0,
            "category_profile": [
                {
                    "category_id": "IT",
                    "category_name": "IT & Technology",
                    "spend": 4_500_000.0,
                    "concentration_flag": "high",
                    "top_suppliers": [{"supplier": "Microsoft", "share_of_category": 0.44, "spend": 2_000_000}],
                },
                {
                    "category_id": "LOG",
                    "category_name": "Logistics",
                    "spend": 2_100_000.0,
                    "top_suppliers": [{"supplier": "DHL", "share_of_category": 0.57, "spend": 1_200_000}],
                },
                {
                    "category_id": "MKT",
                    "category_name": "Marketing",
                    "spend": 1_800_000.0,
                    "top_suppliers": [],
                },
            ],
        },
        "peer-benchmarker": {
            "industry": "technology",
            "comparisons": [
                {
                    "category_id": "IT",
                    "category_name": "IT & Technology",
                    "actual_pct_of_revenue": 3.2,
                    "benchmark_p50_pct": 2.1,
                    "percentile_band": "P75-P90",
                    "estimated_saving_amount": 18_200_000.0,
                    "benchmark_sample_n": 42,
                },
                {
                    "category_id": "LOG",
                    "category_name": "Logistics",
                    "actual_pct_of_revenue": 1.5,
                    "benchmark_p50_pct": 0.9,
                    "percentile_band": "P75+",
                    "estimated_saving_amount": 6_500_000.0,
                    "benchmark_sample_n": 38,
                },
            ],
            "benchmark_dataset": {"source": "PeerSet India Tech", "vintage_date": "2024-Q4"},
        },
        "root-cause-analyzer": {
            "root_cause_findings": [
                {
                    "category_id": "IT",
                    "category_name": "IT & Technology",
                    "root_causes": [
                        {
                            "diagnosis": "Shelfware and overlapping enterprise agreements",
                            "recommended_lever": "license_rightsizing",
                            "implementation_approach": "Rationalize EA seats before renewal window.",
                        }
                    ],
                },
                {
                    "category_id": "LOG",
                    "category_name": "Logistics",
                    "root_causes": [
                        {
                            "diagnosis": "Lane fragmentation across carriers",
                            "implementation_approach": "Consolidate volume to strategic carriers.",
                        }
                    ],
                },
            ]
        },
        "savings-modeler": {
            "initiatives": [
                {
                    "category_id": "IT",
                    "category_name": "IT & Technology",
                    "lever": "license_rightsizing",
                    "lever_name": "License Rightsizing",
                    "root_cause": "Shelfware above peer norm",
                    "confidence": "medium",
                    "payback_months": 5,
                    "annualized_run_rate_savings": 2_500_000.0,
                    "ebitda_impact": {"ebitda_bps": 12.0},
                    "execution_playbook": [{"step": "Baseline utilization and retire unused seats"}],
                },
                {
                    "category_id": "LOG",
                    "category_name": "Logistics",
                    "lever": "carrier_consolidation",
                    "lever_name": "Carrier Consolidation",
                    "root_cause": "Fragmented lane contracts",
                    "confidence": "high",
                    "payback_months": 7,
                    "annualized_run_rate_savings": 1_100_000.0,
                    "ebitda_impact": {"ebitda_bps": 5.5},
                    "execution_playbook": [{"step": "Rebid top lanes with consolidated volume"}],
                },
                {
                    "category_id": "MKT",
                    "category_name": "Marketing",
                    "lever": "agency_fee_reset",
                    "lever_name": "Agency Fee Reset",
                    "root_cause": "Above-market agency retainers",
                    "confidence": "medium",
                    "payback_months": 4,
                    "annualized_run_rate_savings": 600_000.0,
                    "ebitda_impact": {"ebitda_bps": 3.0},
                },
            ],
            "summary": {"portfolio_ebitda_impact_bps": 20.5, "total_run_rate_savings": 4_200_000.0},
        },
        "value-bridge-calculator": {
            "confidence_bands": {"low": 30_000_000.0, "mid": 36_000_000.0, "high": 42_000_000.0},
            "value_matrix": [{"category_id": "IT", "lever": "license_rightsizing"}],
        },
        "scenario-modeler": {
            "downside_floor": 22_000_000.0,
            "downside_floor_pct_of_base": 0.61,
            "p10_savings": 24_000_000.0,
            "p90_savings": 48_000_000.0,
        },
    }


def test_composer_passes_advisory_quality_gate() -> None:
    advisory = compose_deterministic_advisory(
        _rich_outputs(),
        company_name="Acme",
        currency="INR",
        category_focused=True,
    )
    assert advisory_quality_ok(advisory, category_focused=True)
    assert len(advisory.business_levers) >= 3
    assert len(advisory.quick_wins_from_data) >= 2


def test_executive_takeaway_cites_percentile_and_currency_gap() -> None:
    advisory = compose_deterministic_advisory(_rich_outputs(), company_name="Acme", currency="INR")
    text = advisory.executive_takeaway.lower()
    assert "p75" in text or "peer" in text
    assert "₹" in advisory.executive_takeaway
    assert "acme" in text


def test_build_citations_from_skill_outputs() -> None:
    cites = build_citations(_rich_outputs(), currency="INR")
    skills = {c.source_skill for c in cites}
    assert "peer-benchmarker" in skills
    assert "savings-modeler" in skills
    assert "value-bridge-calculator" in skills


def test_sparse_data_partial_mode() -> None:
    sparse = {
        "value-bridge-calculator": {"confidence_bands": {"low": 1, "mid": 2, "high": 3}},
        "savings-modeler": {"initiatives": [_rich_outputs()["savings-modeler"]["initiatives"][0]]},
    }
    advisory = compose_deterministic_advisory(sparse, company_name="SparseCo", currency="INR", sparse_note=True)
    assert advisory.executive_takeaway
    assert advisory.sme_qualification_narrative
    assert not advisory_quality_ok(advisory, category_focused=True)


def test_provenance_banner_only_for_deterministic() -> None:
    assert provenance_banner_text({"mode": "deterministic", "llm_skip_reason": "provider_billing"})
    assert provenance_banner_text({"mode": "llm"}) is None
