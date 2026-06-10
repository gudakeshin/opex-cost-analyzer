"""JSON-file-backed repository implementations.

Each method delegates to the existing storage helpers (app.routers._shared and
app.services.engagements_store) so there is no duplication of atomic-write,
locking, or path-resolution logic.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.repositories.base import EngagementRepository, SessionRepository


class JsonSessionRepository(SessionRepository):
    """Session manifests stored as JSON files under DATA_DIR/sessions/<id>/manifest.json."""

    def get(self, session_id: str) -> Dict[str, Any]:
        from app.routers._shared import manifest_path, read_manifest, validate_session_id

        validate_session_id(session_id)
        if not manifest_path(session_id).exists():
            raise KeyError(f"Session not found: {session_id}")
        return read_manifest(session_id)

    def save(self, session_id: str, manifest: Dict[str, Any]) -> None:
        from app.routers._shared import validate_session_id, write_manifest

        validate_session_id(session_id)
        write_manifest(session_id, manifest)

    def exists(self, session_id: str) -> bool:
        from app.routers._shared import manifest_path

        try:
            return manifest_path(session_id).exists()
        except Exception:
            return False

    def list_ids(self) -> List[str]:
        from app.config import DATA_DIR

        sessions_dir = DATA_DIR / "sessions"
        if not sessions_dir.exists():
            return []
        return [
            p.name
            for p in sessions_dir.iterdir()
            if p.is_dir() and (p / "manifest.json").exists()
        ]

    def delete(self, session_id: str) -> None:
        import shutil

        from app.routers._shared import session_dir, validate_session_id

        validate_session_id(session_id)
        path = session_dir(session_id)
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)


class JsonEngagementRepository(EngagementRepository):
    """Engagement manifests stored as JSON files under DATA_DIR/engagements/<id>/manifest.json."""

    def get(self, engagement_id: str) -> Dict[str, Any]:
        from app.services.engagements_store import read_engagement_manifest
        from app.routers._shared import validate_engagement_id

        validate_engagement_id(engagement_id)
        try:
            return read_engagement_manifest(engagement_id)
        except Exception as exc:
            raise KeyError(f"Engagement not found: {engagement_id}") from exc

    def save(self, engagement_id: str, manifest: Dict[str, Any]) -> None:
        from app.services.engagements_store import write_engagement_manifest
        from app.routers._shared import validate_engagement_id

        validate_engagement_id(engagement_id)
        write_engagement_manifest(engagement_id, manifest)

    def exists(self, engagement_id: str) -> bool:
        from app.services.engagements_store import engagement_manifest_path
        from app.routers._shared import validate_engagement_id

        try:
            validate_engagement_id(engagement_id)
            return engagement_manifest_path(engagement_id).exists()
        except Exception:
            return False

    def list_all(self) -> List[Dict[str, Any]]:
        from app.services.engagements_store import list_engagements

        return list_engagements()

    def list_for_owner(self, owner: Optional[str]) -> List[Dict[str, Any]]:
        from app.services.engagements_store import list_engagements

        all_engagements = list_engagements()
        if owner is None:
            return all_engagements
        # Legacy records with no owner field are visible to all principals (same
        # semantics as auth.visible_to_principal, but without needing a Request).
        return [
            e for e in all_engagements
            if not e.get("owner") or e.get("owner") == owner
        ]

    def delete(self, engagement_id: str) -> None:
        from app.services.engagements_store import delete_engagement
        from app.routers._shared import validate_engagement_id

        validate_engagement_id(engagement_id)
        delete_engagement(engagement_id)
