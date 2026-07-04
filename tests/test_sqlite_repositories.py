"""tests/test_sqlite_repositories.py — SqliteSessionRepository / SqliteEngagementRepository.

Mirrors tests/test_repositories.py's contract for the JSON backend, plus
coverage for the two things the JSON backend cannot offer: cross-row
transactional atomicity (engagement + its documents) and real concurrent
write serialization (no corruption salvage needed).
"""
from __future__ import annotations

import uuid

import pytest


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    """Point SQLITE_DB_PATH at an isolated tmp file and reset the migration cache."""
    db_path = tmp_path / "test_opex.db"
    monkeypatch.setattr("app.config.SQLITE_DB_PATH", db_path)
    monkeypatch.setattr("app.db.connection.SQLITE_DB_PATH", db_path)
    from app.db.connection import reset_schema_cache

    reset_schema_cache()
    yield db_path
    reset_schema_cache()


@pytest.fixture
def session_repo(sqlite_db):
    from app.repositories.sqlite_store import SqliteSessionRepository

    return SqliteSessionRepository()


@pytest.fixture
def engagement_repo(sqlite_db):
    from app.repositories.sqlite_store import SqliteEngagementRepository

    return SqliteEngagementRepository()


def _uuid4() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Interface conformance
# ---------------------------------------------------------------------------

def test_sqlite_session_repo_implements_interface():
    from app.repositories.base import SessionRepository
    from app.repositories.sqlite_store import SqliteSessionRepository

    assert issubclass(SqliteSessionRepository, SessionRepository)


def test_sqlite_engagement_repo_implements_interface():
    from app.repositories.base import EngagementRepository
    from app.repositories.sqlite_store import SqliteEngagementRepository

    assert issubclass(SqliteEngagementRepository, EngagementRepository)


# ---------------------------------------------------------------------------
# SqliteSessionRepository
# ---------------------------------------------------------------------------

def test_session_not_exists_for_unknown(session_repo):
    assert not session_repo.exists(_uuid4())


def test_session_raises_on_missing_get(session_repo):
    with pytest.raises(KeyError):
        session_repo.get(_uuid4())


def test_session_save_then_get_round_trips(session_repo):
    sid = _uuid4()
    manifest = {
        "session_id": sid,
        "company_name": "Acme Corp",
        "industry": "it_ites",
        "annual_revenue": 1_000_000.0,
        "currency": "INR",
        "files": [{"filename": "spend.csv"}],
    }
    session_repo.save(sid, manifest)
    assert session_repo.exists(sid)
    fetched = session_repo.get(sid)
    assert fetched["company_name"] == "Acme Corp"
    assert fetched["files"] == [{"filename": "spend.csv"}]
    assert sid in session_repo.list_ids()


def test_session_save_is_upsert(session_repo):
    sid = _uuid4()
    session_repo.save(sid, {"session_id": sid, "company_name": "First"})
    session_repo.save(sid, {"session_id": sid, "company_name": "Second"})
    assert session_repo.get(sid)["company_name"] == "Second"
    assert session_repo.list_ids().count(sid) == 1


def test_session_delete_removes_row(session_repo):
    sid = _uuid4()
    session_repo.save(sid, {"session_id": sid, "company_name": "Acme"})
    session_repo.delete(sid)
    assert not session_repo.exists(sid)
    with pytest.raises(KeyError):
        session_repo.get(sid)


def test_session_delete_unknown_is_noop(session_repo):
    session_repo.delete(_uuid4())  # must not raise


def test_session_list_ids_is_list(session_repo):
    assert isinstance(session_repo.list_ids(), list)


# ---------------------------------------------------------------------------
# SqliteEngagementRepository
# ---------------------------------------------------------------------------

def test_engagement_not_exists_for_unknown(engagement_repo):
    assert not engagement_repo.exists(_uuid4())


def test_engagement_raises_on_missing_get(engagement_repo):
    with pytest.raises(KeyError):
        engagement_repo.get(_uuid4())


def test_engagement_save_then_get_round_trips(engagement_repo):
    eid = _uuid4()
    manifest = {
        "engagement_id": eid,
        "company_name": "Bharat Bazaar",
        "industry": "retail_organized",
        "annual_revenue": 420_000_000_000.0,
        "currency": "INR",
        "session_ids": [_uuid4()],
        "documents": [],
    }
    engagement_repo.save(eid, manifest)
    fetched = engagement_repo.get(eid)
    assert fetched["company_name"] == "Bharat Bazaar"
    assert fetched["session_ids"] == manifest["session_ids"]
    assert fetched["documents"] == []


