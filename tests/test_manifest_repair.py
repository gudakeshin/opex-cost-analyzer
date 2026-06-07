from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.engagements_store import (
    ManifestReadError,
    _MANIFEST_BACKUP_NAME,
    engagement_manifest_path,
    list_engagements,
    read_engagement_manifest,
    repair_engagement_manifest,
    write_engagement_manifest,
)


@pytest.fixture
def client():
    return TestClient(app)


def test_read_engagement_manifest_repairs_trailing_garbage(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.services.engagements_store.ENGAGEMENTS_DIR", tmp_path)
    eid = "71e79e72-2e70-498c-9363-db3f3d52686b"
    eng_dir = tmp_path / eid
    docs_dir = eng_dir / "documents"
    orphan_id = "77d2305a-d3df-4682-a4b7-f49fe51d993b"
    orphan_dir = docs_dir / orphan_id
    orphan_dir.mkdir(parents=True)
    (orphan_dir / "raw.txt").write_text("hello", encoding="utf-8")

    base = {
        "engagement_id": eid,
        "company_name": "Test Co",
        "documents": [],
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
    good = json.dumps(base, indent=2)
    corrupt = good + 'path": "/tmp/orphan/raw.txt", "role": "context_doc"} ] }'
    (eng_dir / "manifest.json").write_text(corrupt, encoding="utf-8")

    manifest = read_engagement_manifest(eid)
    assert manifest["engagement_id"] == eid
    assert len(manifest["documents"]) == 1
    assert manifest["documents"][0]["document_id"] == orphan_id

    repaired = (eng_dir / "manifest.json").read_text(encoding="utf-8")
    json.loads(repaired)


def test_list_engagements_isolates_corrupt_manifest(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.services.engagements_store.ENGAGEMENTS_DIR", tmp_path)

    good_id = str(uuid.uuid4())
    bad_id = str(uuid.uuid4())

    good_dir = tmp_path / good_id
    good_dir.mkdir()
    (good_dir / "documents").mkdir()
    write_engagement_manifest(
        good_id,
        {
            "engagement_id": good_id,
            "company_name": "Healthy Co",
            "industry": "",
            "annual_revenue": 0.0,
            "currency": "INR",
            "created_at": "2026-01-02T00:00:00+00:00",
            "updated_at": "2026-01-02T00:00:00+00:00",
            "session_ids": [],
            "documents": [],
        },
    )

    bad_dir = tmp_path / bad_id
    bad_dir.mkdir()
    (bad_dir / "manifest.json").write_text("{not-json", encoding="utf-8")

    summaries = list_engagements()
    by_id = {row["engagement_id"]: row for row in summaries}
    assert by_id[good_id]["manifest_status"] == "ok"
    assert by_id[good_id]["company_name"] == "Healthy Co"
    assert by_id[bad_id]["manifest_status"] == "corrupt"
    assert by_id[bad_id]["company_name"] == "Unavailable"


def test_manifest_backup_on_write(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.services.engagements_store.ENGAGEMENTS_DIR", tmp_path)
    eid = str(uuid.uuid4())
    eng_dir = tmp_path / eid
    eng_dir.mkdir()
    (eng_dir / "documents").mkdir()

    payload_v1 = {
        "engagement_id": eid,
        "company_name": "Version One",
        "industry": "",
        "annual_revenue": 0.0,
        "currency": "INR",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "session_ids": [],
        "documents": [],
    }
    write_engagement_manifest(eid, payload_v1)

    payload_v2 = {**payload_v1, "company_name": "Version Two", "updated_at": "2026-01-02T00:00:00+00:00"}
    write_engagement_manifest(eid, payload_v2)

    backup_path = engagement_manifest_path(eid).with_name(_MANIFEST_BACKUP_NAME)
    assert backup_path.exists()
    backup = json.loads(backup_path.read_text(encoding="utf-8"))
    assert backup["company_name"] == "Version One"
    current = json.loads(engagement_manifest_path(eid).read_text(encoding="utf-8"))
    assert current["company_name"] == "Version Two"


def test_repair_engagement_manifest_rebuilds_from_disk(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.services.engagements_store.ENGAGEMENTS_DIR", tmp_path)
    eid = str(uuid.uuid4())
    eng_dir = tmp_path / eid
    doc_id = str(uuid.uuid4())
    doc_dir = eng_dir / "documents" / doc_id
    doc_dir.mkdir(parents=True)
    (doc_dir / "raw.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    (eng_dir / "manifest.json").write_text("{broken", encoding="utf-8")

    manifest = repair_engagement_manifest(eid)
    assert manifest["engagement_id"] == eid
    assert len(manifest["documents"]) == 1
    assert manifest["documents"][0]["document_id"] == doc_id


def test_repair_manifest_endpoint(client, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.config.ENGAGEMENTS_DIR", tmp_path)
    monkeypatch.setattr("app.services.engagements_store.ENGAGEMENTS_DIR", tmp_path)

    eid = str(uuid.uuid4())
    eng_dir = tmp_path / eid
    eng_dir.mkdir()
    (eng_dir / "manifest.json").write_text("{broken", encoding="utf-8")

    res = client.post(f"/api/v1/engagements/{eid}/repair-manifest")
    assert res.status_code == 200
    body = res.json()
    assert body["repaired"] is True
    assert body["engagement_id"] == eid
    json.loads((eng_dir / "manifest.json").read_text(encoding="utf-8"))
