"""End-to-end coverage for features reconnected in the gap-remediation pass:
strategic skills in the core pipeline, board-deck / CFO-brief / MOR-pack endpoints,
and the calibration + teardown-plan endpoints.
"""
from __future__ import annotations

import uuid

from app.models import NormalizedSpendLine
from app.services.analysis import run_core_pipeline

_NEW_STRATEGIC_SKILLS = [
    "assumption-register",
    "scenario-modeler",
    "value-to-shareholder-bridge",
    "brsr-cobenefit-calculator",
    "peer-disclosure-miner",
]


def _lines() -> list[NormalizedSpendLine]:
    rows = [
        ("Infosys", "IT managed services", 12_000_000, "IT_SERVICES", "IT Services", "actual"),
        ("Infosys", "IT managed services budget", 10_000_000, "IT_SERVICES", "IT Services", "budget"),
        ("Advisory LLP", "Management consulting", 8_000_000, "PROF_SERVICES", "Professional Services", "actual"),
        ("Realty Co", "Office lease", 6_500_000, "FACILITIES", "Facilities & Real Estate", "actual"),
        ("TravelDesk India", "Corporate travel", 3_000_000, "TRAVEL", "Travel & Entertainment", "actual"),
    ]
    return [
        NormalizedSpendLine(
            row_id=i, supplier=s, description=d, amount=a, category_id=c,
            category_name=n, amount_type=t, spend_date="2025-06-15", payment_terms_days=30,
        )
        for i, (s, d, a, c, n, t) in enumerate(rows, start=1)
    ]


def test_core_pipeline_now_emits_strategic_skills() -> None:
    sid = str(uuid.uuid4())
    state = run_core_pipeline(
        sid, _lines(), [], "technology", 500_000_000,
        company_name="Test Co", reporting_currency="INR",
    )
    outputs = state["skill_outputs"]
    for skill in _NEW_STRATEGIC_SKILLS:
        assert skill in outputs, f"{skill} missing from core pipeline outputs"
        assert isinstance(outputs[skill], dict) and outputs[skill], f"{skill} produced empty output"


def _seed_session(client) -> str:
    create = client.post(
        "/api/v1/sessions",
        json={"company_name": "Test Co", "industry": "technology",
              "annual_revenue": 500_000_000, "currency": "INR"},
    )
    assert create.status_code == 200
    sid = create.json()["session_id"]
    run_core_pipeline(sid, _lines(), [], "technology", 500_000_000,
                      company_name="Test Co", reporting_currency="INR")
    return sid


def test_board_deck_cfo_brief_mor_endpoints(client) -> None:
    sid = _seed_session(client)
    for path, key in [("board-deck", "board_deck"), ("cfo-brief", "cfo_brief"), ("mor-pack", "mor_pack")]:
        resp = client.post(f"/api/v1/{path}/{sid}")
        assert resp.status_code == 200, (path, resp.text)
        body = resp.json()
        assert key in body
        assert body["export_url"].startswith("/api/exports/")
        # the export file is downloadable
        dl = client.get(body["export_url"])
        assert dl.status_code == 200


def test_board_deck_missing_session_returns_404(client) -> None:
    resp = client.post(f"/api/v1/board-deck/{uuid.uuid4()}")
    assert resp.status_code == 404


def test_calibration_ingest_and_report(client) -> None:
    eng = f"eng-{uuid.uuid4().hex[:8]}"
    rec = {
        "initiative_id": "INI-1", "lever_id": "vendor_consolidation", "pack_id": "it_ites",
        "planned_p50_cr": 2.0, "realised_cr": 1.6, "realised_date": "2026-01-31",
        "data_source": "finance_sign_off",
    }
    ing = client.post(f"/api/v1/calibration/{eng}/realised", json={"records": [rec]})
    assert ing.status_code == 200
    assert ing.json()["records_ingested"] == 1
    rep = client.get(f"/api/v1/calibration/{eng}/report")
    assert rep.status_code == 200
    body = rep.json()
    assert body["engagement_id"] == eng
    assert body["overall_realisation_rate"] > 0


def test_teardown_plan_endpoint(client) -> None:
    plan = client.get(f"/api/v1/engagement/eng-{uuid.uuid4().hex[:8]}/teardown-plan")
    assert plan.status_code == 200
    step_ids = {s["step_id"] for s in plan.json()["steps"]}
    assert {"dlp_checklist", "calibration_export"}.issubset(step_ids)
