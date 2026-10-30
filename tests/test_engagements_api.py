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
    # Backend-agnostic: read through the store (json files or sqlite rows).
    from app.services.engagements_store import read_engagement_manifest

    manifest = read_engagement_manifest(eid)
    assert body["session_id"] in manifest.get("session_ids", [])


def test_search_engagements_by_company_name(client, tmp_path, monkeypatch):
    _patch_engagements_dir(monkeypatch, tmp_path)
    client.post("/api/v1/engagements", json={"company_name": "Alpha Retail"})
    client.post("/api/v1/engagements", json={"company_name": "Beta Telecom", "industry": "telecom_infra"})

    all_rows = client.get("/api/v1/engagements")
    assert all_rows.status_code == 200
    assert len(all_rows.json()) == 2

    filtered = client.get("/api/v1/engagements", params={"q": "telecom"})
    assert filtered.status_code == 200
    names = {row["company_name"] for row in filtered.json()}
    assert names == {"Beta Telecom"}

    legacy = client.get("/api/engagements", params={"q": "alpha"})
    assert legacy.status_code == 200
    assert len(legacy.json()) == 1
    assert legacy.json()[0]["company_name"] == "Alpha Retail"


def test_delete_engagement(client, tmp_path, monkeypatch):
    _patch_engagements_dir(monkeypatch, tmp_path)
    res = client.post("/api/v1/engagements", json={"company_name": "Delete Me Co"})
    eid = res.json()["engagement_id"]

    deleted = client.delete(f"/api/v1/engagements/{eid}")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] == eid

    listing = client.get("/api/v1/engagements")
    assert all(row["engagement_id"] != eid for row in listing.json())

    gone = client.get(f"/api/v1/engagements/{eid}")
    assert gone.status_code == 404


def test_duplicate_upload_is_rejected_unless_allowed(client, tmp_path, monkeypatch):
    _patch_engagements_dir(monkeypatch, tmp_path)
    eid = client.post(
        "/api/v1/engagements",
        json={"company_name": "Dup Co", "industry": "it_ites", "annual_revenue": 1e9, "currency": "INR"},
    ).json()["engagement_id"]
    body = b"supplier,description,amount\nAcme,Cloud services,100000\n"

    def _upload(**params):
        return client.post(
            f"/api/v1/engagements/{eid}/documents",
            files={"file": ("ledger.csv", body, "text/csv")},
            params=params,
        )

    assert _upload().status_code == 200
    dup = _upload()
    assert dup.status_code == 409
    assert "already uploaded" in dup.json()["detail"]
    assert _upload(allow_duplicate="true").status_code == 200


def test_ingest_warnings_reach_the_analysis_corpus(client, tmp_path, monkeypatch):
    _patch_engagements_dir(monkeypatch, tmp_path)
    eid = client.post(
        "/api/v1/engagements",
        json={"company_name": "Messy Co", "industry": "it_ites", "annual_revenue": 1e9, "currency": "INR"},
    ).json()["engagement_id"]
    body = (
        b"supplier,description,amount,currency\n"
        b"Acme,cloud hosting,100000,INR\n"
        b"Beta,freight charges,45000 Cr,INR\n"
        b"Gamma,software licences,300,USD\n"
    )
    assert client.post(
        f"/api/v1/engagements/{eid}/documents", files={"file": ("m.csv", body, "text/csv")}
    ).status_code == 200

    from app.services.engagement_corpus import load_engagement_corpus

    _, _, reports, _ = load_engagement_corpus(eid)
    assert len(reports) == 1
    joined = " ".join(reports[0].get("warnings") or [])
    assert "could not be read" in joined and "FX rate" in joined
    assert reports[0]["quality"]["rows_dropped_unparseable_amount"] == 1


def test_column_mapping_is_reported_and_can_be_overridden(client, tmp_path, monkeypatch):
    _patch_engagements_dir(monkeypatch, tmp_path)
    eid = client.post(
        "/api/v1/engagements",
        json={"company_name": "Map Co", "industry": "it_ites", "annual_revenue": 1e9, "currency": "INR"},
    ).json()["engagement_id"]
    # "Vendor Name" matches supplier; "Notes" holds the real supplier names
    body = b"Vendor Name,Notes,Details,Value\nV-001,Acme Cloud,cloud hosting,1000\nV-002,Beta Freight,freight charges,2000\n"
    doc = client.post(f"/api/v1/engagements/{eid}/documents", files={"file": ("m.csv", body, "text/csv")}).json()["document"]
    did = doc["document_id"]

    q = client.get(f"/api/v1/engagements/{eid}/documents/{did}/ingestion-report").json()["report"]["quality"]
    assert q["column_mapping"]["supplier"] == {"column": "Vendor Name", "match": "partial"}
    assert "Notes" in q["unmapped_columns"] and "Notes" in q["available_columns"]
    assert any("Column mapping" in w for w in client.get(
        f"/api/v1/engagements/{eid}/documents/{did}/ingestion-report").json()["report"]["warnings"])

    bad = client.post(f"/api/v1/engagements/{eid}/documents/{did}/reprocess", json={"column_overrides": {"nope": "Notes"}})
    assert bad.status_code == 422

    ok = client.post(f"/api/v1/engagements/{eid}/documents/{did}/reprocess", json={"column_overrides": {"supplier": "Notes"}})
    assert ok.status_code == 200
    out = client.get(f"/api/v1/engagements/{eid}/documents/{did}/ingestion-report").json()
    assert out["column_overrides"] == {"supplier": "Notes"}
    assert out["report"]["quality"]["column_mapping"]["supplier"] == {"column": "Notes", "match": "manual"}


