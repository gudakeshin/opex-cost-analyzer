"""Tests for SME probe answer persistence and API."""

from __future__ import annotations

import uuid

import pytest

from app.config import UPLOAD_DIR
from app.opar.hitl.probe_answers import (
    apply_probe_answer,
    filter_sme_critique_with_answers,
    get_answered_family_ids,
    load_probe_answers,
)
from app.storage import ensure_dirs, write_json


@pytest.fixture
def session_id() -> str:
    ensure_dirs()
    sid = str(uuid.uuid4())
    write_json(UPLOAD_DIR / sid / "manifest.json", {
        "files": [],
        "industry": "technology",
        "annual_revenue": 0.0,
    })
    return sid


def test_apply_probe_answer_persists_to_manifest(session_id: str) -> None:
    entry = apply_probe_answer(session_id, {
        "probe_family_id": "transaction_volume",
        "question": "Invoice cycle time?",
        "answer": "Average 12 days, ~800 invoices/month",
        "scope": "portfolio",
        "applies_to_categories": ["HR", "Travel", "Other"],
    })
    assert entry["probe_family_id"] == "transaction_volume"
    answers = load_probe_answers(session_id)
    assert len(answers) == 1
    assert answers[0]["answer"].startswith("Average 12 days")
    assert get_answered_family_ids(session_id) == {"transaction_volume"}


def test_filter_sme_critique_removes_answered_families(session_id: str) -> None:
    sme = {
        "portfolio_probes": [
            {"probe_family_id": "transaction_volume", "question": "Q1"},
            {"probe_family_id": "po_coverage", "question": "Q2"},
        ],
        "top_probes": [
            {"probe_family_id": "transaction_volume", "question": "Q1"},
            {"probe_family_id": "po_coverage", "question": "Q2"},
        ],
        "initiative_critiques": [
            {
                "sme_verdict": "probe_first",
                "modelled_saving_3yr": 100,
                "probe_questions": [
                    {"probe_family_id": "transaction_volume", "question": "Q1"},
                ],
            },
            {
                "sme_verdict": "probe_first",
                "modelled_saving_3yr": 50,
                "probe_questions": [
                    {"probe_family_id": "po_coverage", "question": "Q2"},
                ],
            },
        ],
        "critique_summary": {
            "probe_count": 2,
            "ready_count": 0,
            "savings_probe": 150,
            "savings_ready": 0,
            "insufficient_count": 0,
        },
    }
    answers = [{
        "probe_family_id": "transaction_volume",
        "answer": "12 days",
        "applies_to_categories": ["HR"],
    }]
    filtered = filter_sme_critique_with_answers(sme, answers)
    assert len(filtered["portfolio_probes"]) == 1
    assert filtered["portfolio_probes"][0]["probe_family_id"] == "po_coverage"
    assert filtered["critique_summary"]["probe_count"] == 1
    assert filtered["initiative_critiques"][0]["sme_verdict"] == "proceed"
    assert filtered["initiative_critiques"][0].get("evidence_supplemented_by_user") is True


def test_probe_answer_api(client, session_id: str) -> None:
    resp = client.post(
        "/api/v1/chat/probe-answer",
        json={
            "session_id": session_id,
            "probe_family_id": "transaction_volume",
            "question": "What is invoice cycle time across AP?",
            "answer": "Average 12 days, ~800 invoices/month",
            "scope": "portfolio",
            "applies_to_categories": ["HR", "Travel"],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["probe_answer"]["probe_family_id"] == "transaction_volume"
    assert "transaction_volume" in body["answered_probe_families"]
    assert body["response_text"]
    assert load_probe_answers(session_id)[0]["answer"].startswith("Average 12 days")