def test_engagement_documents_round_trip_with_extra_fields(engagement_repo):
    """Documents normalize into their own table; unknown fields (added by the
    document pipeline after chunking/indexing) must survive via the `extra` column."""
    eid = _uuid4()
    did = _uuid4()
    manifest = {
        "engagement_id": eid,
        "company_name": "Acme",
        "documents": [
            {
                "document_id": did,
                "filename": "spend.csv",
                "content_type": "text/csv",
                "size_bytes": 1234,
                "raw_path": f"/data/engagements/{eid}/documents/{did}/raw.csv",
                "role": "spend_tabular",
                "status": "ready",
                "line_count": 42,
                # Fields not in EngagementDocumentRecord's core schema:
                "chunk_count": 7,
                "parent_count": 2,
                "indexed": True,
                "index_backend": "qdrant",
                "warnings": ["low_confidence_header"],
            }
        ],
    }
    engagement_repo.save(eid, manifest)
    fetched = engagement_repo.get(eid)
    assert len(fetched["documents"]) == 1
    doc = fetched["documents"][0]
    assert doc["document_id"] == did
    assert doc["status"] == "ready"
    assert doc["line_count"] == 42
    assert doc["chunk_count"] == 7
    assert doc["indexed"] is True
    assert doc["warnings"] == ["low_confidence_header"]


def test_engagement_save_removes_stale_documents(engagement_repo):
    """Saving a manifest with a document removed from the list must delete
    that document's row too (mirrors JSON backend: the manifest's `documents`
    array is always the full authoritative list)."""
    eid = _uuid4()
    did1, did2 = _uuid4(), _uuid4()
    engagement_repo.save(eid, {
        "engagement_id": eid,
        "documents": [
            {"document_id": did1, "filename": "a.csv"},
            {"document_id": did2, "filename": "b.csv"},
        ],
    })
    assert len(engagement_repo.get(eid)["documents"]) == 2

    engagement_repo.save(eid, {
        "engagement_id": eid,
        "documents": [{"document_id": did1, "filename": "a.csv"}],
    })
    fetched = engagement_repo.get(eid)
    assert [d["document_id"] for d in fetched["documents"]] == [did1]


def test_engagement_delete_cascades_documents(engagement_repo, sqlite_db):
    import contextlib

    from app.db import get_connection

    eid = _uuid4()
    did = _uuid4()
    engagement_repo.save(eid, {
        "engagement_id": eid,
        "documents": [{"document_id": did, "filename": "a.csv"}],
    })
    engagement_repo.delete(eid)
    assert not engagement_repo.exists(eid)
    with contextlib.closing(get_connection()) as conn:
        row = conn.execute("SELECT 1 FROM documents WHERE document_id = ?", (did,)).fetchone()
    assert row is None


def test_engagement_list_all_includes_document_counts(engagement_repo):
    eid = _uuid4()
    engagement_repo.save(eid, {
        "engagement_id": eid,
        "company_name": "Acme",
        "documents": [
            {"document_id": _uuid4(), "filename": "a.csv", "status": "ready"},
            {"document_id": _uuid4(), "filename": "b.csv", "status": "pending"},
        ],
    })
    summaries = engagement_repo.list_all()
    match = next(s for s in summaries if s["engagement_id"] == eid)
    assert match["document_count"] == 2
    assert match["documents_ready"] == 1


def test_engagement_list_for_owner_filters(engagement_repo):
    owned = _uuid4()
    legacy = _uuid4()
    other_owner = _uuid4()
    engagement_repo.save(owned, {"engagement_id": owned, "owner": "alice", "documents": []})
    engagement_repo.save(legacy, {"engagement_id": legacy, "owner": None, "documents": []})
    engagement_repo.save(other_owner, {"engagement_id": other_owner, "owner": "bob", "documents": []})

    visible = {e["engagement_id"] for e in engagement_repo.list_for_owner("alice")}
    assert owned in visible
    assert legacy in visible  # legacy (no owner) records are visible to everyone
    assert other_owner not in visible


def test_engagement_delete_unknown_is_noop(engagement_repo):
    engagement_repo.delete(_uuid4())  # must not raise


# ---------------------------------------------------------------------------
# Transaction atomicity — the thing JSON files cannot offer.
# ---------------------------------------------------------------------------

def test_save_is_all_or_nothing_on_failure(engagement_repo, monkeypatch):
    """A failure partway through save() must not leave a half-written engagement
    row + partial document rows — BEGIN IMMEDIATE / ROLLBACK guarantees this."""
    eid = _uuid4()
    good_doc = _uuid4()

    import app.repositories.sqlite_store as sqlite_store

    original = sqlite_store._document_row_params
    call_count = {"n": 0}

    def _boom(engagement_id, sort_order, doc):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise RuntimeError("simulated failure mid-transaction")
        return original(engagement_id, sort_order, doc)

    monkeypatch.setattr(sqlite_store, "_document_row_params", _boom)

    with pytest.raises(RuntimeError):
        engagement_repo.save(eid, {
            "engagement_id": eid,
            "company_name": "Acme",
            "documents": [
                {"document_id": good_doc, "filename": "a.csv"},
                {"document_id": _uuid4(), "filename": "b.csv"},
            ],
        })

    # Nothing committed: neither the engagement row nor the first document row.
    assert not engagement_repo.exists(eid)
