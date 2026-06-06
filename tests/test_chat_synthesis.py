"""Tests for Gemini-primary chat synthesis."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.opar.chat_synthesis import (
    build_chat_context,
    extract_query_dimensions,
    synthesize_chat_response,
)
from app.opar.models import ObserveContext
from app.opar.qa_lookup import aggregate_portfolio_suppliers, answer_general_qa


def _multi_category_profile() -> list[dict]:
    return [
        {
            "category_id": "IT_TECH",
            "category_name": "IT & Technology",
            "spend": 1_000_000_000,
            "line_count": 100,
            "top_suppliers": [
                {"supplier": "Infosys", "spend": 200_000_000, "share_of_category": 20.0},
                {"supplier": "AWS", "spend": 150_000_000, "share_of_category": 15.0},
            ],
        },
        {
            "category_id": "PROF",
            "category_name": "Professional Services",
            "spend": 800_000_000,
            "line_count": 80,
            "top_suppliers": [
                {"supplier": "Deloitte", "spend": 180_000_000, "share_of_category": 22.5},
                {"supplier": "Infosys", "spend": 50_000_000, "share_of_category": 6.25},
            ],
        },
    ]


def _it_category_profile() -> list[dict]:
    return [
        {
            "category_id": "IT_TECH",
            "category_name": "IT & Technology",
            "spend": 1_974_960_000,
            "line_count": 109,
            "share_of_total": 34.7,
            "top_suppliers": [
                {"supplier": "Infosys", "spend": 450_000_000, "share_of_category": 22.8},
                {"supplier": "AWS", "spend": 380_000_000, "share_of_category": 19.2},
            ],
            "top_geos": [{"geo": "India", "spend": 900_000_000, "share_of_category": 45.6}],
        }
    ]


def test_extract_query_dimensions_supplier_breakdown() -> None:
    dims = extract_query_dimensions(
        "Break down IT & Technology spend by supplier",
        _it_category_profile(),
    )
    assert dims.breakdown_dimension == "supplier"
    assert dims.focus_category == "IT & Technology"


def test_build_chat_context_includes_session_and_suppliers() -> None:
    ctx = ObserveContext(
        user_message="Break down IT & Technology spend by supplier",
        intent_class="general_qa",
        session_id="s1",
        engagement_id="e1",
        has_tabular_spend=True,
        data_quality_score=0.9,
    )
    manifest = {
        "company_name": "Aranya Digital Services Ltd.",
        "industry": "Manufacturing",
        "currency": "INR",
        "audience": "cfo",
        "files": [{"name": "spend.csv"}],
    }
    skill_outputs = {
        "spend-profiler": {
            "total_spend": 5_688_900_000,
            "category_profile": _it_category_profile(),
        }
    }
    context = build_chat_context(
        ctx,
        manifest,
        skill_outputs,
        chat_history=[{"role": "user", "content": "Show IT spend"}],
        currency="INR",
    )
    assert context["session_context"]["company_name"] == "Aranya Digital Services Ltd."
    assert context["query_analysis"]["breakdown_dimension"] == "supplier"
    assert context["relevant_data"]["top_suppliers"][0]["supplier"] == "Infosys"
    assert len(context["recent_turns"]) == 1


def test_extract_query_dimensions_portfolio_suppliers() -> None:
    dims = extract_query_dimensions(
        "Show me the top 10 suppliers by spend",
        _multi_category_profile(),
    )
    assert dims.breakdown_dimension == "supplier"
    assert dims.focus_category is None


def test_aggregate_portfolio_suppliers_sums_across_categories() -> None:
    ranked = aggregate_portfolio_suppliers(
        _multi_category_profile(),
        limit=10,
        total_spend=5_000_000_000,
    )
    assert ranked[0]["supplier"] == "Infosys"
    assert ranked[0]["spend"] == 250_000_000
    assert ranked[1]["supplier"] == "Deloitte"


def test_build_chat_context_portfolio_suppliers() -> None:
    ctx = ObserveContext(
        user_message="Show me the top 10 suppliers by spend",
        intent_class="general_qa",
        session_id="s1",
        engagement_id="e1",
        has_tabular_spend=True,
        data_quality_score=0.9,
    )
    manifest = {"company_name": "Acme", "currency": "INR"}
    skill_outputs = {
        "spend-profiler": {
            "total_spend": 5_000_000_000,
            "category_profile": _multi_category_profile(),
        }
    }
    context = build_chat_context(ctx, manifest, skill_outputs, currency="INR")
    portfolio = context["relevant_data"]["top_suppliers_portfolio"]
    assert portfolio[0]["supplier"] == "Infosys"
    assert context["query_analysis"]["breakdown_dimension"] == "supplier"


def test_answer_general_qa_portfolio_top_suppliers() -> None:
    validated = {
        "spend-profiler": {
            "total_spend": 5_000_000_000,
            "category_profile": _multi_category_profile(),
        }
    }
    answer = answer_general_qa(
        "Show me the top 10 suppliers by spend",
        validated,
        currency="INR",
    )
    assert "Infosys" in answer
    assert "Deloitte" in answer
    assert "Top categories" not in answer
    assert "supplier" in answer.lower()


def test_answer_general_qa_supplier_fallback() -> None:
    validated = {"spend-profiler": {"total_spend": 5e9, "category_profile": _it_category_profile()}}
    answer = answer_general_qa(
        "Break down IT & Technology spend by supplier",
        validated,
        currency="INR",
    )
    assert "Infosys" in answer
    assert "AWS" in answer
    assert "supplier" in answer.lower() or "Infosys" in answer


@patch("app.opar.chat_synthesis.synthesize_chat_response_gemini")
def test_synthesize_chat_response_uses_gemini(mock_gemini) -> None:
    mock_gemini.return_value = ("**IT & Technology** top supplier: **Infosys**", None)
    ctx = ObserveContext(
        user_message="Break down IT & Technology spend by supplier",
        intent_class="general_qa",
        session_id="s1",
    )
    manifest = {"company_name": "Acme", "industry": "tech", "currency": "INR"}
    skill_outputs = {"spend-profiler": {"total_spend": 1e9, "category_profile": _it_category_profile()}}
    result = synthesize_chat_response(ctx, manifest, skill_outputs, currency="INR")
    assert result.used_llm is True
    assert "Infosys" in result.response_text
    assert result.response_metadata.get("insight_dimension") == "supplier"
    mock_gemini.assert_called_once()


@patch("app.opar.chat_synthesis.synthesize_chat_response_gemini")
def test_synthesize_chat_response_fallback_when_gemini_off(mock_gemini) -> None:
    mock_gemini.return_value = (None, None)
    ctx = ObserveContext(
        user_message="Break down IT & Technology spend by supplier",
        intent_class="general_qa",
        session_id="s1",
    )
    manifest = {"currency": "INR"}
    skill_outputs = {"spend-profiler": {"total_spend": 1e9, "category_profile": _it_category_profile()}}
    result = synthesize_chat_response(ctx, manifest, skill_outputs, currency="INR")
    assert result.used_llm is False
    assert "Infosys" in result.response_text


@patch("app.opar.hitl.clarification_generator._call_clarification_gemini")
def test_hitl_clarification_uses_gemini(mock_gemini) -> None:
    from app.opar.hitl.clarification_generator import generate_business_clarification
    from app.opar.hitl.clarification_tool import BusinessClarificationPayload

    mock_gemini.return_value = BusinessClarificationPayload(
        question="How proceed?",
        options=["Upload spend file now", "Use industry median proxy (indicative only)"],
        reasoning="Missing data",
    )
    ctx = ObserveContext(
        user_message="benchmark",
        intent_class="benchmark",
        missing_fields=["spend_data"],
        clarification_required=True,
    )
    payload = generate_business_clarification(ctx, company_name="Acme")
    assert payload.question == "How proceed?"
    assert len(payload.options) >= 2
    mock_gemini.assert_called_once()
