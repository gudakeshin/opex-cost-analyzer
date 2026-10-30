"""Billing/auth error classification and composer fallback when LLM is down."""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.memory import MemoryStore
from app.opar.llm_errors import ProviderBillingError, classify_provider_error
from app.opar.models import ActResult, ExecutionPlan, ObserveContext, SkillTask
from app.opar.reflect import reflect
from app.opar.reflect_advisory import generate_llm_advisory_sections
from app.services import business_case as bc_mod
from app.services.business_case import build_business_case, export_docx
from tests.test_narrative_composer import _rich_outputs


def test_classify_credit_balance_as_billing() -> None:
    class FakeExc(Exception):
        status_code = 400

        def __str__(self) -> str:
            return "credit balance is too low"

    classified = classify_provider_error(FakeExc())
    assert isinstance(classified, ProviderBillingError)
    assert classified.skip_reason == "provider_billing"


def test_generate_llm_advisory_short_circuits_on_billing_error() -> None:
    ctx = ObserveContext(user_message="value bridge", intent_class="value_bridge")
    validated = {
        "value-bridge-calculator": {"confidence_bands": {"mid": 100_000}},
        "savings-modeler": {"initiatives": [{"category_id": "IT", "lever_name": "x"}]},
    }

    def _raise_billing(*_a, **_k):
        raise ProviderBillingError("no credits")

    mock_synth = MagicMock(side_effect=_raise_billing)
    with patch("app.opar.reflect_advisory.GEMINI_ENABLED", True), patch(
        "app.opar.reflect_advisory._iter_analysis_synthesizers", return_value=[mock_synth]
    ):
        advisory, _thinking, skip = generate_llm_advisory_sections(ctx, {"currency": "INR"}, validated)
    assert advisory is None
    assert skip == "provider_billing"
    assert mock_synth.call_count == 1


def test_business_case_billing_skip_uses_composer_with_provenance(tmp_path) -> None:
    analysis = {
        "company_name": "Acme",
        "reporting_currency": "INR",
        "skill_outputs": _rich_outputs(),
    }
    with patch.object(bc_mod, "_llm_advisory_sections", return_value=(None, "provider_billing")):
        bc = build_business_case(analysis)
    assert bc["narrative_provenance"]["mode"] == "deterministic"
    assert bc["narrative_provenance"]["llm_skip_reason"] == "provider_billing"
    secs = bc["sections"]
    assert len(secs["business_levers"]) >= 3
    assert len(secs["quick_wins"]) >= 2
    assert secs["evidence_and_sources"]
    with patch.object(bc_mod, "OUTPUT_DIR", tmp_path):
        path = export_docx(bc, "bc.docx")
    assert path.exists()


def test_reflect_composer_when_advisory_billing_fails() -> None:
    session_id = str(uuid.uuid4())
    validated = _rich_outputs()
    MemoryStore().put(
        "session",
        session_id,
        {"session_id": session_id, "skill_outputs": validated, "normalized_spend": []},
    )
    ctx = ObserveContext(
        user_message="What drives spend in IT & Technology?",
        intent_class="value_bridge",
        explicit_category="IT & Technology",
        query_capabilities=["root_cause", "value_modeling"],
        session_id=session_id,
        user_id="user-1",
    )
    act_result = ActResult(skill_outputs=validated, errors={})
    plan = ExecutionPlan(tasks=[SkillTask(skill_name=name) for name in validated])

    with patch("app.opar.reflect.needs_llm_advisory", return_value=True), patch(
        "app.opar.reflect.generate_llm_advisory_sections",
        return_value=(None, None, "provider_billing"),
    ):
        result = reflect(act_result, plan, ctx)

    assert result.advisory_sections is not None
    assert len(result.advisory_sections.business_levers) >= 1
    assert result.response_metadata.get("narrative_mode") == "deterministic"
    assert result.fallback_reasons.get("llm_advisory") == "provider_billing"
    assert "IT" in result.response_text or "technology" in result.response_text.lower()
