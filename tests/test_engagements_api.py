"""Engagement and document API tests."""
from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
@pytest.fixture
def client():
    return TestClient(app)


def _patch_engagements_dir(monkeypatch, tmp_path):
    eng_dir = tmp_path / "engagements"
    eng_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("app.config.ENGAGEMENTS_DIR", eng_dir)
    monkeypatch.setattr("app.services.engagements_store.ENGAGEMENTS_DIR", eng_dir)
    return eng_dir


def test_create_engagement_and_upload_csv(client, tmp_path, monkeypatch):
    _patch_engagements_dir(monkeypatch, tmp_path)

    res = client.post(
        "/api/v1/engagements",
        json={"company_name": "Test Co", "industry": "it_ites", "annual_revenue": 1e9, "currency": "INR"},
    )
    assert res.status_code == 200
    eid = res.json()["engagement_id"]
    assert uuid.UUID(eid).version == 4

    csv_content = (
        "supplier,description,amount,category,spend_date\n"
        "Acme Corp,Cloud services,100000,IT & Cloud,2024-01-15\n"
    ).encode()
    upload = client.post(
        f"/api/v1/engagements/{eid}/documents",
        files={"file": ("spend.csv", csv_content, "text/csv")},
    )
    assert upload.status_code == 200
    doc_id = upload.json()["document"]["document_id"]

    import time
    for _ in range(30):
        listing = client.get(f"/api/v1/engagements/{eid}/documents")
        docs = listing.json()["documents"]
        if docs and docs[0].get("status") == "ready":
            break
        time.sleep(0.2)
    else:
        pytest.fail("document did not reach ready status")

    detail = client.get(f"/api/v1/engagements/{eid}/documents/{doc_id}")
    assert detail.status_code == 200
    assert detail.json()["document"]["line_count"] >= 1


def test_session_links_engagement(client, monkeypatch, tmp_path):
    eng_dir = _patch_engagements_dir(monkeypatch, tmp_path)
    eng = client.post("/api/v1/engagements", json={"company_name": "Linked Co"})
    eid = eng.json()["engagement_id"]
    sess = client.post("/api/v1/sessions", json={"engagement_id": eid, "company_name": "Linked Co"})
    assert sess.status_code == 200
    body = sess.json()
    assert body["engagement_id"] == eid
    manifest_path = eng_dir / eid / "manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text())
    assert body["session_id"] in manifest.get("session_ids", [])
