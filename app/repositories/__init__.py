"""Repository interfaces and factories.

Usage::

    from app.repositories import engagement_repo, session_repo

    manifest = session_repo().get("session-uuid")
    session_repo().save("session-uuid", manifest)

The default implementation is JSON-on-disk (``JsonSessionRepository`` /
``JsonEngagementRepository``).  Future implementations (SQLite, PostgreSQL)
can be swapped in by setting the ``REPOSITORY_BACKEND`` env var and providing
the corresponding class in this package.
"""
from __future__ import annotations

import os

from app.repositories.base import EngagementRepository, SessionRepository
from app.repositories.json_store import JsonEngagementRepository, JsonSessionRepository

_BACKEND = os.getenv("REPOSITORY_BACKEND", "json").lower()


def _make_session_repo() -> SessionRepository:
    if _BACKEND == "json":
        return JsonSessionRepository()
    raise ValueError(f"Unknown REPOSITORY_BACKEND={_BACKEND!r}; supported: json")


def _make_engagement_repo() -> EngagementRepository:
    if _BACKEND == "json":
        return JsonEngagementRepository()
    raise ValueError(f"Unknown REPOSITORY_BACKEND={_BACKEND!r}; supported: json")


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
