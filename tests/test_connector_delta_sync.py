"""Connector delta sync and job queue integration tests."""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from app.services.connector_sync import get_watermark, set_watermark
from app.services.jobs import enqueue_job, get_job, register_job_handler


def test_watermark_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr("app.db.connection.SQLITE_DB_PATH", tmp_path / "test.db")
    from app.db.connection import reset_schema_cache

    reset_schema_cache()
    eid = str(uuid.uuid4())
    assert get_watermark(eid, "ariba_csv") is None
    wm = set_watermark(eid, "ariba_csv", last_sync_at="2025-06-01T00:00:00Z", cursor={"rows": 10})
    assert wm["last_sync_at"] == "2025-06-01T00:00:00Z"
    assert wm["cursor"]["rows"] == 10


def test_job_enqueue_and_complete(tmp_path, monkeypatch):
    monkeypatch.setattr("app.db.connection.SQLITE_DB_PATH", tmp_path / "jobs.db")
    from app.db.connection import reset_schema_cache

    reset_schema_cache()

    def _handler(payload):
        return {"ok": True, "n": payload.get("n")}

    register_job_handler("test_kind", _handler)
    job_id = enqueue_job("test_kind", {"n": 42})

    from app.services.jobs import _claim_next, _complete_job, _HANDLERS

    _HANDLERS["test_kind"] = _handler
    claimed = _claim_next()
    assert claimed is not None
    result = _handler({**claimed["payload"], "_job_id": claimed["id"]})
    _complete_job(claimed["id"], result, failed=False)

    job = get_job(job_id)
    assert job is not None
    assert job["state"] == "done"
    assert job["result"]["n"] == 42


def test_filter_lines_since():
    from app.connectors._since import filter_lines_since
    from app.models import NormalizedSpendLine

    lines = [
        NormalizedSpendLine(
            row_id=1, supplier="A", description="a", amount=1,
            category_id="C1", category_name="Cat1",
            spend_date="2025-01-15", source_record_id="r1", source_file_hash="h",
        ),
        NormalizedSpendLine(
            row_id=2, supplier="B", description="b", amount=2,
            category_id="C2", category_name="Cat2",
            spend_date="2025-06-01", source_record_id="r2", source_file_hash="h",
        ),
    ]
    filtered = filter_lines_since(lines, "2025-05-01T00:00:00Z")
    assert len(filtered) == 1
    assert filtered[0].supplier == "B"


def test_connector_delta_sync_queues_job(client, monkeypatch, tmp_path):
    monkeypatch.setattr("app.db.connection.SQLITE_DB_PATH", tmp_path / "opex.db")
    from app.db.connection import reset_schema_cache

    reset_schema_cache()
    create = client.post(
        "/api/v1/sessions",
        json={"company_name": "Delta Co", "industry": "technology", "annual_revenue": 1e9},
    )
    session_id = create.json()["session_id"]
    resp = client.post(
        "/api/v1/connectors/ariba_csv/ingest",
        json={
            "session_id": session_id,
            "source_file": "missing.csv",
            "delta_sync": True,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "queued"
    assert body["job_id"]
    assert body["delta_sync"] is True
