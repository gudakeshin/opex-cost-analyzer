"""Tests for reflect response composition and recommendation formatters."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.opar.models import ExecutionPlan, ObserveContext, SkillTask
from app.opar.reflect_advisory import generate_llm_advisory_sections
from app.opar.reflect_compose import build_response_text
from app.opar.reflect_currency import set_reflect_currency
from app.opar.reflect_recommendations import (
    build_data_backed_recommendation_lines,
    build_synthesizer_recommendation_lines,
    recommendations_section_title,
)


def _value_bridge_validated() -> dict:
    return {
        "spend-profiler": {
            "total_spend": 1_000_000,
            "category_profile": [
                {
                    "category_id": "IT",
                    "category_name": "IT & Technology",
                    "spend": 600_000,
                    "addressable_spend": 450_000,
                }
            ],
        },
        "value-bridge-calculator": {
            "confidence_bands": {"low": 50_000, "mid": 100_000, "high": 150_000},
            "value_matrix": [
                {
                    "category_id": "IT",
                    "category_name": "IT & Technology",
                    "deduped_mid_savings": 80_000,
                    "net_npv": 200_000,
                    "payback_months": 8,
                    "confidence": "high",
                    "lever": "supplier_consolidation",
                }
            ],
        },
        "peer-benchmarker": {
            "comparisons": [
                {
                    "category_id": "IT",
                    "actual_pct_of_revenue": 2.5,
                    "benchmark_p50_pct": 1.8,
                    "percentile_band": "P75+",
                }
            ],
            "benchmark_dataset": {
                "source": "PeerSet India Tech",
                "vintage_date": "2024-Q4",
                "specificity_score": 0.75,
            },
        },
    }


def test_build_response_text_includes_data_backed_recommendations() -> None:
    set_reflect_currency("INR")
    ctx = ObserveContext(
        user_message="Show savings opportunities",
        intent_class="value_bridge",
        wants_executive_narrative=True,
    )
    plan = ExecutionPlan(tasks=[SkillTask(skill_name="value-bridge-calculator", inputs={})], user_summary="Summary")
    text = build_response_text(_value_bridge_validated(), {}, plan, ctx)
    assert "Top Recommendations (Data-Backed)" in text
    assert "IT & Technology" in text
    assert "PeerSet India Tech" in text
    assert "Value bridge" in text


def test_build_response_text_analysis_synthesizer_path() -> None:
    set_reflect_currency("INR")
    validated = {
        **_value_bridge_validated(),
        "analysis-synthesizer": {
            "executive_takeaway": "IT is the primary savings lever.",
            "recommendations": [
                {
                    "category_name": "IT & Technology",
                    "category_id": "IT",
                    "lever": "supplier_consolidation",
                    "financials": {"mid_case_savings": 80_000, "net_npv": 200_000, "payback_months": 8},
                    "confidence": {"level": "high"},
                    "evidence": [{"source": "peer-benchmarker", "detail": "2.5% vs 1.8% P50"}],
                }
            ],
            "assumptions": ["Assumes contract renewals within 12 months"],
        },
    }
    ctx = ObserveContext(user_message="optimize IT", intent_class="value_bridge", wants_executive_narrative=True)
    plan = ExecutionPlan(tasks=[], user_summary="fallback")
    text = build_response_text(validated, {}, plan, ctx)
    assert "LLM-Synthesized, Skill-Grounded" in text
    assert "IT is the primary savings lever" in text
    assert "Key Assumptions" in text


def test_recommendation_section_titles() -> None:
    assert "Data-Backed" in recommendations_section_title(False, "data")
    assert "LLM-Synthesized" in recommendations_section_title(False, "llm")
    assert "Focused category" in recommendations_section_title(True, "data")


def test_build_synthesizer_recommendation_lines_business_case() -> None:
    set_reflect_currency("INR")
    recs = [
        {
            "category_name": "Logistics",
            "lever": "contract_renegotiation",
            "financials": {"mid_case_savings": 50_000, "net_npv": 120_000, "payback_months": 6},
            "confidence": {"level": "mid"},
            "evidence": [{"source": "peer-benchmarker", "detail": "Gap vs P50"}],
        }
    ]
    ctx = ObserveContext(user_message="business case", intent_class="business_case")
    lines = build_synthesizer_recommendation_lines(recs, ctx, category_focused=False)
    joined = "\n".join(lines)
    assert "NPV" in joined
    assert "payback 6 months" in joined


def test_generate_llm_advisory_uses_configured_synthesizer() -> None:
    ctx = ObserveContext(user_message="value bridge for IT", intent_class="value_bridge")
    validated = {"value-bridge-calculator": {"confidence_bands": {"mid": 100_000}}}
    raw_advisory = {
        "executive_takeaway": "IT consolidation is the primary modeled lever with measurable peer gap.",
        "category_focus_section": "",
        "quick_wins_from_data": ["Renegotiate top vendor", "Consolidate SaaS"],
        "business_levers": [
            {
                "lever_name": "Supplier consolidation",
                "what_changes": "Reduce vendor count from 12 to 5 strategic partners",
                "why_it_works": "Volume concentration unlocks tiered pricing",
                "evidence": ["Top 3 vendors are 68% of spend", "Peer median is 4 vendors"],
            },
            {
                "lever_name": "Contract renegotiation",
                "what_changes": "Reset maintenance uplift at renewal",
                "why_it_works": "Benchmark gap is contract-driven not usage-driven",
                "evidence": ["Gap vs P75 is 2.1 pts of revenue", "Largest vendor is 31% of category"],
            },
            {
                "lever_name": "Maverick compliance",
                "what_changes": "Route card spend through approved PO workflow",
                "why_it_works": "Off-contract buying inflates unit cost materially",
                "evidence": ["Express-like lines are 14% of category", "Policy exists but is not enforced"],
            },
        ],
        "executive_callouts": ["IT is 0.7 pts above P50"],
        "priority_actions_30_60_90": [],
        "sme_qualification_narrative": "",
    }
    mock_synth = MagicMock(return_value=(raw_advisory, "thinking trace"))
    with patch("app.opar.reflect_advisory.GEMINI_ENABLED", True), patch(
        "app.opar.reflect_advisory.resolve_analysis_synthesizer", return_value=mock_synth
    ):
        advisory, thinking = generate_llm_advisory_sections(ctx, {"currency": "INR"}, validated)
    assert advisory is not None
    assert thinking == "thinking trace"
    mock_synth.assert_called()
    assert len(advisory.business_levers) == 3


def test_build_data_backed_recommendation_lines_focus_category() -> None:
    set_reflect_currency("INR")
    validated = _value_bridge_validated()
    recs = [
        {
            "category": "IT & Technology",
            "lever": "supplier_consolidation",
            "lever_label": "supplier consolidation",
            "dedup_mid": 80_000,
            "npv": 200_000,
            "payback_months": 8,
            "confidence": "high",
            "evidence": ["Peer gap: actual 2.50% of revenue vs P50 1.80%"],
        }
    ]
    ctx = ObserveContext(
        user_message="optimize IT and technology costs",
        intent_class="value_bridge",
        wants_executive_narrative=True,
    )
    bands = validated["value-bridge-calculator"]["confidence_bands"]
    lines = build_data_backed_recommendation_lines(
        recs, validated, ctx, category_focused=True, bands=bands
    )
    joined = "\n".join(lines)
    assert "Focused category actions" in joined
    assert "primary focus" in joined.lower() or "IT" in joined
