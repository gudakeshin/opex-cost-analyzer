"""CRUD + validation for saved what-if scenario sets."""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

pytest.importorskip("duckdb")
pytest.importorskip("pyarrow")

from app.main import app
from app.models import NormalizedSpendLine
from app.services.spend_store import SpendStore, write_document_spend_lines


@pytest.fixture
def client():
    return TestClient(app)


def _line(row_id: int) -> NormalizedSpendLine:
    return NormalizedSpendLine(
        row_id=row_id,
        supplier=f"Vendor {row_id % 5}",
        description=f"Line {row_id}",
        amount=1000.0 + row_id,
        category_id=f"CAT_{row_id % 3}",
        category_name=f"Category {row_id % 3}",
        source_record_id=f"rec-{row_id}",
        source_file_hash="hash",
    )


def _seed_session(monkeypatch, tmp_path, *, with_bridge: bool = True) -> str:
    monkeypatch.setattr("app.services.spend_store.ENGAGEMENTS_DIR", tmp_path)
    sid = str(uuid.uuid4())
    eid = str(uuid.uuid4())
    write_document_spend_lines(eid, "doc-1", [_line(i) for i in range(1, 11)])

    from app.memory import MemoryStore

    record = {
        "session_id": sid,
        "engagement_id": eid,
        "manifest": {"engagement_id": eid, "wacc": 0.1},
        "skill_outputs": {},
    }
    if with_bridge:
        record["skill_outputs"] = {
            "value-bridge-calculator": {
                "confidence_bands": {"low": 80, "mid": 100, "high": 120}
            },
            "savings-modeler": {"initiatives": []},
        }
    MemoryStore().put("session", sid, record)
    monkeypatch.setattr(
        "app.services.spend_base.ensure_spend_store_synced",
        lambda session_id: SpendStore(eid),
    )
    return sid


def test_scenario_set_crud_round_trip(client, monkeypatch, tmp_path):
    sid = _seed_session(monkeypatch, tmp_path)
    payload = {
        "name": "Downside pack",
        "description": "Two downside cases",
        "scenarios": [
            {"name": "soft", "target": "portfolio", "savings_pct_delta": -0.1},
            {"name": "hard", "target": "category", "id": "CAT_0", "savings_pct_delta": -0.2},
        ],
        "drivers": {"execution_rate_pct": 0.7},
    }
    created = client.post(f"/api/v1/sensitivity/{sid}/saved", json=payload)
    assert created.status_code == 200
    body = created.json()
    assert body["name"] == "Downside pack"
    assert body["set_id"]
    assert len(body["scenarios"]) == 2
    assert body["drivers"]["execution_rate_pct"] == pytest.approx(0.7)

    listed = client.get(f"/api/v1/sensitivity/{sid}/saved")
    assert listed.status_code == 200
    sets = listed.json()["sets"]
    assert any(s["set_id"] == body["set_id"] for s in sets)

    deleted = client.delete(f"/api/v1/sensitivity/{sid}/saved/{body['set_id']}")
    assert deleted.status_code == 200
    assert deleted.json()["status"] == "deleted"
    assert not any(
        s["set_id"] == body["set_id"]
        for s in client.get(f"/api/v1/sensitivity/{sid}/saved").json()["sets"]
    )


def test_scenario_set_replace_by_name(client, monkeypatch, tmp_path):
    sid = _seed_session(monkeypatch, tmp_path)
    first = client.post(
        f"/api/v1/sensitivity/{sid}/saved",
        json={
            "name": "Pack A",
            "scenarios": [{"name": "a", "savings_pct_delta": -0.05}],
        },
    ).json()
    second = client.post(
        f"/api/v1/sensitivity/{sid}/saved",
        json={
            "name": "Pack A",
            "scenarios": [
                {"name": "a", "savings_pct_delta": -0.05},
                {"name": "b", "savings_pct_delta": -0.15},
            ],
        },
    ).json()
    assert first["set_id"] != second["set_id"]
    sets = client.get(f"/api/v1/sensitivity/{sid}/saved").json()["sets"]
    named = [s for s in sets if s["name"] == "Pack A"]
    assert len(named) == 1
    assert len(named[0]["scenarios"]) == 2


