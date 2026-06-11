"""Deep Research completion → engagement document ingestion (poll endpoint)."""
from __future__ import annotations

import uuid
from unittest.mock import patch


def _fake_completed():
    return {
        "status": "completed",
        "output_text": "## Industry\nDetailed telecom analysis with regulatory context.",
        "sources": [{"title": "TRAI report", "url": "https://example.com/trai"}],
    }


def test_poll_completion_ingests_and_replaces_research_doc(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.engagements_store.ENGAGEMENTS_DIR", tmp_path)
    monkeypatch.setattr("app.routers.enterprise.DEEP_RESEARCH_ENABLED", True)
    monkeypatch.setattr(
        "app.routers.enterprise._summarize_deep_research_llm",
        lambda text: "Condensed summary.",
    )

    from app.routers import enterprise
    from app.routers._shared import read_manifest, write_manifest
    from app.services.document_pipeline import load_cached_markdown
    from app.services.engagements_store import read_engagement_manifest

    sid = str(uuid.uuid4())
    manifest = read_manifest(sid)
    manifest.update(
        {
            "deep_research_company_name": "Acme Corp",
            "deep_research_industry": "telecom",
            "deep_research_annual_revenue_cr": 5_000.0,
            "currency": "INR",
        }
    )
    write_manifest(sid, manifest)

    # First completion creates exactly one research document.
    with patch(
        "app.opar.deep_research_client.poll_deep_research", return_value=_fake_completed()
    ):
        resp1 = enterprise.poll_deep_research_endpoint("interaction-1", session_id=sid)
    assert resp1["status"] == "completed"

    sess = read_manifest(sid)
    eid = sess["engagement_id"]
    first_doc_id = sess["deep_research_document_id"]

    eng = read_engagement_manifest(eid)
    docs = eng.get("documents") or []
    assert len(docs) == 1
    assert docs[0]["document_id"] == first_doc_id
    assert docs[0]["status"] == "ready"
    assert docs[0]["filename"].endswith(".md")

    md = load_cached_markdown(eid, first_doc_id)
    assert "Industry & Business Context Research" in md
    assert "Detailed telecom analysis" in md
    assert "Condensed summary." in md

    # Re-run replaces the prior doc — count stays 1, document_id changes.
    with patch(
        "app.opar.deep_research_client.poll_deep_research", return_value=_fake_completed()
    ):
        enterprise.poll_deep_research_endpoint("interaction-2", session_id=sid)

    sess2 = read_manifest(sid)
    second_doc_id = sess2["deep_research_document_id"]
    assert second_doc_id != first_doc_id

    eng2 = read_engagement_manifest(eid)
    docs2 = eng2.get("documents") or []
    assert len(docs2) == 1
    assert docs2[0]["document_id"] == second_doc_id


def test_poll_in_progress_does_not_ingest(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.engagements_store.ENGAGEMENTS_DIR", tmp_path)
    monkeypatch.setattr("app.routers.enterprise.DEEP_RESEARCH_ENABLED", True)

    from app.routers import enterprise
    from app.routers._shared import read_manifest

    sid = str(uuid.uuid4())
    with patch(
        "app.opar.deep_research_client.poll_deep_research",
        return_value={"status": "in_progress"},
    ):
        resp = enterprise.poll_deep_research_endpoint("interaction-x", session_id=sid)

    assert resp["status"] == "in_progress"
    assert "deep_research_document_id" not in read_manifest(sid)
