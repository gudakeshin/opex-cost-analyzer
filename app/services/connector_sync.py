"""Connector delta-sync watermarks — one cursor per (engagement, connector)."""
from __future__ import annotations

import contextlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.db.connection import get_connection, transaction


def get_watermark(engagement_id: str, connector_type: str) -> Optional[Dict[str, Any]]:
    with contextlib.closing(get_connection()) as conn, transaction(conn):
        row = conn.execute(
            "SELECT last_sync_at, cursor_json, updated_at FROM connector_watermarks "
            "WHERE engagement_id = ? AND connector_type = ?",
            (engagement_id, connector_type),
        ).fetchone()
    if not row:
        return None
    cursor = {}
    try:
        cursor = json.loads(row[1] or "{}")
    except json.JSONDecodeError:
        pass
    return {
        "engagement_id": engagement_id,
        "connector_type": connector_type,
        "last_sync_at": row[0],
        "cursor": cursor,
        "updated_at": row[2],
    }


def set_watermark(
    engagement_id: str,
    connector_type: str,
    *,
    last_sync_at: str | None = None,
    cursor: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    sync_at = last_sync_at or now
    cursor_json = json.dumps(cursor or {})
    with contextlib.closing(get_connection()) as conn, transaction(conn):
        conn.execute(
            "INSERT INTO connector_watermarks "
            "(engagement_id, connector_type, last_sync_at, cursor_json, updated_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(engagement_id, connector_type) DO UPDATE SET "
            "last_sync_at = excluded.last_sync_at, "
            "cursor_json = excluded.cursor_json, "
            "updated_at = excluded.updated_at",
            (engagement_id, connector_type, sync_at, cursor_json, now),
        )
    return get_watermark(engagement_id, connector_type) or {}


def list_watermarks(engagement_id: str) -> list[Dict[str, Any]]:
    with contextlib.closing(get_connection()) as conn:
        rows = conn.execute(
            "SELECT connector_type, last_sync_at, cursor_json, updated_at "
            "FROM connector_watermarks WHERE engagement_id = ? ORDER BY connector_type",
            (engagement_id,),
        ).fetchall()
    out: list[Dict[str, Any]] = []
    for row in rows:
        try:
            cursor = json.loads(row[2] or "{}")
        except json.JSONDecodeError:
            cursor = {}
        out.append({
            "connector_type": row[0],
            "last_sync_at": row[1],
            "cursor": cursor,
            "updated_at": row[3],
        })
    return out