def test_scenario_set_delete_404(client, monkeypatch, tmp_path):
    sid = _seed_session(monkeypatch, tmp_path)
    resp = client.delete(f"/api/v1/sensitivity/{sid}/saved/{uuid.uuid4()}")
    assert resp.status_code == 404


def test_scenario_set_rejects_empty_scenarios(client, monkeypatch, tmp_path):
    sid = _seed_session(monkeypatch, tmp_path)
    resp = client.post(
        f"/api/v1/sensitivity/{sid}/saved",
        json={"name": "Empty", "scenarios": []},
    )
    assert resp.status_code == 422


def test_scenario_set_rejects_vendor_target(client, monkeypatch, tmp_path):
    sid = _seed_session(monkeypatch, tmp_path)
    resp = client.post(
        f"/api/v1/sensitivity/{sid}/saved",
        json={
            "name": "Bad",
            "scenarios": [{"name": "v", "target": "vendor", "id": "V1"}],
        },
    )
    assert resp.status_code == 422
    assert "portfolio" in resp.json()["detail"].lower() or "category" in resp.json()["detail"].lower()


def test_custom_sensitivity_rejects_vendor_target(client, monkeypatch, tmp_path):
    sid = _seed_session(monkeypatch, tmp_path)
    resp = client.post(
        "/api/v1/sensitivity/custom",
        json={
            "session_id": sid,
            "scenarios": [{"name": "vendor hit", "target": "vendor", "id": "V1"}],
        },
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert "vendor" in str(detail).lower() or "unsupported" in str(detail).lower()


def test_custom_sensitivity_accepts_lever_target(client, monkeypatch, tmp_path):
    sid = _seed_session(monkeypatch, tmp_path)
    from app.memory import MemoryStore

    record = MemoryStore().get("session", sid)
    record["skill_outputs"] = {
        "value-bridge-calculator": {
            "confidence_bands": {"low": 80, "mid": 100, "high": 120}
        },
        "savings-modeler": {
            "initiatives": [
                {
                    "lever": "license_rightsizing",
                    "lever_name": "License Rightsizing",
                    "category_id": "IT",
                    "net_savings": {"total_3yr": 40.0},
                },
                {
                    "lever": "carrier_consolidation",
                    "category_id": "TRAVEL",
                    "net_savings": {"total_3yr": 60.0},
                },
            ]
        },
    }
    MemoryStore().put("session", sid, record)

    resp = client.post(
        "/api/v1/sensitivity/custom",
        json={
            "session_id": sid,
            "scenarios": [
                {
                    "name": "license cut",
                    "target": "lever",
                    "id": "license_rightsizing",
                    "savings_pct_delta": -0.5,
                }
            ],
        },
    )
    assert resp.status_code == 200, resp.text
    custom = next(s for s in resp.json()["scenarios"] if s.get("custom"))
    assert custom["target"] == "lever"
    assert custom["target_id"] == "license_rightsizing"
    # mid=100, lever share=40 → adjusted = 100 - 40 + 40*0.5 = 80; * base exec (~1)
    assert custom["savings_3yr"] == pytest.approx(80.0, rel=0.05)


def test_base_npv_falls_back_to_mid_band_without_phased_savings():
    """Base NPV must not collapse to 0 when the savings model has no initiatives —
    every Δ-vs-base comparison in the What-If UI would be meaningless."""
    from app.services.sensitivity import compute_sensitivity

    result = compute_sensitivity(
        {"confidence_bands": {"low": 80, "mid": 100, "high": 120}},
        savings_model={"initiatives": []},
        discount_rate=0.10,
    )
    base = next(s for s in result["scenarios"] if s["name"] == "base")
    assert base["npv_pretax"] > 0
    # Annuity of mid/3 per year over 3 years at 10% ≈ 82.9
    assert base["npv_pretax"] == pytest.approx(82.9, rel=0.01)
    assert base["npv_aftertax"] == base["npv_pretax"]  # tax defaults to 0
