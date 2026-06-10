"""tests/test_repositories.py — P2-11: repository interface."""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Interface contract
# ---------------------------------------------------------------------------

def test_session_repo_interface_methods():
    """SessionRepository exposes the required abstract methods."""
    from app.repositories.base import SessionRepository
    import inspect

    abstract_methods = {
        name for name, _ in inspect.getmembers(SessionRepository, predicate=inspect.isfunction)
        if getattr(getattr(SessionRepository, name), "__isabstractmethod__", False)
    }
    assert abstract_methods == {"get", "save", "exists", "list_ids", "delete"}


def test_engagement_repo_interface_methods():
    """EngagementRepository exposes the required abstract methods."""
    from app.repositories.base import EngagementRepository
    import inspect

    abstract_methods = {
        name for name, _ in inspect.getmembers(EngagementRepository, predicate=inspect.isfunction)
        if getattr(getattr(EngagementRepository, name), "__isabstractmethod__", False)
    }
    assert abstract_methods == {"get", "save", "exists", "list_all", "list_for_owner", "delete"}


# ---------------------------------------------------------------------------
# JsonSessionRepository
# ---------------------------------------------------------------------------

def test_json_session_repo_instantiates():
    from app.repositories.json_store import JsonSessionRepository

    repo = JsonSessionRepository()
    assert repo is not None


def test_json_session_repo_implements_interface():
    from app.repositories.base import SessionRepository
    from app.repositories.json_store import JsonSessionRepository

    assert issubclass(JsonSessionRepository, SessionRepository)


def test_json_session_repo_not_exists_for_unknown():
    from app.repositories.json_store import JsonSessionRepository

    repo = JsonSessionRepository()
    assert not repo.exists("nonexistent-session-000")


def test_json_session_repo_raises_on_missing_get():
    from app.repositories.json_store import JsonSessionRepository

    repo = JsonSessionRepository()
    with pytest.raises((KeyError, Exception)):
        repo.get("nonexistent-session-000")


def test_json_session_repo_list_ids_is_list():
    from app.repositories.json_store import JsonSessionRepository

    repo = JsonSessionRepository()
    result = repo.list_ids()
    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# JsonEngagementRepository
# ---------------------------------------------------------------------------

def test_json_engagement_repo_instantiates():
    from app.repositories.json_store import JsonEngagementRepository

    repo = JsonEngagementRepository()
    assert repo is not None


def test_json_engagement_repo_implements_interface():
    from app.repositories.base import EngagementRepository
    from app.repositories.json_store import JsonEngagementRepository

    assert issubclass(JsonEngagementRepository, EngagementRepository)


def test_json_engagement_repo_not_exists_for_unknown():
    from app.repositories.json_store import JsonEngagementRepository

    repo = JsonEngagementRepository()
    assert not repo.exists("nonexistent-engagement-000")


def test_json_engagement_repo_raises_on_missing_get():
    from app.repositories.json_store import JsonEngagementRepository

    repo = JsonEngagementRepository()
    with pytest.raises((KeyError, Exception)):
        repo.get("nonexistent-engagement-000")


def test_json_engagement_repo_list_all_is_list():
    from app.repositories.json_store import JsonEngagementRepository

    repo = JsonEngagementRepository()
    result = repo.list_all()
    assert isinstance(result, list)


def test_json_engagement_repo_list_for_owner_none():
    from app.repositories.json_store import JsonEngagementRepository

    repo = JsonEngagementRepository()
    result = repo.list_for_owner(None)
    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Module-level factories
# ---------------------------------------------------------------------------

def test_session_repo_factory_returns_session_repo():
    from app.repositories import session_repo
    from app.repositories.base import SessionRepository

    repo = session_repo()
    assert isinstance(repo, SessionRepository)


def test_engagement_repo_factory_returns_engagement_repo():
    from app.repositories import engagement_repo
    from app.repositories.base import EngagementRepository

    repo = engagement_repo()
    assert isinstance(repo, EngagementRepository)


def test_factories_return_singletons():
    from app.repositories import session_repo, engagement_repo

    assert session_repo() is session_repo()
    assert engagement_repo() is engagement_repo()


def test_unknown_backend_raises():
    import os
    from unittest.mock import patch

    with patch.dict(os.environ, {"REPOSITORY_BACKEND": "postgres"}):
        import importlib
        import app.repositories as repo_module
        importlib.reload(repo_module)
        with pytest.raises(ValueError, match="Unknown REPOSITORY_BACKEND"):
            repo_module._make_session_repo()
    # Restore
    importlib.reload(repo_module)
