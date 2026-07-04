"""SQLite-backed repository implementations.

Hybrid relational + JSON, matching app/db/migrations/0001_init.sql: scalar
fields used for filtering/sorting/joins live in real columns; the rest of
each manifest is preserved verbatim in a `data` JSON column so this layer
does not need to track every field the app adds to a manifest dict (both
manifest pydantic models use `extra="allow"`).

`documents` is normalized into its own table (see 0001_init.sql for why) —
get() reconstructs manifest["documents"] from it, save() diffs the incoming
list against existing rows and upserts/deletes accordingly, all inside one
BEGIN IMMEDIATE transaction alongside the engagement row. That transaction
is the cross-file-consistency guarantee the JSON backend cannot offer: an
engagement update and its document rows either land together or not at all.

Raw file blobs (uploaded originals, parsed/parent_nodes.json, etc.) are
unchanged by this migration — they stay on disk under UPLOAD_DIR /
ENGAGEMENTS_DIR exactly as today. Only the manifest/registry data that used
to live in manifest.json moves into SQLite.
"""
from __future__ import annotations

import contextlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.db import get_connection, transaction
from app.repositories.base import EngagementRepository, SessionRepository

# EngagementDocumentRecord's known fields (app/schemas.py). Anything else on
# a document dict is preserved in the `extra` JSON column so pipeline code
# (app/services/document_pipeline.py) can keep adding fields like
# chunk_count/parent_count/indexed/index_backend/warnings without this layer
# silently dropping them.
_DOCUMENT_FIELDS = (
    "document_id",
    "filename",
    "content_type",
    "size_bytes",
    "raw_path",
    "role",
    "status",
    "parse_backend",
    "error",
    "uploaded_at",
    "processed_at",
    "text_preview",
    "line_count",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _document_row_to_dict(row: Any) -> Dict[str, Any]:
    record: Dict[str, Any] = {field: row[field] for field in _DOCUMENT_FIELDS}
    extra = json.loads(row["extra"] or "{}")
    record.update(extra)
    return record


def _document_row_params(engagement_id: str, sort_order: int, doc: Dict[str, Any]) -> tuple:
    extra = {k: v for k, v in doc.items() if k not in _DOCUMENT_FIELDS}
    return (
        str(doc.get("document_id") or ""),
        engagement_id,
        doc.get("filename") or "",
        doc.get("content_type") or "application/octet-stream",
        int(doc.get("size_bytes") or 0),
        doc.get("raw_path") or "",
        doc.get("role") or "context_doc",
        doc.get("status") or "pending",
        doc.get("parse_backend"),
        doc.get("error"),
        doc.get("uploaded_at"),
        doc.get("processed_at"),
        doc.get("text_preview"),
        int(doc.get("line_count") or 0),
        sort_order,
        json.dumps(extra),
    )


class SqliteSessionRepository(SessionRepository):
    """Session manifests stored in the `sessions` table (SQLITE_DB_PATH)."""

    def get(self, session_id: str) -> Dict[str, Any]:
        from app.routers._shared import validate_session_id

        validate_session_id(session_id)
        with contextlib.closing(get_connection()) as conn:
            row = conn.execute(
                "SELECT data FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"Session not found: {session_id}")
        return json.loads(row["data"])

    def save(self, session_id: str, manifest: Dict[str, Any]) -> None:
        from app.routers._shared import validate_session_id

        validate_session_id(session_id)
        payload = dict(manifest)
        payload["session_id"] = session_id
        now = _utc_now()
        with contextlib.closing(get_connection()) as conn, transaction(conn):
            conn.execute(
                """
                INSERT INTO sessions
                    (session_id, engagement_id, owner, company_name, industry,
                     annual_revenue, currency, created_at, updated_at, data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    engagement_id = excluded.engagement_id,
                    owner = excluded.owner,
                    company_name = excluded.company_name,
                    industry = excluded.industry,
                    annual_revenue = excluded.annual_revenue,
                    currency = excluded.currency,
                    updated_at = excluded.updated_at,
                    data = excluded.data
                """,
                (
                    session_id,
                    payload.get("engagement_id"),
                    payload.get("owner"),
                    payload.get("company_name") or "New engagement",
                    payload.get("industry") or "",
                    float(payload.get("annual_revenue") or 0.0),
                    payload.get("currency") or "INR",
                    payload.get("created_at") or now,
                    now,
                    json.dumps(payload),
                ),
            )

    def exists(self, session_id: str) -> bool:
        from app.routers._shared import validate_session_id

        try:
            validate_session_id(session_id)
        except Exception:
            return False
        with contextlib.closing(get_connection()) as conn:
            row = conn.execute(
                "SELECT 1 FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        return row is not None

    def list_ids(self) -> List[str]:
        with contextlib.closing(get_connection()) as conn:
            rows = conn.execute("SELECT session_id FROM sessions").fetchall()
        return [r["session_id"] for r in rows]

    def delete(self, session_id: str) -> None:
        import shutil

        from app.config import UPLOAD_DIR
        from app.routers._shared import validate_session_id

        validate_session_id(session_id)
        with contextlib.closing(get_connection()) as conn, transaction(conn):
            conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        # Raw uploads for this session (if any) live outside the DB, same as today.
        path = UPLOAD_DIR / session_id
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)


class SqliteEngagementRepository(EngagementRepository):
    """Engagement manifests in `engagements`, documents normalized into `documents`."""

    def get(self, engagement_id: str) -> Dict[str, Any]:
        from app.routers._shared import validate_engagement_id

        validate_engagement_id(engagement_id)
        with contextlib.closing(get_connection()) as conn:
            row = conn.execute(
                "SELECT data FROM engagements WHERE engagement_id = ?", (engagement_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"Engagement not found: {engagement_id}")
            doc_rows = conn.execute(
                "SELECT * FROM documents WHERE engagement_id = ? ORDER BY sort_order",
                (engagement_id,),
            ).fetchall()
        manifest = json.loads(row["data"])
        manifest["engagement_id"] = engagement_id
        manifest["documents"] = [_document_row_to_dict(r) for r in doc_rows]
        return manifest

    def save(self, engagement_id: str, manifest: Dict[str, Any]) -> None:
        from app.routers._shared import validate_engagement_id

        validate_engagement_id(engagement_id)
        payload = dict(manifest)
        payload["engagement_id"] = engagement_id
        documents = [d for d in (payload.pop("documents", None) or []) if isinstance(d, dict)]
        now = _utc_now()
        updated_at = payload.get("updated_at") or now

        with contextlib.closing(get_connection()) as conn, transaction(conn):
            conn.execute(
                """
                INSERT INTO engagements
                    (engagement_id, owner, company_name, industry, annual_revenue,
                     currency, created_at, updated_at, data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(engagement_id) DO UPDATE SET
                    owner = excluded.owner,
                    company_name = excluded.company_name,
                    industry = excluded.industry,
                    annual_revenue = excluded.annual_revenue,
                    currency = excluded.currency,
                    updated_at = excluded.updated_at,
                    data = excluded.data
                """,
                (
                    engagement_id,
                    payload.get("owner"),
                    payload.get("company_name") or "New engagement",
                    payload.get("industry") or "",
                    float(payload.get("annual_revenue") or 0.0),
                    payload.get("currency") or "INR",
                    payload.get("created_at") or now,
                    updated_at,
                    json.dumps(payload),
                ),
            )

            existing_ids = {
                r[0]
                for r in conn.execute(
                    "SELECT document_id FROM documents WHERE engagement_id = ?",
                    (engagement_id,),
                )
            }
            incoming_ids: set[str] = set()
            for i, doc in enumerate(documents):
                did = str(doc.get("document_id") or "").strip()
                if not did:
                    continue
                incoming_ids.add(did)
                conn.execute(
                    """
                    INSERT INTO documents
                        (document_id, engagement_id, filename, content_type, size_bytes,
                         raw_path, role, status, parse_backend, error, uploaded_at,
                         processed_at, text_preview, line_count, sort_order, extra)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(document_id) DO UPDATE SET
                        filename = excluded.filename,
                        content_type = excluded.content_type,
                        size_bytes = excluded.size_bytes,
                        raw_path = excluded.raw_path,
                        role = excluded.role,
                        status = excluded.status,
                        parse_backend = excluded.parse_backend,
                        error = excluded.error,
                        uploaded_at = excluded.uploaded_at,
                        processed_at = excluded.processed_at,
                        text_preview = excluded.text_preview,
                        line_count = excluded.line_count,
                        sort_order = excluded.sort_order,
                        extra = excluded.extra
                    """,
                    _document_row_params(engagement_id, i, doc),
                )

            stale_ids = existing_ids - incoming_ids
            if stale_ids:
                conn.executemany(
                    "DELETE FROM documents WHERE document_id = ?",
                    [(d,) for d in stale_ids],
                )

    def exists(self, engagement_id: str) -> bool:
        from app.routers._shared import validate_engagement_id

        try:
            validate_engagement_id(engagement_id)
        except Exception:
            return False
        with contextlib.closing(get_connection()) as conn:
            row = conn.execute(
                "SELECT 1 FROM engagements WHERE engagement_id = ?", (engagement_id,)
            ).fetchone()
        return row is not None

    def _summary_from_row(self, row: Any) -> Dict[str, Any]:
        data = json.loads(row["data"] or "{}")
        return {
            "engagement_id": row["engagement_id"],
            "owner": row["owner"],
            "company_name": row["company_name"] or "Unknown",
            "industry": row["industry"] or "",
            "currency": row["currency"] or "INR",
            "annual_revenue": row["annual_revenue"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "session_count": len(data.get("session_ids") or []),
            "document_count": row["document_count"],
            "documents_ready": row["documents_ready"],
            "detected_company_name": data.get("detected_company_name") or "",
            "detected_industry": data.get("detected_industry") or "",
            "detected_industry_label": data.get("detected_industry_label") or "",
            "detected_annual_revenue_cr": data.get("detected_annual_revenue_cr"),
            "manifest_status": "ok",
        }

    def list_all(self) -> List[Dict[str, Any]]:
        with contextlib.closing(get_connection()) as conn:
            rows = conn.execute(
                """
                SELECT e.*,
                    (SELECT COUNT(*) FROM documents d WHERE d.engagement_id = e.engagement_id)
                        AS document_count,
                    (SELECT COUNT(*) FROM documents d
                        WHERE d.engagement_id = e.engagement_id AND d.status = 'ready')
                        AS documents_ready
                FROM engagements e
                ORDER BY e.updated_at DESC
                """
            ).fetchall()
        return [self._summary_from_row(r) for r in rows]

    def list_for_owner(self, owner: Optional[str]) -> List[Dict[str, Any]]:
        all_engagements = self.list_all()
        if owner is None:
            return all_engagements
        # Legacy records with no owner field are visible to all principals —
        # same semantics as JsonEngagementRepository.list_for_owner.
        return [
            e for e in all_engagements
            if not e.get("owner") or e.get("owner") == owner
        ]

    def delete(self, engagement_id: str) -> None:
        import shutil

        from app.config import ENGAGEMENTS_DIR
        from app.routers._shared import validate_engagement_id

        validate_engagement_id(engagement_id)
        with contextlib.closing(get_connection()) as conn, transaction(conn):
            # documents cascade via ON DELETE CASCADE.
            conn.execute("DELETE FROM engagements WHERE engagement_id = ?", (engagement_id,))
        # Raw document blobs / parsed artifacts live outside the DB, same as today.
        path = ENGAGEMENTS_DIR / engagement_id
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
