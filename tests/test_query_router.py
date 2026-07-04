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
