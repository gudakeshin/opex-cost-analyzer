"""Abstract repository interfaces for session and engagement persistence.

Concrete implementations live alongside this file (json_store.py, sqlite_store.py, …).
Business logic should depend only on these interfaces — never on the concrete classes.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class SessionRepository(ABC):
    """CRUD for session manifests."""

    @abstractmethod
    def get(self, session_id: str) -> Dict[str, Any]:
        """Return the session manifest.  Raises KeyError when not found."""
        ...

    @abstractmethod
    def save(self, session_id: str, manifest: Dict[str, Any]) -> None:
        """Atomically persist the session manifest."""
        ...

    @abstractmethod
    def exists(self, session_id: str) -> bool:
        """True when a manifest exists for *session_id*."""
        ...

    @abstractmethod
    def list_ids(self) -> List[str]:
        """All session IDs known to this backend."""
        ...

    @abstractmethod
    def delete(self, session_id: str) -> None:
        """Remove a session and all associated files.  No-op when not found."""
        ...


class EngagementRepository(ABC):
    """CRUD for engagement manifests."""

    @abstractmethod
    def get(self, engagement_id: str) -> Dict[str, Any]:
        """Return the engagement manifest.  Raises KeyError when not found."""
        ...

    @abstractmethod
    def save(self, engagement_id: str, manifest: Dict[str, Any]) -> None:
        """Atomically persist the engagement manifest."""
        ...

    @abstractmethod
    def exists(self, engagement_id: str) -> bool:
        """True when a manifest exists for *engagement_id*."""
        ...

    @abstractmethod
    def list_all(self) -> List[Dict[str, Any]]:
        """Return all engagement manifests as a list of dicts."""
        ...

    @abstractmethod
    def list_for_owner(self, owner: Optional[str]) -> List[Dict[str, Any]]:
        """Return engagements visible to *owner* (None = all).

        Ownership semantics mirror the current JSON-store behaviour:
        legacy records (no owner field) are visible to every principal.
        """
        ...

    @abstractmethod
    def delete(self, engagement_id: str) -> None:
        """Teardown an engagement and all associated documents.  No-op when not found."""
        ...
