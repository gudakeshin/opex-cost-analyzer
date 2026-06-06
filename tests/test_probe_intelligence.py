"""Tests for Gemini-assisted portfolio probe composer."""

from __future__ import annotations

import json
from unittest.mock import patch

from app.opar.probe_intelligence import (
    _merge_gemini_probes,
    enrich_portfolio_probes_with_gemini,
    synthesize_probe_answer_acknowledgment,
)


def test_merge_gemini_probes_rewrites_question_and_categories() -> None:
    original = [
        {
            "probe_family_id": "transaction_volume",
            "question": "What is the current invoice-approval cycle time for HR?",
            "why_critical": "Volume drives ROI",
            "affected_categories": ["HR", "Travel"],
            "saving_at_stake": 300,
            "scope": "portfolio",
        }
    ]
    refined = [
        {
            "probe_family_id": "transaction_volume",
            "question": "What is the current invoice-approval cycle time and monthly invoice volume across AP?",
            "reasoning": "Automation ROI scales with volume.",
            "applies_to_categories": ["HR", "Travel", "Other"],
            "scope": "portfolio",
            "options": ["12 days, ~800/month", "Defer data gathering"],
        }
    ]
    out = _merge_gemini_probes(original, refined)
    assert len(out) == 1
    assert "invoice" in out[0]["question"].lower()
    assert out[0]["affected_categories"] == ["HR", "Travel", "Other"]
    assert out[0]["options"][0].startswith("12 days")


@patch("app.opar.probe_intelligence.GEMINI_ENABLED", False)
def test_enrich_skips_when_gemini_disabled() -> None:
    probes = [{"probe_family_id": "transaction_volume", "question": "Q"}]
    assert enrich_portfolio_probes_with_gemini(probes) is None


@patch("app.opar.probe_intelligence.GEMINI_ENABLED", True)
@patch("app.opar.probe_intelligence.call_gemini")
def test_enrich_portfolio_probes_with_gemini(mock_gemini) -> None:
    mock_gemini.return_value = json.dumps({
        "portfolio_probes": [
            {
                "probe_family_id": "transaction_volume",
                "question": "One portfolio question on invoice cycle time?",
                "reasoning": "Shared AP gap",
                "scope": "portfolio",
                "applies_to_categories": ["HR", "Travel"],
                "options": ["Option A", "Option B"],
            }
        ]
    })
    original = [
        {
            "probe_family_id": "transaction_volume",
            "question": "Per-category question HR",
            "why_critical": "x",
            "affected_categories": ["HR", "Travel"],
            "saving_at_stake": 200,
            "scope": "portfolio",
        }
    ]
    out = enrich_portfolio_probes_with_gemini(original)
    assert out is not None
    assert len(out) == 1
    assert out[0]["question"].startswith("One portfolio question")


@patch("app.opar.probe_intelligence.GEMINI_ENABLED", False)
def test_acknowledgment_fallback_when_gemini_off() -> None:
    assert (
        synthesize_probe_answer_acknowledgment(
            probe_family_id="transaction_volume",
            answer="12 days",
            applies_to_categories=["HR"],
            remaining_count=2,
        )
        is None
    )
