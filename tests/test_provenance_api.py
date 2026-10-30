"""Tests for GET /api/v1/provenance/{engagement_id}/{turn_id}."""
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.main import app
from app.opar.provenance import build_provenance_tag, save_snapshot, tag_narrative

client = TestClient(app)


def test_provenance_snapshot_endpoint_returns_sentences() -> None:
    eid, tid = f"test-eng-prov-{uuid.uuid4().hex[:8]}", f"test-turn-prov-{uuid.uuid4().hex[:8]}"
    tag = build_provenance_tag(
        ["peer-benchmarker", "savings-modeler"],
        "prompt body",
        "deterministic-composer",
    )
    tagged = tag_narrative("First sentence. Second sentence.", tag)
    save_snapshot(eid, tid, tagged)

    res = client.get(f"/api/v1/provenance/{eid}/{tid}")
    assert res.status_code == 200
    body = res.json()
    assert body["engagement_id"] == eid
    assert body["turn_id"] == tid
    assert body["sentence_count"] == 2
    assert body["sentences"][0]["provenance"]["data_slice"] == [
        "peer-benchmarker",
        "savings-modeler",
    ]


def test_provenance_snapshot_404_when_missing() -> None:
    res = client.get("/api/v1/provenance/missing-eng/missing-turn")
    assert res.status_code == 404
