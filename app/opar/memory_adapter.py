from __future__ import annotations

from abc import ABC, abstractmethod
import os
from typing import Any, Dict, List

from app.config import QDRANT_ENABLED
from app.memory import MemoryStore

_ADAPTER_SINGLETON: MemoryAdapterInterface | None = None
_ADAPTER_META: Dict[str, Any] = {
    "backend": "local",
    "qdrant_enabled": QDRANT_ENABLED,
    "qdrant_active": False,
    "reason": "default_local",
}


def _try_init_qdrant() -> MemoryAdapterInterface | None:
    global _ADAPTER_SINGLETON
    try:
        from app.opar.qdrant_memory_adapter import QdrantMemoryAdapter
        adapter = QdrantMemoryAdapter()
        _ADAPTER_SINGLETON = adapter  # type: ignore[assignment]
        active = getattr(adapter, "_qdrant_ok", False)
        _ADAPTER_META.update(
            {
                "backend": "qdrant" if active else "local",
                "qdrant_enabled": True,
                "qdrant_active": active,
                "reason": "ok" if active else "qdrant_unreachable_using_local_fallback",
            }
        )
        return _ADAPTER_SINGLETON
    except ImportError as e:
        _ADAPTER_META.update({"backend": "local", "qdrant_enabled": False, "qdrant_active": False, "reason": f"qdrant_import_error:{e}"})
        return None
    except Exception as e:
        _ADAPTER_META.update({"backend": "local", "qdrant_enabled": False, "qdrant_active": False, "reason": f"qdrant_init_failed:{type(e).__name__}"})
        return None


class MemoryAdapterInterface(ABC):
    """Abstract interface for OPAR memory access."""

    @abstractmethod
    def get_user_memory(self, user_id: str) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def get_session_memory(self, session_id: str, query: str = "", limit: int = 10) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def get_agent_memories(self, skill_names: List[str]) -> Dict[str, List[Dict[str, Any]]]:
        pass

    @abstractmethod
    def add_session(self, session_id: str, content: Dict[str, Any], metadata: Dict[str, Any] | None = None) -> None:
        pass

    @abstractmethod
    def add_user(self, user_id: str, content: Dict[str, Any]) -> None:
        pass

    @abstractmethod
    def add_agent(self, agent_id: str, content: Dict[str, Any]) -> None:
        pass

    # v2.0 engagement scope
    @abstractmethod
    def get_engagement_memory(self, engagement_id: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    def add_engagement(self, engagement_id: str, content: Dict[str, Any]) -> None:
        pass

    @abstractmethod
    def teardown_engagement(self, engagement_id: str) -> Dict[str, Any]:
        pass


class LocalMemoryAdapter(MemoryAdapterInterface):
    """File-backed memory using existing MemoryStore."""

    def __init__(self) -> None:
        self._store = MemoryStore()

    def get_user_memory(self, user_id: str) -> List[Dict[str, Any]]:
        data = self._store.get("user", user_id)
        return [data] if data else []

    def get_session_memory(self, session_id: str, query: str = "", limit: int = 10) -> List[Dict[str, Any]]:
        opar_key = f"{session_id}_opar"
        data = self._store.get("session", opar_key)
        if not data:
            return []
        entries = data.get("entries", []) if isinstance(data, dict) else []
        return entries[:limit]

    def get_agent_memories(self, skill_names: List[str]) -> Dict[str, List[Dict[str, Any]]]:
        out: Dict[str, List[Dict[str, Any]]] = {}
        for name in skill_names:
            data = self._store.get("agent", name)
            opar_data = self._store.get("agent", f"{name}_opar")
            entries = opar_data.get("entries", []) if isinstance(opar_data, dict) else []
            if not entries and data:
                entries = [data]
            out[name] = entries
        return out

    def add_session(self, session_id: str, content: Dict[str, Any], metadata: Dict[str, Any] | None = None) -> None:
        opar_key = f"{session_id}_opar"
        existing = self._store.get("session", opar_key)
        entries = existing.get("entries", []) if isinstance(existing, dict) else []
        entries.append({"content": content, "metadata": metadata or {}})
        self._store.put("session", opar_key, {"entries": entries})

    def add_user(self, user_id: str, content: Dict[str, Any]) -> None:
        self._store.put("user", user_id, content)

    def add_agent(self, agent_id: str, content: Dict[str, Any]) -> None:
        opar_key = f"{agent_id}_opar"
        existing = self._store.get("agent", opar_key)
        entries = existing.get("entries", []) if isinstance(existing, dict) else []
        entries.append(content)
        self._store.put("agent", opar_key, {"entries": entries})

    def get_engagement_memory(self, engagement_id: str) -> Dict[str, Any]:
        return self._store.get_engagement(engagement_id)

    def add_engagement(self, engagement_id: str, content: Dict[str, Any]) -> None:
        existing = self._store.get_engagement(engagement_id)
        existing.update(content)
        self._store.put_engagement(engagement_id, existing)

    def teardown_engagement(self, engagement_id: str) -> Dict[str, Any]:
        return self._store.teardown_engagement(engagement_id)


def get_memory_adapter() -> MemoryAdapterInterface:
    """Return the memory adapter. Qdrant is preferred; falls back to local file store."""
    global _ADAPTER_SINGLETON

    # Tests always use the lightweight local file adapter.
    if os.getenv("PYTEST_CURRENT_TEST"):
        _ADAPTER_SINGLETON = LocalMemoryAdapter()
        _ADAPTER_META.update({"backend": "local", "qdrant_enabled": False, "qdrant_active": False, "reason": "pytest_forced_local"})
        return _ADAPTER_SINGLETON

    # Reuse existing adapter after successful initialization.
    if _ADAPTER_SINGLETON is not None:
        return _ADAPTER_SINGLETON

    if QDRANT_ENABLED:
        adapter = _try_init_qdrant()
        if adapter is not None:
            return adapter

    # Definitive fallback: local file-backed store.
    _ADAPTER_SINGLETON = LocalMemoryAdapter()
    _ADAPTER_META.update({"backend": "local", "qdrant_enabled": False, "qdrant_active": False, "reason": "qdrant_disabled_or_failed"})
    return _ADAPTER_SINGLETON


def get_memory_adapter_status() -> Dict[str, Any]:
    """Expose backend status for diagnostics/health endpoint."""
    get_memory_adapter()
    return dict(_ADAPTER_META)
