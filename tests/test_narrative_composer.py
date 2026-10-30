"""Tests for deterministic narrative composer (CXO-grade fallback)."""
from __future__ import annotations

from app.opar.reflect_advisory import advisory_quality_ok
from app.services.narrative_composer import (
    build_citations,
    compose_deterministic_advisory,
    provenance_banner_text,
    _sme_qualification_narrative,
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


def _sme_outputs() -> dict:
    base = _rich_outputs()
    base["sme-critique"] = {
        "critique_summary": {
            "total_initiatives": 3,
            "ready_count": 1,
            "probe_count": 1,
            "insufficient_count": 1,
            "savings_ready": 2_500_000,
            "savings_probe": 1_100_000,
            "savings_insufficient": 600_000,
        },
        "initiative_critiques": [
            {
                "category_id": "MKT",
                "category_name": "Marketing",
                "lever": "agency_fee_reset",
                "lever_name": "Agency Fee Reset",
                "modelled_saving_3yr": 600_000,
                "evidence_maturity": "hypothesis",
                "maturity_score": 1,
                "sme_verdict": "insufficient_data",
                "double_count_risk": False,
                "gaps": ["No contract expiry data on file"],
            },
            {
                "category_id": "IT",
                "category_name": "IT & Technology",
                "lever": "license_rightsizing",
                "lever_name": "License Rightsizing",
                "modelled_saving_3yr": 2_500_000,
                "evidence_maturity": "indicative",
                "maturity_score": 2,
                "sme_verdict": "probe_first",
                "double_count_risk": True,
                "gaps": ["Utilization baseline not validated"],
            },
        ],
        "top_probes": [
            {
                "question": "What percentage of EA seats are actively used?",
                "data_to_request": "License utilization report from SAM tool",
            }
        ],
    }
    return base


def test_sme_qualification_narrative_names_categories_and_maturity() -> None:
    text = _sme_qualification_narrative(_sme_outputs(), "INR")
    assert "Marketing" in text
    assert "hypothesis" in text
    assert "Double-count risk" in text
    assert "Priority probe" in text
    assert "License utilization" in text or "SAM tool" in text


def test_compose_advisory_uses_sme_critique_not_sparse_stub() -> None:
    advisory = compose_deterministic_advisory(_sme_outputs(), company_name="Acme", currency="INR")
    assert "Marketing" in advisory.sme_qualification_narrative
    assert "Deterministic narrative composed" not in advisory.sme_qualification_narrative


def test_business_lever_so_what_contains_currency_or_bps() -> None:
    advisory = compose_deterministic_advisory(_rich_outputs(), company_name="Acme", currency="INR")
    assert advisory.business_levers
    with_figure = [lv for lv in advisory.business_levers if lv.so_what and ("₹" in lv.so_what or "bps" in lv.so_what)]
    assert with_figure, "expected at least one lever with currency or bps in so_what"
