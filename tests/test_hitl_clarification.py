"""Tests for HITL business clarification probe at Observe gate."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from app.opar.hitl.checkpoint_store import checkpoint_store
from app.opar.hitl.clarification_generator import generate_business_clarification
from app.opar.hitl.clarification_tool import (
    BusinessClarificationPayload,
    ClarificationAnswer,
)
from app.opar.hitl.resume import apply_clarification_answer, should_waive_spend_requirement
from app.opar.models import ObserveContext, ReflectOutput
from app.opar.orchestrator import (
    CheckpointNotFoundError,
    resume_opar_loop,
    run_opar_plan_preview,
)
from app.storage import ensure_dirs, write_json
from app.config import UPLOAD_DIR


def test_business_clarification_payload_rejects_too_few_options() -> None:
    with pytest.raises(ValidationError):
        BusinessClarificationPayload(
            question="How should we proceed?",
            options=["Only one"],
            reasoning="Need input",
        )


def test_business_clarification_payload_rejects_too_many_options() -> None:
    with pytest.raises(ValidationError):
        BusinessClarificationPayload(
            question="How should we proceed?",
            options=["a", "b", "c", "d", "e"],
            reasoning="Need input",
        )


def test_clarification_answer_has_response() -> None:
    assert ClarificationAnswer(selected_option="Upload spend file now").has_response()
    assert ClarificationAnswer(free_text="Ignore subsidiary variance").has_response()
    assert not ClarificationAnswer().has_response()


@patch("app.opar.hitl.clarification_generator.GEMINI_ENABLED", False)
def test_generate_business_clarification_fallback() -> None:
    ctx = ObserveContext(
        user_message="Benchmark my spend",
        intent_class="benchmark",
        missing_fields=["spend_data", "annual_revenue"],
        data_quality_score=0.2,
        clarification_required=True,
    )
    payload = generate_business_clarification(ctx, company_name="Acme Corp")
    assert 2 <= len(payload.options) <= 4
    assert payload.question
    assert payload.reasoning
    assert any("upload" in o.lower() or "proxy" in o.lower() for o in payload.options)


def test_checkpoint_store_save_and_get() -> None:
    clarification = BusinessClarificationPayload(
        question="What inputs should we use?",
        options=["Upload spend file now", "Use industry median proxy (indicative only)"],
        reasoning="Spend data is missing.",
    )
    checkpoint_id = checkpoint_store.save(
        session_id="sess-1",
        user_id="user-1",
        original_message="benchmark my spend",
        observe_context={"intent_class": "benchmark"},
        clarification=clarification,
    )
    loaded = checkpoint_store.get(checkpoint_id)
    assert loaded is not None
    assert loaded.session_id == "sess-1"
    assert loaded.clarification.question == clarification.question


def test_should_waive_spend_requirement() -> None:
    assert should_waive_spend_requirement(
        ClarificationAnswer(selected_option="Use industry median proxy (indicative only)")
    )
    assert should_waive_spend_requirement(
        ClarificationAnswer(free_text="Ignore variance related to Wonder Cement subsidiary")
    )
    assert not should_waive_spend_requirement(
        ClarificationAnswer(selected_option="Upload spend file now")
    )


def test_apply_clarification_answer_persists_waiver(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.opar.hitl.resume.UPLOAD_DIR", tmp_path)
    session_id = "hitl-session"
    (tmp_path / session_id).mkdir(parents=True)
    write_json(
        tmp_path / session_id / "manifest.json",
        {"files": [], "industry": "technology", "annual_revenue": 0.0},
    )
    overrides = apply_clarification_answer(
        session_id,
        ClarificationAnswer(selected_option="Use industry median proxy (indicative only)"),
    )
    assert overrides["waive_spend_requirement"] is True
    assert overrides["clarification_resolved"] is True


def test_plan_preview_returns_hitl_when_data_missing(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.opar.orchestrator.UPLOAD_DIR", tmp_path)
    session_id = str(uuid.uuid4())
    (tmp_path / session_id).mkdir(parents=True)
    write_json(
        tmp_path / session_id / "manifest.json",
        {"files": [], "industry": "technology", "annual_revenue": 1_000_000_000},
    )
    preview = run_opar_plan_preview(
        "Benchmark my spend against peers",
        session_id,
        "test_user",
    )
    assert preview["hitl_required"] is True
    assert preview["checkpoint_id"]
    assert preview["clarification"]["question"]
    assert 2 <= len(preview["clarification"]["options"]) <= 4


@pytest.mark.asyncio
async def test_resume_opar_loop_checkpoint_not_found() -> None:
    with pytest.raises(CheckpointNotFoundError):
        await resume_opar_loop(
            str(uuid.uuid4()),
            ClarificationAnswer(selected_option="Use industry median proxy (indicative only)"),
        )


@pytest.mark.asyncio
async def test_resume_opar_loop_with_waiver(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.opar.orchestrator.UPLOAD_DIR", tmp_path)
    monkeypatch.setattr("app.opar.hitl.resume.UPLOAD_DIR", tmp_path)
    session_id = str(uuid.uuid4())
    (tmp_path / session_id).mkdir(parents=True)
    write_json(
        tmp_path / session_id / "manifest.json",
        {"files": [], "industry": "technology", "annual_revenue": 1_000_000_000},
    )
    preview = run_opar_plan_preview("Benchmark my spend", session_id, "test_user")
    checkpoint_id = preview["checkpoint_id"]
    assert checkpoint_id

    mock_reflect = ReflectOutput(response_text="Analysis complete.", loop_complete=True)
    with patch("app.opar.orchestrator.act", new_callable=AsyncMock) as mock_act:
        from app.opar.models import ActResult

        mock_act.return_value = ActResult(skill_outputs={}, errors={})
        with patch("app.opar.orchestrator.reflect", return_value=mock_reflect):
            result = await resume_opar_loop(
                checkpoint_id,
                ClarificationAnswer(selected_option="Use industry median proxy (indicative only)"),
            )
    assert result.response_text == "Analysis complete."
    assert result.loop_complete is True


def test_chat_resume_endpoint_404(client) -> None:
    resp = client.post(
        "/api/v1/chat/resume",
        json={
            "checkpoint_id": str(uuid.uuid4()),
            "selected_option": "Use industry median proxy (indicative only)",
        },
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["error"] == "checkpoint_not_found"


def test_chat_resume_endpoint_422_empty_answer(client) -> None:
    resp = client.post(
        "/api/v1/chat/resume",
        json={"checkpoint_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 422


def test_chat_plan_hitl_integration(client) -> None:
    ensure_dirs()
    create = client.post(
        "/api/sessions",
        json={"company_name": "HITL Co", "industry": "technology", "annual_revenue": 1_000_000_000},
    )
    session_id = create.json()["session_id"]
    resp = client.post(
        "/api/v1/chat/plan",
        json={"message": "Run benchmark analysis", "session_id": session_id},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("hitl_required") is True
    assert data.get("checkpoint_id")
    assert data["clarification"]["question"]
    assert len(data["clarification"]["options"]) >= 2
