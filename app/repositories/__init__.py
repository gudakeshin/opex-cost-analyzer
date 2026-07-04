"""Repository interfaces and factories.

Usage::

    from app.repositories import engagement_repo, session_repo

    manifest = session_repo().get("session-uuid")
    session_repo().save("session-uuid", manifest)

The default implementation is JSON-on-disk (``JsonSessionRepository`` /
``JsonEngagementRepository``).  Set ``REPOSITORY_BACKEND=sqlite`` to switch to
``SqliteSessionRepository`` / ``SqliteEngagementRepository`` (see
app/repositories/sqlite_store.py and docs/architecture/persistence-migration-plan.md).
A future PostgreSQL implementation can be added the same way.
"""
from __future__ import annotations

import os

from app.repositories.base import EngagementRepository, SessionRepository
from app.repositories.json_store import JsonEngagementRepository, JsonSessionRepository

_BACKEND = os.getenv("REPOSITORY_BACKEND", "json").lower()


def _make_session_repo() -> SessionRepository:
    if _BACKEND == "json":
        return JsonSessionRepository()
    if _BACKEND == "sqlite":
        from app.repositories.sqlite_store import SqliteSessionRepository

        return SqliteSessionRepository()
    raise ValueError(f"Unknown REPOSITORY_BACKEND={_BACKEND!r}; supported: json, sqlite")


def _make_engagement_repo() -> EngagementRepository:
    if _BACKEND == "json":
        return JsonEngagementRepository()
    if _BACKEND == "sqlite":
        from app.repositories.sqlite_store import SqliteEngagementRepository

        return SqliteEngagementRepository()
    raise ValueError(f"Unknown REPOSITORY_BACKEND={_BACKEND!r}; supported: json, sqlite")


# Module-level singletons — lazily initialised, cheap to construct.
_session_repo: SessionRepository | None = None
_engagement_repo: EngagementRepository | None = None


def session_repo() -> SessionRepository:
    global _session_repo
    if _session_repo is None:
        _session_repo = _make_session_repo()
    return _session_repo


def engagement_repo() -> EngagementRepository:
    global _engagement_repo
    if _engagement_repo is None:
        _engagement_repo = _make_engagement_repo()
    return _engagement_repo


__all__ = [
    "EngagementRepository",
    "SessionRepository",
    "JsonEngagementRepository",
    "JsonSessionRepository",
    "session_repo",
    "engagement_repo",
]
