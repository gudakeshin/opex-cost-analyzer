from __future__ import annotations

import pytest

from app.services.benchmarks import dataset_coverage, sector_pack_detail_payload
from app.services.sector_packs import list_available_packs, pack_file_counts, pack_levers_list


def test_pack_levers_list_reads_levers_key():
    raw = {"levers": [{"lever_id": "a"}, {"lever_id": "b"}]}
    assert len(pack_levers_list(raw)) == 2
    assert pack_levers_list({"sector_specific_levers": [{"lever_id": "c"}]})[0]["lever_id"] == "c"


def test_pack_file_counts_bfsi():
    counts = pack_file_counts("bfsi_banks")
    assert counts["lever_count"] >= 5
    assert counts["kpi_count"] >= 5
    assert counts["peer_count"] >= 5
    assert counts["category_count"] >= 5


def test_sector_pack_detail_payload_full():
    detail = sector_pack_detail_payload("bfsi_banks")
    assert detail is not None
    assert detail["pack_id"] == "bfsi_banks"
    assert len(detail.get("levers", [])) >= 5
    assert len(detail.get("kpi_pack", [])) >= 5
    assert len(detail.get("peers", [])) >= 5
    assert detail.get("taxonomy_extension")
    assert detail.get("regulatory_layer")
    assert "RBI" in detail.get("regulatory_layer", "")
    assert detail.get("benchmark_sources")
    assert detail.get("categories")


def test_dataset_coverage_includes_levers():
    cov = dataset_coverage("sector-pack-bfsi_banks")
    assert cov is not None
    assert cov.get("lever_detail")
    assert len(cov["lever_detail"]) >= 5
    assert cov.get("category_lever_map") is not None
    assert cov.get("lever_count", 0) > 0
    it_software = cov.get("category_detail", {}).get("IT_SOFTWARE", {})
    linked = it_software.get("linked_levers") or []
    assert any("it" in lid.lower() or "software" in lid.lower() for lid in linked) or len(linked) >= 0


def test_list_sector_packs_lever_count(client):
    resp = client.get("/api/v1/sector-packs")
    assert resp.status_code == 200
    packs = {p["pack_id"]: p for p in resp.json()["packs"]}
    assert packs["bfsi_banks"]["lever_count"] > 0


def test_sector_pack_detail_endpoint(client):
    resp = client.get("/api/v1/sector-packs/bfsi_banks/detail")
    assert resp.status_code == 200
    body = resp.json()
    assert body["pack_id"] == "bfsi_banks"
    assert len(body.get("levers", [])) >= 5
    assert body.get("regulatory_layer")


@pytest.mark.parametrize("pack_id,regulator", [
    ("pharma_lifesciences", "CDSCO"),
    ("telecom_infra", "TRAI"),
    ("insurance_general", "IRDAI"),
])
def test_sector_pack_detail_payload_regulatory_layer(pack_id, regulator):
    detail = sector_pack_detail_payload(pack_id)
    assert detail is not None
    assert detail.get("regulatory_layer")
    assert regulator in detail.get("regulatory_layer", "")


@pytest.mark.parametrize("pack_id", list_available_packs())
def test_all_sector_packs_expose_regulatory_layer(pack_id):
    detail = sector_pack_detail_payload(pack_id)
    assert detail is not None
    assert detail.get("regulatory_layer", "").strip()
