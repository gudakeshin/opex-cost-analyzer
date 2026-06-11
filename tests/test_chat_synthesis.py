"""Tests for provider-agnostic chat synthesis."""

from __future__ import annotations

from unittest.mock import patch


import app.opar.chat_synthesis as cs
from app.opar.chat_synthesis import (
    build_chat_context,
    extract_query_dimensions,
    resolve_chat_synthesizer,
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
    # Full context exposed (no keyword pre-filter): the focused category detail is
    # present AND the whole category list is available for the model to choose from.
    assert context["spend_data"]["focus_category_detail"]["top_suppliers"][0]["supplier"] == "Infosys"
    assert len(context["spend_data"]["categories"]) == 1
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
    portfolio = context["spend_data"]["portfolio_top_suppliers"]
    assert portfolio[0]["supplier"] == "Infosys"
    assert context["query_analysis"]["breakdown_dimension"] == "supplier"


def test_build_chat_context_exposes_all_data_regardless_of_query() -> None:
    """A vague question must still surface every category + the portfolio supplier
    ranking — the LLM picks the relevant slice; we never withhold by keyword."""
    ctx = ObserveContext(
        user_message="tell me about my spend",
        intent_class="general_qa",
        session_id="s1",
        has_tabular_spend=True,
    )
    manifest = {"company_name": "Acme", "currency": "INR"}
    skill_outputs = {
        "spend-profiler": {
            "total_spend": 1_800_000_000,
            "category_profile": _multi_category_profile(),
        }
    }
    context = build_chat_context(ctx, manifest, skill_outputs, currency="INR")
    assert len(context["spend_data"]["categories"]) == 2
    assert context["spend_data"]["portfolio_top_suppliers"][0]["supplier"] == "Infosys"
    assert context["spend_data"]["category_count"] == 2


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


@patch("app.opar.chat_synthesis._synthesize_via_llm")
def test_synthesize_chat_response_uses_llm(mock_llm) -> None:
    mock_llm.return_value = ("**IT & Technology** top supplier: **Infosys**", None)
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
    mock_llm.assert_called_once()


@patch("app.opar.chat_synthesis._synthesize_via_llm")
def test_synthesize_chat_response_fallback_when_llm_off(mock_llm) -> None:
    mock_llm.return_value = (None, None)
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


def test_resolve_chat_synthesizer_claude_default(monkeypatch) -> None:
    from app.opar.claude_client import synthesize_chat_response_claude

    monkeypatch.setattr(cs, "get_resolved_llm_provider", lambda: "anthropic")
    monkeypatch.setattr(cs, "ANTHROPIC_ENABLED", True)
    monkeypatch.setattr(cs, "GEMINI_ENABLED", False)
    assert resolve_chat_synthesizer() is synthesize_chat_response_claude


def test_resolve_chat_synthesizer_gemini_when_preferred(monkeypatch) -> None:
    monkeypatch.setattr(cs, "get_resolved_llm_provider", lambda: "gemini")
    monkeypatch.setattr(cs, "GEMINI_ENABLED", True)
    monkeypatch.setattr(cs, "ANTHROPIC_ENABLED", False)
    assert resolve_chat_synthesizer() is cs.synthesize_chat_response_gemini


def test_resolve_chat_synthesizer_cross_fallback_to_gemini(monkeypatch) -> None:
    monkeypatch.setattr(cs, "get_resolved_llm_provider", lambda: "anthropic")
    monkeypatch.setattr(cs, "ANTHROPIC_ENABLED", False)
    monkeypatch.setattr(cs, "GEMINI_ENABLED", True)
    assert resolve_chat_synthesizer() is cs.synthesize_chat_response_gemini


def test_resolve_chat_synthesizer_none_when_no_provider(monkeypatch) -> None:
    monkeypatch.setattr(cs, "ANTHROPIC_ENABLED", False)
    monkeypatch.setattr(cs, "GEMINI_ENABLED", False)
    assert resolve_chat_synthesizer() is None


def test_build_chat_context_includes_modeled_initiatives_and_contracts() -> None:
    ctx = ObserveContext(
        user_message="Give me the details of the contract renegotiations",
        intent_class="general_qa",
        session_id="s1",
        has_tabular_spend=True,
    )
    manifest = {"company_name": "Prakrit", "currency": "INR"}
    skill_outputs = {
        "spend-profiler": {
            "total_spend": 77_354_600_000,
            "category_profile": _it_category_profile(),
        },
        "savings-modeler": {
            "initiatives": [
                {
                    "category_id": "IT_TECH",
                    "category_name": "IT & Technology",
                    "lever": "contract_renegotiation",
                    "lever_name": "Contract Renegotiation",
                    "confidence": "high",
                    "net_savings": {"total_3yr": 120_000_000},
                }
            ]
        },
        "value-bridge-calculator": {
            "confidence_bands": {"low": 50_000_000, "mid": 100_000_000, "high": 150_000_000},
            "value_matrix": [
                {
                    "category_id": "IT_TECH",
                    "category_name": "IT & Technology",
                    "lever": "contract_renegotiation",
                    "deduped_mid_savings": 80_000_000,
                    "payback_months": 9,
                }
            ],
        },
        "contract-lifecycle-manager": {
            "renewal_alerts": [
                {"supplier": "Infosys", "alert_type": "renewal_due", "annual_spend": 450_000_000, "days_to_expiry": 25}
            ]
        },
        "document-contextualizer": {
            "constraints": ["Oracle maintenance contract renews in Q3 — renegotiate before auto-renewal"],
            "context_summary": "Contract register notes upcoming renewals.",
        },
    }
    context = build_chat_context(ctx, manifest, skill_outputs, currency="INR")
    assert context["modeled_initiatives"][0]["lever"] == "contract_renegotiation"
    assert context["value_matrix_rows"][0]["deduped_mid_savings"] == 80_000_000
    assert context["contract_renewals"][0]["supplier"] == "Infosys"
    assert "Oracle" in context["document_context"]["constraints"][0]


def test_answer_general_qa_contract_renegotiation_details() -> None:
    validated = {
        "spend-profiler": {
            "total_spend": 77_354_600_000,
            "category_profile": _it_category_profile(),
        },
        "savings-modeler": {
            "initiatives": [
                {
                    "category_id": "IT_TECH",
                    "category_name": "IT & Technology",
                    "lever": "contract_renegotiation",
                    "lever_name": "Contract Renegotiation",
                    "confidence": "high",
                    "net_savings": {"total_3yr": 120_000_000},
                }
            ]
        },
        "value-bridge-calculator": {
            "value_matrix": [
                {
                    "category_id": "IT_TECH",
                    "category_name": "IT & Technology",
                    "lever": "contract_renegotiation",
                    "deduped_mid_savings": 80_000_000,
                    "payback_months": 9,
                }
            ]
        },
    }
    answer = answer_general_qa(
        "Give me the details of the contract renegotiations",
        validated,
        currency="INR",
    )
    assert "Contract renegotiation" in answer
    assert "IT & Technology" in answer
    assert "Top categories" not in answer
    assert "total spend is" not in answer.lower()


def test_answer_general_qa_contract_without_model_prompts_value_bridge() -> None:
    validated = {
        "spend-profiler": {
            "total_spend": 1_000_000,
            "category_profile": _it_category_profile(),
        }
    }
    answer = answer_general_qa(
        "Give me the details of the contract renegotiations",
        validated,
        currency="INR",
    )
    assert "value-at-the-table" in answer.lower()
    assert "total spend is" not in answer.lower()


@patch("app.opar.chat_synthesis._synthesize_via_llm")
def test_synthesize_chat_response_contract_question_uses_deterministic_when_llm_off(mock_llm) -> None:
    mock_llm.return_value = (None, None)
    ctx = ObserveContext(
        user_message="Give me the details of the contract renegotiations",
        intent_class="general_qa",
        session_id="s1",
    )
    manifest = {"currency": "INR"}
    skill_outputs = {
        "spend-profiler": {"total_spend": 1e9, "category_profile": _it_category_profile()},
        "savings-modeler": {
            "initiatives": [
                {
                    "category_id": "IT_TECH",
                    "category_name": "IT & Technology",
                    "lever": "contract_renegotiation",
                    "lever_name": "Contract Renegotiation",
                    "net_savings": {"total_3yr": 120_000_000},
                }
            ]
        },
    }
    result = synthesize_chat_response(ctx, manifest, skill_outputs, currency="INR")
    assert result.used_llm is False
    assert "Contract renegotiation" in result.response_text


def test_build_chat_context_truncates_oversized_manifest_fields() -> None:
    fat = "z" * 200_000
    ctx = ObserveContext(user_message="summarize spend", intent_class="drill_down")
    manifest = {
        "deep_research_summary": fat,
        "business_override_note": fat,
        "probe_answers": [{"answer": fat}],
    }
    with patch("app.opar.chat_synthesis._fetch_document_excerpts", lambda *a, **k: []):
        context = build_chat_context(ctx, manifest, {}, currency="INR")
    assert len(context["deep_research_summary"]) <= 1200
    assert len(context["business_override_note"]) <= 1200
    assert len(context["probe_context"]["probe_answers"][0]["answer"]) <= 400


def test_build_chat_context_fat_row_strings_bounded() -> None:
    fat = "n" * 200_000
    ctx = ObserveContext(user_message="payment terms", intent_class="drill_down")
    skill_outputs = {
        "spend-profiler": {
            "total_spend": 1_000_000,
            "category_profile": [{
                "category_id": "IT",
                "category_name": fat,
                "spend": 500_000,
                "top_suppliers": [{"supplier": "S1", "spend": 100, "note": fat}],
            }],
        },
        "payment-terms-optimizer": {
            "opportunities": [{"supplier": "Zenmark", "note": fat, "annual_cash_value": 1}],
        },
    }
    with patch("app.opar.chat_synthesis._fetch_document_excerpts", lambda *a, **k: []):
        context = build_chat_context(ctx, {}, skill_outputs, currency="INR")
    cat = context["spend_data"]["categories"][0]
    assert len(cat["category_name"]) <= 120
    assert len(cat["top_suppliers"][0]["note"]) <= 120
    assert len(context["spend_data"]["payment_terms_opportunities"][0]["note"]) <= 200


def test_build_chat_context_overall_budget_trim() -> None:
    fat = "b" * 200_000
    ctx = ObserveContext(user_message="overview", intent_class="drill_down")
    manifest = {"deep_research_summary": fat, "probe_answers": [{"answer": fat} for _ in range(10)]}
    history = [{"role": "user", "content": fat} for _ in range(6)]
    skill_outputs = {
        "spend-profiler": {
            "total_spend": 1_000_000,
            "category_profile": [
                {"category_id": f"C{i}", "category_name": fat, "spend": 10_000,
                 "top_suppliers": [{"supplier": f"S{j}", "note": fat} for j in range(10)]}
                for i in range(12)
            ],
        },
        "document-contextualizer": {"context_summary": fat, "constraints": [fat] * 8},
    }
    with patch("app.opar.chat_synthesis._fetch_document_excerpts", lambda *a, **k: [fat] * 4):
        context = build_chat_context(ctx, manifest, skill_outputs, chat_history=history, currency="INR")
    from app.opar.reflect_advisory import _estimate_tokens
    from app.opar.chat_synthesis import _CHAT_CONTEXT_TOKEN_LIMIT

    assert _estimate_tokens(context) <= _CHAT_CONTEXT_TOKEN_LIMIT


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
