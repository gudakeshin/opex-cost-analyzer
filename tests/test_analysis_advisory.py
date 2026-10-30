"""Batch analyze path attaches deterministic advisory sections to session."""
from __future__ import annotations

from app.models import NormalizedSpendLine
from app.services.analysis import run_core_pipeline


def _lines() -> list[NormalizedSpendLine]:
    return [
        NormalizedSpendLine(
            row_id=1,
            supplier="Infosys",
            description="IT managed services",
            amount=5_000_000,
            category_id="IT",
            category_name="IT & Technology",
            amount_type="actual",
            spend_date="2024-06-15",
            currency="INR",
        ),
        NormalizedSpendLine(
            row_id=2,
            supplier="Advisory LLP",
            description="HR consulting",
            amount=2_000_000,
            category_id="HR",
            category_name="Human Resources",
            amount_type="actual",
            spend_date="2024-06-15",
            currency="INR",
        ),
    ]


def test_run_core_pipeline_attaches_advisory_sections() -> None:
    sid = "test-advisory-batch-001"
    state = run_core_pipeline(
        sid,
        _lines(),
        [],
        "technology",
        500_000_000,
        company_name="Acme Corp",
        reporting_currency="INR",
        run_id="run-advisory-test-001",
    )
    adv = state.get("advisory_sections") or {}
    assert adv.get("executive_takeaway"), "expected executive takeaway"
    assert adv.get("sme_qualification_narrative") is not None
    assert state.get("response_metadata", {}).get("narrative_mode") == "deterministic"
    assert state.get("used_llm_synthesis") is False
    cites = adv.get("citations") or []
    assert isinstance(cites, list)
    suggested = state.get("suggested_outputs") or []
    assert any(s.get("skill") == "evidence-appendix" for s in suggested if isinstance(s, dict))
