from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict

from app.config import MEMORY_DIR, logger
from app.storage import read_json, write_json


class MemoryStore:
    """Local file-backed memory with user/session/agent scopes."""

    def __init__(self) -> None:
        self.base = MEMORY_DIR

    def _path(self, scope: str, key: str) -> Path:
        return self.base / scope / f"{key}.json"

    def put(self, scope: str, key: str, payload: Dict[str, Any]) -> None:
        write_json(self._path(scope, key), payload)

    def get(self, scope: str, key: str) -> Dict[str, Any]:
        return read_json(self._path(scope, key), {})

    def delete(self, scope: str, key: str) -> None:
        path = self._path(scope, key)
        if path.exists():
            path.unlink()

    # ------------------------------------------------------------------
    # Engagement scope — v2.0 outermost scope; tear-down destroys all.
    # ------------------------------------------------------------------

    def put_engagement(self, engagement_id: str, payload: Dict[str, Any]) -> None:
        write_json(self._path("engagement", engagement_id), payload)

    def get_engagement(self, engagement_id: str) -> Dict[str, Any]:
        return read_json(self._path("engagement", engagement_id), {})

    def delete_engagement(self, engagement_id: str) -> None:
        path = self._path("engagement", engagement_id)
        if path.exists():
            path.unlink()

    def list_engagement_sessions(self, engagement_id: str) -> list:
        """Return all session_ids that declare this engagement_id."""
        sessions: list[str] = []
        session_dir = self.base / "session"
        if not session_dir.exists():
            return sessions
        for f in session_dir.glob("*.json"):
            try:
                data = read_json(f, {})
                if data.get("engagement_id") == engagement_id:
                    sessions.append(f.stem)
            except Exception:
                pass
        return sessions

    def teardown_engagement(self, engagement_id: str) -> Dict[str, Any]:
        """Destroy all data for an engagement and return a deletion manifest.

        Removes the engagement record, all child sessions, their OPAR entries,
        and associated agent memory entries that were tagged to this engagement.
        Returns a dict summarising what was deleted for the attestation record.
        """
        deleted: Dict[str, Any] = {
            "engagement_id": engagement_id,
            "sessions_deleted": [],
            "engagement_record_deleted": False,
        }
        # Delete child sessions
        for session_id in self.list_engagement_sessions(engagement_id):
            self.delete("session", session_id)
            self.delete("session", f"{session_id}_opar")
            deleted["sessions_deleted"].append(session_id)
        # Delete engagement record
        self.delete_engagement(engagement_id)
        deleted["engagement_record_deleted"] = True
        logger.info(
            '"engagement_teardown engagement_id=%s sessions=%d"',
            engagement_id,
            len(deleted["sessions_deleted"]),
        )
        return deleted

    def cleanup_expired_sessions(self, ttl_days: int = 30) -> int:
        """Delete session memory files older than ttl_days. Returns count of deleted files."""
        cutoff_seconds = ttl_days * 86_400
        now = time.time()
        deleted = 0
        for json_file in self.base.rglob("*.json"):
            try:
                age_s = now - json_file.stat().st_mtime
                if age_s > cutoff_seconds:
                    json_file.unlink()
                    deleted += 1
            except OSError:
                pass  # file may have been deleted concurrently
        if deleted:
            logger.info('"memory_cleanup deleted=%d ttl_days=%d"', deleted, ttl_days)
        return deleted

    def usage_stats(self) -> Dict[str, Any]:
        """Return basic disk usage stats for the /health endpoint."""
        files = list(self.base.rglob("*.json"))
        total_bytes = sum(f.stat().st_size for f in files if f.exists())
        return {
            "memory_file_count": len(files),
            "memory_dir_size_mb": round(total_bytes / 1_048_576, 2),
        }
