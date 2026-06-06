"""Connector ingest API and registry tests."""
from __future__ import annotations

from pathlib import Path

import pytest

import uuid

from app.routers._shared import read_manifest, write_manifest
from app.services.connector_registry import CONNECTOR_REGISTRY, list_connectors
from app.services.connector_ingest import ingest_via_connector


def _sample_ariba_csv() -> str:
    return (
        "InvoiceNumber,SupplierName,InvoiceAmount,InvoiceCurrency,InvoiceDate,"
        "CommodityDescription,CommodityCode,CostCenter\n"
        "INV-001,Infosys Ltd,500000,INR,2024-06-15,Cloud services,IT_CLOUD,CC-101\n"
        "INV-002,AWS India,250000,INR,2024-06-20,Infrastructure,IT_CLOUD,CC-102\n"
    )


def test_list_connectors_includes_six_types() -> None:
    types = {c["type"] for c in list_connectors()}
    assert types == set(CONNECTOR_REGISTRY.keys())


def test_connector_ingest_ariba_csv(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.routers._shared.UPLOAD_DIR", tmp_path)

    session_id = str(uuid.uuid4())
    sdir = tmp_path / session_id
    sdir.mkdir(parents=True)
    source = sdir / "ariba_export.csv"
    source.write_text(_sample_ariba_csv(), encoding="utf-8")
    write_manifest(session_id, {"session_id": session_id, "files": [], "industry": "technology", "annual_revenue": 1e9, "currency": "INR"})

    result = ingest_via_connector(session_id, "ariba_csv", source_file="ariba_export.csv")
    assert result["row_count"] == 2
    manifest = read_manifest(session_id)
    assert len(manifest.get("connector_ingests", [])) == 1
    normalized = sdir / result["normalized_file"]
    assert normalized.exists()


def test_connector_ingest_api(client) -> None:
    create = client.post(
        "/api/v1/sessions",
        json={"company_name": "Connector Co", "industry": "technology", "annual_revenue": 500_000_000, "currency": "INR"},
    )
    assert create.status_code == 200
    session_id = create.json()["session_id"]

    up = client.post(
        f"/api/v1/upload/{session_id}",
        files={"file": ("ariba_export.csv", _sample_ariba_csv(), "text/csv")},
    )
    assert up.status_code == 200

    resp = client.post(
        "/api/v1/connectors/ariba_csv/ingest",
        json={"session_id": session_id, "source_file": "ariba_export.csv"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["row_count"] == 2
    assert body["connector_type"] == "ariba_csv"


def test_connector_ingest_unknown_type_returns_400(client) -> None:
    create = client.post("/api/v1/sessions", json={"company_name": "X", "industry": "tech", "annual_revenue": 1e9})
    session_id = create.json()["session_id"]
    resp = client.post(
        "/api/v1/connectors/not_a_connector/ingest",
        json={"session_id": session_id, "source_file": "missing.csv"},
    )
    assert resp.status_code == 400


def test_get_connectors_endpoint(client) -> None:
    resp = client.get("/api/v1/connectors")
    assert resp.status_code == 200
    assert len(resp.json()["connectors"]) == 6
