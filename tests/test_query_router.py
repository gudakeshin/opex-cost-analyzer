"""Integration tests for the ad-hoc query router."""
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


def test_query_router_rejects_multi_statement(client, monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.spend_store.ENGAGEMENTS_DIR", tmp_path)
    sid = str(uuid.uuid4())
    eid = str(uuid.uuid4())
    write_document_spend_lines(eid, "doc-1", [_line(i) for i in range(1, 11)])

    # Seed a minimal session the owner check can resolve (auth may be off in tests).
    from app.memory import MemoryStore

    MemoryStore().put(
        "session",
        sid,
        {"session_id": sid, "engagement_id": eid, "manifest": {"engagement_id": eid}},
    )
    monkeypatch.setattr(
        "app.services.spend_base.ensure_spend_store_synced",
        lambda session_id: SpendStore(eid),
    )

    resp = client.post(
        f"/api/v1/query/{sid}",
        json={"sql": "SELECT 1; SELECT 2"},
    )
    assert resp.status_code == 422


def test_query_schema_endpoint(client, monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.spend_store.ENGAGEMENTS_DIR", tmp_path)
    sid = str(uuid.uuid4())
    eid = str(uuid.uuid4())
    write_document_spend_lines(eid, "doc-1", [_line(i) for i in range(1, 21)])

    from app.memory import MemoryStore

    MemoryStore().put(
        "session",
        sid,
        {"session_id": sid, "engagement_id": eid, "manifest": {"engagement_id": eid}},
    )
    monkeypatch.setattr(
        "app.services.spend_base.ensure_spend_store_synced",
        lambda session_id: SpendStore(eid),
    )

    resp = client.get(f"/api/v1/query/{sid}/schema")
    assert resp.status_code == 200
    body = resp.json()
    assert body["line_count"] == 20
    assert "spend" in body["views"]


def _seed_session(monkeypatch, tmp_path, n_lines: int = 10) -> str:
    monkeypatch.setattr("app.services.spend_store.ENGAGEMENTS_DIR", tmp_path)
    sid = str(uuid.uuid4())
    eid = str(uuid.uuid4())
    write_document_spend_lines(eid, "doc-1", [_line(i) for i in range(1, n_lines + 1)])

    from app.memory import MemoryStore

    MemoryStore().put(
        "session",
        sid,
        {"session_id": sid, "engagement_id": eid, "manifest": {"engagement_id": eid}},
    )
    monkeypatch.setattr(
        "app.services.spend_base.ensure_spend_store_synced",
        lambda session_id: SpendStore(eid),
    )
    return sid


def test_nl2sql_rules_path_executes_with_chart_and_audit(client, monkeypatch, tmp_path):
    sid = _seed_session(monkeypatch, tmp_path)
    from unittest.mock import patch as mock_patch

    with mock_patch("app.routers.query.append_audit_event") as audit:
        resp = client.post(
            f"/api/v1/query/{sid}/nl2sql",
            json={"question": "top 3 suppliers by spend", "execute": True},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "rules"
    assert "GROUP BY supplier" in body["sql"]
    assert body["result"]["row_count"] >= 1
    assert body["chart"] is not None and body["chart"]["x_key"] == "supplier"
    assert body["provenance"]["prompt_hash"]
    assert any("nl2sql" in str(c.args[0]) for c in audit.call_args_list)


def test_nl2sql_review_gate_does_not_execute(client, monkeypatch, tmp_path):
    sid = _seed_session(monkeypatch, tmp_path)
    resp = client.post(
        f"/api/v1/query/{sid}/nl2sql",
        json={"question": "top 3 suppliers by spend"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["sql"] and body["result"] is None


def test_nl2sql_unavailable_without_llm(client, monkeypatch, tmp_path):
    # Complex question misses the rules tier; under pytest the LLM is inert.
    sid = _seed_session(monkeypatch, tmp_path)
    resp = client.post(
        f"/api/v1/query/{sid}/nl2sql",
        json={"question": "vendors where spend grew > 20% QoQ", "execute": True},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "unavailable"
    assert body["sql"] is None


def test_nl2sql_rejects_dml_from_llm(client, monkeypatch, tmp_path):
    sid = _seed_session(monkeypatch, tmp_path)
    from unittest.mock import patch as mock_patch

    with mock_patch(
        "app.opar.tools.nl_query._llm_aggregate_or_sql", return_value="DROP TABLE spend"
    ):
        resp = client.post(
            f"/api/v1/query/{sid}/nl2sql",
            json={"question": "vendors where spend grew > 20% QoQ"},
        )
    assert resp.status_code == 422


def test_sensitivity_parse_before_any_analysis_run(client, monkeypatch, tmp_path):
    """No 'session'-scope analysis record yet (fresh session, only /api/v1/sessions
    registration) — engagement_id must resolve via _session_engagement_id, not crash
    ObserveContext with None."""
    monkeypatch.setattr("app.services.spend_store.ENGAGEMENTS_DIR", tmp_path)
    sid = str(uuid.uuid4())
    eid = str(uuid.uuid4())
    from app.routers._shared import write_manifest

    write_manifest(sid, {"session_id": sid, "engagement_id": eid})

    resp = client.post(
        "/api/v1/sensitivity/parse",
        json={"session_id": sid, "question": "what if execution drops to 60%"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["parse_source"] == "regex"
    assert body["drivers"].get("execution_rate_pct") == pytest.approx(0.6)


def test_sensitivity_parse_regex_path(client, monkeypatch, tmp_path):
    sid = _seed_session(monkeypatch, tmp_path)
    from app.memory import MemoryStore

    record = MemoryStore().get("session", sid)
    record["skill_outputs"] = {
        "spend-profiler": {
            "category_profile": [
                {"category_id": "FAC", "category_name": "Facilities"},
            ],
        },
    }
    MemoryStore().put("session", sid, record)

    resp = client.post(
        "/api/v1/sensitivity/parse",
        json={
            "session_id": sid,
            "question": "What if Facilities savings drop 20% and timeline slips 1.5x with high bounce-back?",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["parse_source"] == "regex"  # LLM inert under pytest
    assert body["scenarios"], body
    scen = body["scenarios"][0]
    assert scen["target"] == "category" and scen["id"] == "FAC"
    assert scen["savings_pct_delta"] == pytest.approx(-0.20)
    assert scen["timeline_factor"] == pytest.approx(1.5)
    assert scen["bounce_back_override"] == "high"
    assert body["known_categories"]


def test_custom_sensitivity_accepts_drivers(client, monkeypatch, tmp_path):
    sid = _seed_session(monkeypatch, tmp_path)
    from app.memory import MemoryStore

    record = MemoryStore().get("session", sid)
    record["skill_outputs"] = {
        "value-bridge-calculator": {"confidence_bands": {"low": 80, "mid": 100, "high": 120}},
        "savings-modeler": {"initiatives": []},
    }
    record["manifest"] = {"engagement_id": record["engagement_id"], "wacc": 0.1}
    MemoryStore().put("session", sid, record)

    resp = client.post(
        "/api/v1/sensitivity/custom",
        json={
            "session_id": sid,
            "scenarios": [{"name": "downside", "savings_pct_delta": -0.2}],
            "drivers": {"execution_rate_pct": 0.6},
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "scenarios" in body


def test_manual_query_chart_flag(client, monkeypatch, tmp_path):
    sid = _seed_session(monkeypatch, tmp_path)
    resp = client.post(
        f"/api/v1/query/{sid}?chart=true",
        json={"sql": "SELECT supplier, SUM(amount) AS spend FROM spend GROUP BY supplier"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["chart"] is not None
    assert body["chart"]["type"] == "bar"
