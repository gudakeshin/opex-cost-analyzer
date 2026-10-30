"""Tests for evidence appendix export builder."""
from __future__ import annotations

from app.services.evidence_appendix import build_evidence_appendix


def _analysis_blob() -> dict:
    return {
        "reporting_currency": "INR",
        "skill_outputs": {
            "peer-benchmarker": {
                "comparisons": [
                    {
                        "category_id": "IT",
                        "category_name": "IT & Technology",
                        "actual_pct_of_revenue": 3.2,
                        "benchmark_p50_pct": 2.1,
                        "percentile_band": "P75-P90",
                        "estimated_saving_amount": 1_800_000,
                        "benchmark_sample_n": 12,
                    }
                ],
                "benchmark_dataset": {"source": "PeerSet", "vintage_date": "2024-Q4"},
            },
            "sme-critique": {
                "critique_summary": {"ready_count": 1, "probe_count": 0, "insufficient_count": 0},
                "initiative_critiques": [
                    {
                        "category_name": "IT & Technology",
                        "lever_name": "License Rightsizing",
                        "modelled_saving_3yr": 2_500_000,
                        "evidence_maturity": "indicative",
                        "sme_verdict": "probe_first",
                        "double_count_risk": False,
                        "gaps": ["Utilization baseline missing"],
                    }
                ],
            },
            "savings-modeler": {"initiatives": [{"lever_name": "License Rightsizing"}]},
            "value-bridge-calculator": {"confidence_bands": {"mid": 3_000_000}},
        },
        "ingestion_summary": {"rows_parsed": 1200},
    }


def test_build_evidence_appendix_includes_citations_and_sme() -> None:
    appendix = build_evidence_appendix(_analysis_blob(), company_name="Acme")
    assert appendix["type"] == "evidence_appendix"
    assert appendix["company_name"] == "Acme"
    assert len(appendix["citations"]) >= 1
    assert appendix["sme_critique"][0]["category"] == "IT & Technology"
    assert appendix["benchmark_rows"][0]["vintage"] == "2024-Q4"
