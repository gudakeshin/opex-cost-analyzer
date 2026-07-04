"""Durable job queue — single-node asyncio worker."""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from app.db.connection import get_connection, transaction

log = logging.getLogger(__name__)

_HANDLERS: Dict[str, Callable[[Dict[str, Any]], Any]] = {}


def register_job_handler(kind: str, handler: Callable[[Dict[str, Any]], Any]) -> None:
    _HANDLERS[kind] = handler


def enqueue_job(kind: str, payload: Dict[str, Any]) -> str:
    job_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with contextlib.closing(get_connection()) as conn, transaction(conn):
        conn.execute(
            "INSERT INTO jobs (id, kind, payload, state, progress, heartbeat, created_at, updated_at) "
            "VALUES (?, ?, ?, 'pending', 0, ?, ?, ?)",
            (job_id, kind, json.dumps(payload), now, now, now),
        )
    return job_id


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    with contextlib.closing(get_connection()) as conn:
        row = conn.execute(
            "SELECT id, kind, payload, state, progress, heartbeat, created_at, updated_at, result "
            "FROM jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
    if not row:
        return None
    result = None
    if row[8]:
        try:
            result = json.loads(row[8])
        except json.JSONDecodeError:
            result = {"raw": row[8]}
    payload = {}
    try:
        payload = json.loads(row[2] or "{}")
    except json.JSONDecodeError:
        pass
    return {
        "job_id": row[0],
        "kind": row[1],
        "payload": payload,
        "state": row[3],
        "progress": float(row[4] or 0),
        "heartbeat": row[5],
        "created_at": row[6],
        "updated_at": row[7],
        "result": result,
    }


def update_job_progress(
    job_id: str,
    progress: float,
    *,
    message: str | None = None,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with contextlib.closing(get_connection()) as conn, transaction(conn):
        if message:
            row = conn.execute("SELECT payload FROM jobs WHERE id = ?", (job_id,)).fetchone()
            payload: Dict[str, Any] = {}
            if row:
                try:
                    payload = json.loads(row[0] or "{}")
                except json.JSONDecodeError:
                    pass
            payload["progress_message"] = message
            conn.execute(
                "UPDATE jobs SET progress = ?, heartbeat = ?, updated_at = ?, payload = ? WHERE id = ?",
                (progress, now, now, json.dumps(payload), job_id),
            )
        else:
            conn.execute(
                "UPDATE jobs SET progress = ?, heartbeat = ?, updated_at = ? WHERE id = ?",
                (progress, now, now, job_id),
            )


def _complete_job(job_id: str, result: Dict[str, Any] | None, *, failed: bool = False) -> None:
    now = datetime.now(timezone.utc).isoformat()
    state = "failed" if failed else "done"
    progress = 0 if failed else 100
    with contextlib.closing(get_connection()) as conn, transaction(conn):
        conn.execute(
            "UPDATE jobs SET state = ?, progress = ?, heartbeat = ?, updated_at = ?, result = ? "
            "WHERE id = ?",
            (state, progress, now, now, json.dumps(result or {}), job_id),
        )


def _claim_next() -> Optional[Dict[str, Any]]:
    now = datetime.now(timezone.utc).isoformat()
    with contextlib.closing(get_connection()) as conn, transaction(conn):
        row = conn.execute(
            "SELECT id, kind, payload FROM jobs WHERE state = 'pending' "
            "ORDER BY created_at LIMIT 1"
        ).fetchone()
        if not row:
            return None
        conn.execute(
            "UPDATE jobs SET state = 'running', heartbeat = ?, updated_at = ? WHERE id = ?",
            (now, now, row[0]),
        )
        return {"id": row[0], "kind": row[1], "payload": json.loads(row[2] or "{}")}


async def run_job_worker(stop_event: asyncio.Event, poll_s: float = 2.0) -> None:
    """Poll SQLite for pending jobs and execute registered handlers."""
    while not stop_event.is_set():
        job = _claim_next()
        if not job:
            await asyncio.sleep(poll_s)
            continue
        handler = _HANDLERS.get(job["kind"])
        payload = {**job["payload"], "_job_id": job["id"]}
        try:
            if handler is None:
                raise RuntimeError(f"No handler for job kind: {job['kind']}")
            if asyncio.iscoroutinefunction(handler):
                result = await handler(payload)
            else:
                result = await asyncio.to_thread(handler, payload)
            if not isinstance(result, dict):
                result = {"value": result}
            _complete_job(job["id"], result, failed=False)
        except Exception as exc:
            log.warning("job_failed id=%s kind=%s err=%s", job["id"], job["kind"], exc)
            _complete_job(job["id"], {"error": str(exc)[:500]}, failed=True)


def requeue_stale_jobs(stale_seconds: int = 300) -> int:
    """Re-queue jobs whose heartbeat is older than stale_seconds."""
    from datetime import timedelta

    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=stale_seconds)).isoformat()
    with contextlib.closing(get_connection()) as conn, transaction(conn):
        cur = conn.execute(
            "UPDATE jobs SET state = 'pending' WHERE state = 'running' AND heartbeat < ?",
            (cutoff,),
        )
        return cur.rowcount
