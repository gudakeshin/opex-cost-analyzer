"""Repository interfaces and factories.

Usage::

    from app.repositories import engagement_repo, session_repo

    manifest = session_repo().get("session-uuid")
    session_repo().save("session-uuid", manifest)

The default backend is SQLite (``SqliteSessionRepository`` /
``SqliteEngagementRepository``, see app/repositories/sqlite_store.py and
docs/architecture/persistence-migration-plan.md). Set
``REPOSITORY_BACKEND=json`` to roll back to the legacy JSON-on-disk stores.
A future PostgreSQL implementation can be added the same way.

The manifest helpers in app/routers/_shared.py and
app/services/engagements_store.py dispatch on ``active_backend()``: their
JSON file logic is the backend when it returns "json", and they delegate to
these repositories otherwise. The Json* repositories delegate back to those
helpers, which is not circular precisely because the helpers only delegate
when the backend is not "json".
"""
from __future__ import annotations

import os

from app.repositories.base import EngagementRepository, SessionRepository
from app.repositories.json_store import JsonEngagementRepository, JsonSessionRepository

_DEFAULT_BACKEND = "sqlite"


def active_backend() -> str:
    """The persistence backend selected by REPOSITORY_BACKEND (default sqlite).

    Read dynamically (not cached at import) so tests can flip backends with
    monkeypatch.setenv; the repo singletons below are keyed by backend name
    for the same reason.
    """
    return os.getenv("REPOSITORY_BACKEND", _DEFAULT_BACKEND).lower()


def _make_session_repo(backend: str) -> SessionRepository:
    if backend == "json":
        return JsonSessionRepository()
    if backend == "sqlite":
        from app.repositories.sqlite_store import SqliteSessionRepository

        return SqliteSessionRepository()
    raise ValueError(f"Unknown REPOSITORY_BACKEND={backend!r}; supported: json, sqlite")


def _make_engagement_repo(backend: str) -> EngagementRepository:
    if backend == "json":
        return JsonEngagementRepository()
    if backend == "sqlite":
        from app.repositories.sqlite_store import SqliteEngagementRepository

        return SqliteEngagementRepository()
    raise ValueError(f"Unknown REPOSITORY_BACKEND={backend!r}; supported: json, sqlite")


# Backend-keyed singletons — lazily initialised, cheap to construct.
_session_repo: tuple[str, SessionRepository] | None = None
_engagement_repo: tuple[str, EngagementRepository] | None = None


def session_repo() -> SessionRepository:
    global _session_repo
    backend = active_backend()
    if _session_repo is None or _session_repo[0] != backend:
        _session_repo = (backend, _make_session_repo(backend))
    return _session_repo[1]


def engagement_repo() -> EngagementRepository:
    global _engagement_repo
    backend = active_backend()
    if _engagement_repo is None or _engagement_repo[0] != backend:
        _engagement_repo = (backend, _make_engagement_repo(backend))
    return _engagement_repo[1]


__all__ = [
    "EngagementRepository",
    "SessionRepository",
    "JsonEngagementRepository",
    "JsonSessionRepository",
    "active_backend",
    "session_repo",
    "engagement_repo",
]
