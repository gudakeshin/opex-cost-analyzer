"""Shared state and helper utilities used across all API routers."""
from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import threading
import uuid as _uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from fastapi import HTTPException

from app.config import UPLOAD_DIR, logger
from app.services.engagements_store import engagement_dir as _engagement_dir
from app.services.engagements_store import engagement_manifest_path as _engagement_manifest_path
from app.memory import MemoryStore
from app.storage import read_json, write_json

# ---------------------------------------------------------------------------
# Shared memory store — stateless wrapper, safe across requests.
# ---------------------------------------------------------------------------
_memory = MemoryStore()

# ---------------------------------------------------------------------------
# UUID v4 regex for session ID path-traversal prevention.
# ---------------------------------------------------------------------------
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def validate_session_id(session_id: str) -> None:
    if not _UUID_RE.match(session_id):
        raise HTTPException(status_code=400, detail="Invalid session_id format")


def validate_engagement_id(engagement_id: str) -> None:
    if not _UUID_RE.match(engagement_id):
        raise HTTPException(status_code=400, detail="Invalid engagement_id format")


def validate_document_id(document_id: str) -> None:
    if not _UUID_RE.match(document_id):
        raise HTTPException(status_code=400, detail="Invalid document_id format")


def engagement_dir(engagement_id: str) -> Path:
    return _engagement_dir(engagement_id)


def engagement_manifest_path(engagement_id: str) -> Path:
    return _engagement_manifest_path(engagement_id)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def session_dir(session_id: str) -> Path:
    return UPLOAD_DIR / session_id


def manifest_path(session_id: str) -> Path:
    return session_dir(session_id) / "manifest.json"


def read_manifest(session_id: str) -> Dict[str, Any]:
    return read_json(manifest_path(session_id), {"files": []})


def write_manifest(session_id: str, payload: Dict[str, Any]) -> None:
    write_json(manifest_path(session_id), payload)


# ---------------------------------------------------------------------------
# Session locking — Redis-backed distributed lock; asyncio.Lock fallback.
# ---------------------------------------------------------------------------

class _SessionLockBackend:
    """Distributed session lock: Redis when available, asyncio.Lock otherwise.

    Redis variant uses SET NX EX + Lua CAS delete for safe multi-replica deploys.
    """

    _LOCK_TTL_S = 30
    _ACQUIRE_TIMEOUT_S = 10
    _RETRY_INTERVAL_S = 0.05

    def __init__(self) -> None:
        self._local: dict[str, asyncio.Lock] = {}
        self._redis: Any = None
        redis_url = os.getenv("REDIS_URL", "")
        if redis_url:
            try:
                import redis as _redis_lib  # type: ignore[import]
                r = _redis_lib.Redis.from_url(
                    redis_url, socket_connect_timeout=1, decode_responses=True
                )
                r.ping()
                self._redis = r
                logger.info('"session_lock backend=redis"')
            except Exception as exc:
                logger.warning('"session_lock redis_unavailable error=%s using=local"', exc)

    @contextlib.asynccontextmanager
    async def acquire(self, session_id: str):  # type: ignore[return]
        if self._redis is None:
            lock = self._local.setdefault(session_id, asyncio.Lock())
            async with lock:
                yield
            return

        lock_key = f"opar:session_lock:{session_id}"
        lock_token = str(_uuid.uuid4())
        deadline = asyncio.get_event_loop().time() + self._ACQUIRE_TIMEOUT_S
        acquired = False
        while asyncio.get_event_loop().time() < deadline:
            ok = await asyncio.to_thread(
                self._redis.set, lock_key, lock_token, nx=True, ex=self._LOCK_TTL_S
            )
            if ok:
                acquired = True
                break
            await asyncio.sleep(self._RETRY_INTERVAL_S)
        if not acquired:
            raise HTTPException(status_code=503, detail="Could not acquire session lock; please retry")
        try:
            yield
        finally:
            _lua = (
                "if redis.call('get',KEYS[1])==ARGV[1] then "
                "return redis.call('del',KEYS[1]) else return 0 end"
            )
            try:
                await asyncio.to_thread(self._redis.eval, _lua, 1, lock_key, lock_token)
            except Exception as exc:
                logger.warning('"session_lock release_failed error=%s"', exc)


_session_lock_backend = _SessionLockBackend()


def session_lock(session_id: str):
    """Async context manager for per-session locking (distributed when Redis is configured)."""
    return _session_lock_backend.acquire(session_id)


