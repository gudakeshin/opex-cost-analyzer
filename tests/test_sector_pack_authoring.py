"""Tests for sector pack authoring service and API."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from app.config import ROOT_DIR
from app.services.lever_runtime_sync import RUNTIME_DIR
from app.services.sector_pack_authoring import (
    SectorPackAuthoringError,
    create_pack,
    publish_pack,
    validate_component,
    validate_pack_id,
    write_component,
)
from app.services.sector_packs import _load_pack_cached, load_pack, run_regression_test


@pytest.fixture
def packs_root(tmp_path, monkeypatch):
    stub = tmp_path / "sector_packs"
    stub.mkdir()
    runtime = tmp_path / "skills" / "sector-packs"
    runtime.mkdir(parents=True)

    monkeypatch.setattr("app.services.sector_packs._SECTOR_PACKS_ROOT", stub)
    monkeypatch.setattr("app.services.sector_pack_authoring._SECTOR_PACKS_ROOT", stub)
    monkeypatch.setattr("app.services.lever_runtime_sync.STUB_DIR", stub)
    monkeypatch.setattr("app.services.lever_runtime_sync.RUNTIME_DIR", runtime)
    monkeypatch.setattr("app.services.sector_pack_authoring.RUNTIME_DIR", runtime)
    _load_pack_cached.cache_clear()
    return {"stub": stub, "runtime": runtime}


def test_validate_pack_id_rejects_traversal():
    with pytest.raises(SectorPackAuthoringError):
        validate_pack_id("../escape")


def test_create_scaffold_passes_regression(packs_root):
    create_pack("test_scaffold", sector="Test Sector")
    result = run_regression_test("test_scaffold")
    assert result["passed"] is True


def test_update_peers_component(packs_root):
    create_pack("peer_pack", sector="Peers Test")
    peers = json.loads((packs_root["stub"] / "peer_pack" / "peer_set.json").read_text())
    peers["peers"].append({
        "name": "Second Peer",
        "ticker": "SEC.NS",
        "exchange": "NSE",
        "entity_type": "listed_company",
        "revenue_cr": 500,
    })
    write_component("peer_pack", "peers", peers)
    loaded = load_pack("peer_pack")
    assert len(loaded["peer_set"]["peers"]) == 2


def test_invalid_lever_payload_rejected(packs_root):
    create_pack("bad_lever", sector="Bad Lever")
    with pytest.raises(SectorPackAuthoringError):
        write_component("bad_lever", "levers", {"levers": [{"lever_id": "x"}]})


def test_manifest_version_immutable_via_component_update(packs_root):
    create_pack("ver_lock", sector="Version Lock")
    manifest = yaml.safe_load((packs_root["stub"] / "ver_lock" / "pack_manifest.yaml").read_text())
    manifest["version"] = "9.9"
    with pytest.raises(SectorPackAuthoringError, match="version can only change via publish"):
        write_component("ver_lock", "manifest", manifest)


def test_cache_invalidated_after_write(packs_root):
    create_pack("cache_pack", sector="Cache")
    before = load_pack("cache_pack")
    manifest = dict(before["manifest"])
    manifest["description"] = "Updated description"
    write_component("cache_pack", "manifest", manifest)
    after = load_pack("cache_pack")
    assert after["manifest"]["description"] == "Updated description"


def test_publish_bumps_version(packs_root):
    create_pack("pub_pack", sector="Publish")
    out = publish_pack("pub_pack", bump="minor")
    assert out["prior_version"] == "0.1"
    assert out["version"] == "0.2"
    manifest = yaml.safe_load((packs_root["stub"] / "pub_pack" / "pack_manifest.yaml").read_text())
    assert manifest["version"] == "0.2"


def test_lever_write_triggers_runtime_sync(packs_root, monkeypatch):
    create_pack("sync_pack", sector="Sync")
    runtime_path = packs_root["runtime"] / "sync_pack" / "sector_levers.json"
    assert runtime_path.exists()

    levers = {
        "sector": "sync_pack",
        "source_type": "test",
        "levers": [
            {
                "lever_id": "test_lever",
                "lever_name": "Test Lever",
                "category_ids": ["sync_pack_core"],
                "p10_pct": 1.0,
                "p50_pct": 3.0,
                "p90_pct": 5.0,
                "implementation_weeks": 8,
                "savings_type": "run_rate",
            }
        ],
    }
    write_component("sync_pack", "levers", levers)
    runtime = json.loads(runtime_path.read_text())
    # runtime sync only adds levers when benchmark categories intersect stub categories
    assert "sector_specific_levers" in runtime


def test_create_pack_api(client, packs_root, monkeypatch):
    monkeypatch.setattr(
        "app.routers.sector_pack_admin.create_pack",
        lambda pack_id, sector, description="": {
            "pack_id": pack_id,
            "status": "scaffold",
            "version": "0.1",
        },
    )
    resp = client.post(
        "/api/v1/sector-packs",
        json={"pack_id": "api_test", "sector": "API Test"},
    )
    assert resp.status_code == 200
    assert resp.json()["pack_id"] == "api_test"


def test_component_update_api(client, packs_root):
    create_pack("api_comp", sector="API Component")
    taxonomy = json.loads((packs_root["stub"] / "api_comp" / "taxonomy_extension.json").read_text())
    resp = client.put(
        "/api/v1/sector-packs/api_comp/components/taxonomy",
        json={"payload": taxonomy},
    )
    assert resp.status_code == 200
    assert resp.json()["component"] == "taxonomy"
