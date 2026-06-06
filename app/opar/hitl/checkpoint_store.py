"""Checkpoint persistence for suspended OPAR runs awaiting HITL clarification."""

from __future__ import annotations

import json
import os
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Literal

from app.config import logger
from app.opar.hitl.clarification_tool import BusinessClarificationPayload


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class OparCheckpoint:
    checkpoint_id: str
    session_id: str
    user_id: str
    original_message: str
    observe_context: dict
    clarification: BusinessClarificationPayload
    file_ids: list[str] | None = None
    created_at: str = field(default_factory=_utc_now_iso)
    status: Literal["pending", "resumed", "expired"] = "pending"
    result_snapshot: dict | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["clarification"] = self.clarification.model_dump()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OparCheckpoint:
        clarification = BusinessClarificationPayload.model_validate(data["clarification"])
        return cls(
            checkpoint_id=data["checkpoint_id"],
            session_id=data["session_id"],
            user_id=data["user_id"],
            original_message=data["original_message"],
            observe_context=data.get("observe_context") or {},
            clarification=clarification,
            file_ids=data.get("file_ids"),
            created_at=data.get("created_at") or _utc_now_iso(),
            status=data.get("status") or "pending",
            result_snapshot=data.get("result_snapshot"),
        )


class _CheckpointStore:
    _TTL_S = int(os.getenv("OPAR_CHECKPOINT_TTL_S", str(24 * 3600)))

    def __init__(self) -> None:
        self._local: Dict[str, dict] = {}
        self._lock = threading.Lock()
        self._redis: Any = None
        redis_url = os.getenv("REDIS_URL", "")
        if redis_url:
            try:
                import redis as _redis_lib  # type: ignore[import]

                r = _redis_lib.Redis.from_url(redis_url, socket_connect_timeout=1, decode_responses=True)
                r.ping()
                self._redis = r
                logger.info('"checkpoint_store backend=redis"')
            except Exception as exc:
                logger.warning('"checkpoint_store redis_unavailable error=%s using=local"', exc)

    def _key(self, checkpoint_id: str) -> str:
        return f"opar:checkpoint:{checkpoint_id}"

    def save(
        self,
        *,
        session_id: str,
        user_id: str,
        original_message: str,
        observe_context: dict,
        clarification: BusinessClarificationPayload,
        file_ids: list[str] | None = None,
    ) -> str:
        checkpoint_id = str(uuid.uuid4())
        entry = OparCheckpoint(
            checkpoint_id=checkpoint_id,
            session_id=session_id,
            user_id=user_id,
            original_message=original_message,
            observe_context=observe_context,
            clarification=clarification,
            file_ids=file_ids,
        )
        payload = json.dumps(entry.to_dict())
        if self._redis:
            self._redis.setex(self._key(checkpoint_id), self._TTL_S, payload)
        else:
            with self._lock:
                self._local[checkpoint_id] = json.loads(payload)
        return checkpoint_id

    def get(self, checkpoint_id: str) -> OparCheckpoint | None:
        if self._redis:
            raw = self._redis.get(self._key(checkpoint_id))
            if not raw:
                return None
            return OparCheckpoint.from_dict(json.loads(raw))
        with self._lock:
            raw = self._local.get(checkpoint_id)
            return OparCheckpoint.from_dict(raw) if raw else None

    def mark_resumed(self, checkpoint_id: str, result_snapshot: dict | None = None) -> bool:
        cp = self.get(checkpoint_id)
        if not cp:
            return False
        cp.status = "resumed"
        if result_snapshot is not None:
            cp.result_snapshot = result_snapshot
        payload = json.dumps(cp.to_dict())
        if self._redis:
            self._redis.setex(self._key(checkpoint_id), self._TTL_S, payload)
        else:
            with self._lock:
                self._local[checkpoint_id] = json.loads(payload)
        return True


checkpoint_store = _CheckpointStore()