def engagement_lock(engagement_id: str):
    """Reuse session lock backend keyed by engagement_id."""
    return _session_lock_backend.acquire(engagement_id)


def merge_context_into_manifest(
    manifest: Dict[str, Any],
    *,
    company_name: str | None = None,
    industry: str | None = None,
    annual_revenue: float | None = None,
    currency: str | None = None,
    audience: str | None = None,
    headcount: float | None = None,
) -> bool:
    changed = False
    if company_name is not None and manifest.get("company_name") != company_name:
        manifest["company_name"] = company_name
        changed = True
    if industry is not None and manifest.get("industry") != industry:
        manifest["industry"] = industry
        changed = True
    if annual_revenue is not None:
        rev = max(float(annual_revenue), 0.0)
        if float(manifest.get("annual_revenue") or 0.0) != rev:
            manifest["annual_revenue"] = rev
            changed = True
    if currency is not None and manifest.get("currency") != currency:
        manifest["currency"] = currency
        changed = True
    if audience is not None and manifest.get("audience") != audience:
        manifest["audience"] = audience
        changed = True
    if headcount is not None:
        hc = float(headcount)
        normalized_hc = hc if hc > 0 else None
        if manifest.get("headcount") != normalized_hc:
            manifest["headcount"] = normalized_hc
            changed = True
    return changed


# ---------------------------------------------------------------------------
# Progress store — in-process with optional Redis backend.
# ---------------------------------------------------------------------------

class _ProgressStore:
    _TTL_S = 3600

    def __init__(self) -> None:
        self._local: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._redis: Any = None
        redis_url = os.getenv("REDIS_URL", "")
        if redis_url:
            try:
                import redis as _redis_lib  # type: ignore[import]
                r = _redis_lib.Redis.from_url(redis_url, socket_connect_timeout=1, decode_responses=True)
                r.ping()
                self._redis = r
                logger.info('"progress_store backend=redis"')
            except Exception as exc:
                logger.warning('"progress_store redis_unavailable error=%s using=local"', exc)

    def _key(self, run_id: str) -> str:
        return f"opar:progress:{run_id}"

    def init(self, run_id: str, session_id: str) -> None:
        entry: Dict[str, Any] = {
            "run_id": run_id,
            "session_id": session_id,
            "status": "running",
            "started_at": utc_now_iso(),
            "updated_at": utc_now_iso(),
            "steps": [],
            "error": None,
        }
        if self._redis:
            self._redis.setex(self._key(run_id), self._TTL_S, json.dumps(entry))
        else:
            with self._lock:
                self._local[run_id] = entry

    def append(self, run_id: str, phase: str, message: str) -> None:
        step = {"phase": phase, "message": message, "timestamp": utc_now_iso()}
        if self._redis:
            raw = self._redis.get(self._key(run_id))
            if raw:
                entry = json.loads(raw)
                entry["steps"].append(step)
                entry["updated_at"] = utc_now_iso()
                self._redis.setex(self._key(run_id), self._TTL_S, json.dumps(entry))
        else:
            with self._lock:
                entry = self._local.get(run_id)
                if entry:
                    entry["steps"].append(step)
                    entry["updated_at"] = utc_now_iso()

    def complete(self, run_id: str, *, failed: bool = False, error: str | None = None) -> None:
        if self._redis:
            raw = self._redis.get(self._key(run_id))
            if raw:
                entry = json.loads(raw)
                entry["status"] = "failed" if failed else "completed"
                entry["error"] = error
                entry["updated_at"] = utc_now_iso()
                self._redis.setex(self._key(run_id), self._TTL_S, json.dumps(entry))
        else:
            with self._lock:
                entry = self._local.get(run_id)
                if entry:
                    entry["status"] = "failed" if failed else "completed"
                    entry["error"] = error
                    entry["updated_at"] = utc_now_iso()

    def get(self, run_id: str) -> Dict[str, Any] | None:
        if self._redis:
            raw = self._redis.get(self._key(run_id))
            return json.loads(raw) if raw else None
        with self._lock:
            entry = self._local.get(run_id)
            return dict(entry) if entry else None


_progress = _ProgressStore()


def progress_init(run_id: str, session_id: str) -> None:
    _progress.init(run_id, session_id)


def progress_append(run_id: str, phase: str, message: str) -> None:
    _progress.append(run_id, phase, message)


def progress_complete(run_id: str, *, failed: bool = False, error: str | None = None) -> None:
    _progress.complete(run_id, failed=failed, error=error)


def progress_get(run_id: str) -> Dict[str, Any] | None:
    return _progress.get(run_id)
