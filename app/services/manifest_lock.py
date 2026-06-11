"""Distributed lock for engagement manifest read-modify-write cycles."""
from __future__ import annotations

import asyncio
import contextlib
import os
import threading
import time
import uuid as _uuid
from typing import Any, Iterator

from app.config import logger

_LOCK_TTL_S = 30
_ACQUIRE_TIMEOUT_S = 10
_RETRY_INTERVAL_S = 0.05
_REDIS_KEY_PREFIX = "opar:manifest_lock:"
_LUA_RELEASE = (
    "if redis.call('get',KEYS[1])==ARGV[1] then "
    "return redis.call('del',KEYS[1]) else return 0 end"
)


class ManifestLockError(RuntimeError):
    """Raised when a manifest lock cannot be acquired."""


class ManifestLock:
    """Redis-backed manifest lock with in-process RLock fallback."""

    def __init__(self) -> None:
        self._local_guard = threading.Lock()
        self._local_locks: dict[str, threading.RLock] = {}
        self._redis: Any = None
        redis_url = os.getenv("REDIS_URL", "")
        if redis_url:
            try:
                import redis as redis_lib  # type: ignore[import-untyped]

                client = redis_lib.Redis.from_url(
                    redis_url,
                    socket_connect_timeout=1,
                    decode_responses=True,
                )
                client.ping()
                self._redis = client
                logger.info('"manifest_lock backend=redis"')
            except Exception as exc:
                logger.warning('"manifest_lock redis_unavailable error=%s using=local"', exc)
        if self._redis is None:
            logger.warning(
                '"manifest_lock backend=local — in-process only; '
                'concurrent writes WILL race with >1 worker/replica (set REDIS_URL)"'
            )

    def _local_lock(self, engagement_id: str) -> threading.RLock:
        with self._local_guard:
            lock = self._local_locks.get(engagement_id)
            if lock is None:
                lock = threading.RLock()
                self._local_locks[engagement_id] = lock
            return lock

    def _acquire_redis(self, engagement_id: str) -> tuple[str, str]:
        if self._redis is None:
            raise ManifestLockError("Redis client unavailable")
        lock_key = f"{_REDIS_KEY_PREFIX}{engagement_id}"
        lock_token = str(_uuid.uuid4())
        deadline = time.monotonic() + _ACQUIRE_TIMEOUT_S
        while time.monotonic() < deadline:
            acquired = self._redis.set(lock_key, lock_token, nx=True, ex=_LOCK_TTL_S)
            if acquired:
                return lock_key, lock_token
            time.sleep(_RETRY_INTERVAL_S)
        raise ManifestLockError(
            f"Could not acquire manifest lock for engagement {engagement_id}; please retry"
        )

    def _release_redis(self, lock_key: str, lock_token: str) -> None:
        if self._redis is None:
            return
        try:
            self._redis.eval(_LUA_RELEASE, 1, lock_key, lock_token)
        except Exception as exc:
            logger.warning('"manifest_lock release_failed error=%s"', exc)

    @contextlib.contextmanager
    def acquire(self, engagement_id: str) -> Iterator[None]:
        if self._redis is None:
            with self._local_lock(engagement_id):
                yield
            return

        lock_key, lock_token = self._acquire_redis(engagement_id)
        try:
            yield
        finally:
            self._release_redis(lock_key, lock_token)

    @contextlib.asynccontextmanager
    async def acquire_async(self, engagement_id: str):
        if self._redis is None:
            with self._local_lock(engagement_id):
                yield
            return

        lock_key, lock_token = await asyncio.to_thread(self._acquire_redis, engagement_id)
        try:
            yield
        finally:
            await asyncio.to_thread(self._release_redis, lock_key, lock_token)


manifest_lock = ManifestLock()