def test_errors_carry_a_machine_readable_code(client):
    missing = client.get("/api/v1/engagements/00000000-0000-4000-8000-000000000000")
    assert missing.status_code == 404
    assert missing.json()["code"] == "not_found" and missing.json()["detail"]

    invalid = client.post("/api/v1/engagements", json={"annual_revenue": "not a number"})
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "validation_error" and isinstance(invalid.json()["detail"], list)


def test_specific_error_codes(client, tmp_path, monkeypatch):
    _patch_engagements_dir(monkeypatch, tmp_path)
    eid = client.post("/api/v1/engagements", json={"company_name": "Code Co", "currency": "INR"}).json()["engagement_id"]
    body = b"supplier,description,amount\nAcme,Cloud,100\n"
    client.post(f"/api/v1/engagements/{eid}/documents", files={"file": ("a.csv", body, "text/csv")})
    dup = client.post(f"/api/v1/engagements/{eid}/documents", files={"file": ("a.csv", body, "text/csv")})
    assert dup.status_code == 409 and dup.json()["code"] == "duplicate_upload"


def test_engagement_list_supports_paging_and_reports_the_total(client, tmp_path, monkeypatch):
    _patch_engagements_dir(monkeypatch, tmp_path)
    for i in range(3):
        client.post("/api/v1/engagements", json={"company_name": f"Page Co {i}", "currency": "INR"})
    everything = client.get("/api/v1/engagements")
    assert everything.status_code == 200
    total = int(everything.headers["X-Total-Count"])
    assert total >= 3 and len(everything.json()) == total
    page = client.get("/api/v1/engagements", params={"limit": 2, "offset": 1})
    assert len(page.json()) == 2 and page.headers["X-Total-Count"] == str(total)
    assert client.get("/api/v1/engagements", params={"limit": 0}).status_code == 422
    assert client.get("/api/v1/sessions", params={"limit": 1}).status_code == 200


def test_gl_mapping_classifies_by_account_code(client, tmp_path, monkeypatch):
    _patch_engagements_dir(monkeypatch, tmp_path)
    eid = client.post("/api/v1/engagements", json={"company_name": "GL Co", "currency": "INR"}).json()["engagement_id"]
    # descriptions carry no keyword signal, so without a mapping every line falls to OTHER
    body = b"supplier,description,amount,gl_code\nAcme,misc item,1000,4100\nBeta,misc item,2000,5200\n"
    did = client.post(f"/api/v1/engagements/{eid}/documents", files={"file": ("gl.csv", body, "text/csv")}).json()[
        "document"
    ]["document_id"]

    from app.services.document_pipeline import load_cached_spend_lines

    assert {l.category_id for l in load_cached_spend_lines(eid, did)} == {"OTHER"}

    bad = client.put(f"/api/v1/engagements/{eid}/gl-mapping", json={"ranges": [{"from": 5, "to": 1, "category_id": "IT"}]})
    assert bad.status_code == 422 and bad.json()["code"] == "invalid_gl_mapping"
    unknown = client.put(f"/api/v1/engagements/{eid}/gl-mapping", json={"ranges": [{"from": 1, "to": 2, "category_id": "NOPE"}]})
    assert unknown.status_code == 422

    ok = client.put(
        f"/api/v1/engagements/{eid}/gl-mapping",
        json={"ranges": [{"from": 4000, "to": 4999, "category_id": "IT"}, {"from": 5000, "to": 5999, "category_id": "TRAVEL"}]},
    )
    assert ok.status_code == 200 and len(client.get(f"/api/v1/engagements/{eid}/gl-mapping").json()["ranges"]) == 2

    assert client.post(f"/api/v1/engagements/{eid}/documents/{did}/reprocess").status_code == 200
    by_supplier = {l.supplier: l.category_id for l in load_cached_spend_lines(eid, did)}
    assert by_supplier == {"Acme": "IT", "Beta": "TRAVEL"}
