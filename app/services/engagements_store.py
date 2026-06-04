"""File-backed engagement manifests and document storage."""
from __future__ import annotations

import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from app.config import ENGAGEMENTS_DIR
from app.storage import read_json, write_json

TABULAR_EXTENSIONS = {".csv", ".xlsx", ".xls", ".json"}
DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".txt"}
SUPPORTED_EXTENSIONS = TABULAR_EXTENSIONS | DOCUMENT_EXTENSIONS


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def engagement_dir(engagement_id: str) -> Path:
    return ENGAGEMENTS_DIR / engagement_id


def engagement_manifest_path(engagement_id: str) -> Path:
    return engagement_dir(engagement_id) / "manifest.json"


def document_dir(engagement_id: str, document_id: str) -> Path:
    return engagement_dir(engagement_id) / "documents" / document_id


def read_engagement_manifest(engagement_id: str) -> Dict[str, Any]:
    return read_json(engagement_manifest_path(engagement_id), {})


def write_engagement_manifest(engagement_id: str, payload: Dict[str, Any]) -> None:
    write_json(engagement_manifest_path(engagement_id), payload)


def ensure_engagement_exists(engagement_id: str) -> Dict[str, Any]:
    manifest = read_engagement_manifest(engagement_id)
    if not manifest.get("engagement_id"):
        raise HTTPException(status_code=404, detail="Engagement not found")
    return manifest


def create_engagement_manifest(
    *,
    company_name: str | None = None,
    industry: str | None = None,
    annual_revenue: float = 0.0,
    currency: str | None = None,
    headcount: float | None = None,
    engagement_id: str | None = None,
) -> Dict[str, Any]:
    eid = engagement_id or str(uuid.uuid4())
    root = engagement_dir(eid)
    root.mkdir(parents=True, exist_ok=True)
    (root / "documents").mkdir(parents=True, exist_ok=True)
    manifest: Dict[str, Any] = {
        "engagement_id": eid,
        "company_name": company_name or "New engagement",
        "industry": industry or "",
        "annual_revenue": annual_revenue,
        "currency": currency or "INR",
        "headcount": headcount if headcount and headcount > 0 else None,
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
        "session_ids": [],
        "documents": [],
    }
    write_engagement_manifest(eid, manifest)
    return manifest


def register_session_on_engagement(engagement_id: str, session_id: str) -> None:
    manifest = ensure_engagement_exists(engagement_id)
    sessions = list(manifest.get("session_ids") or [])
    if session_id not in sessions:
        sessions.append(session_id)
        manifest["session_ids"] = sessions
        manifest["updated_at"] = _utc_now()
        write_engagement_manifest(engagement_id, manifest)


def list_engagements() -> List[Dict[str, Any]]:
    if not ENGAGEMENTS_DIR.exists():
        return []
    summaries: List[Dict[str, Any]] = []
    for path in ENGAGEMENTS_DIR.iterdir():
        if not path.is_dir():
            continue
        try:
            uuid.UUID(path.name, version=4)
        except ValueError:
            continue
        manifest = read_engagement_manifest(path.name)
        if not manifest.get("engagement_id"):
            continue
        docs = manifest.get("documents") or []
        summaries.append({
            "engagement_id": manifest["engagement_id"],
            "company_name": manifest.get("company_name") or "Unknown",
            "industry": manifest.get("industry") or "",
            "currency": manifest.get("currency") or "INR",
            "annual_revenue": manifest.get("annual_revenue"),
            "created_at": manifest.get("created_at"),
            "updated_at": manifest.get("updated_at"),
            "session_count": len(manifest.get("session_ids") or []),
            "document_count": len(docs),
            "documents_ready": sum(1 for d in docs if d.get("status") == "ready"),
        })
    summaries.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
    return summaries


def classify_document_role(suffix: str) -> str:
    ext = suffix.lower()
    if ext in (".csv", ".xlsx", ".xls", ".json"):
        return "spend_tabular"
    if ext == ".pdf":
        return "mixed"
    return "context_doc"


def add_document_record(
    engagement_id: str,
    *,
    document_id: str,
    filename: str,
    content_type: str,
    size_bytes: int,
    raw_path: str,
) -> Dict[str, Any]:
    manifest = ensure_engagement_exists(engagement_id)
    suffix = Path(filename).suffix.lower()
    record: Dict[str, Any] = {
        "document_id": document_id,
        "filename": filename,
        "content_type": content_type,
        "size_bytes": size_bytes,
        "raw_path": raw_path,
        "role": classify_document_role(suffix),
        "status": "pending",
        "parse_backend": None,
        "error": None,
        "uploaded_at": _utc_now(),
        "processed_at": None,
        "text_preview": None,
        "line_count": 0,
    }
    docs = list(manifest.get("documents") or [])
    docs.append(record)
    manifest["documents"] = docs
    manifest["updated_at"] = _utc_now()
    write_engagement_manifest(engagement_id, manifest)
    return record


def update_document_record(engagement_id: str, document_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
    manifest = ensure_engagement_exists(engagement_id)
    docs = list(manifest.get("documents") or [])
    updated: Optional[Dict[str, Any]] = None
    for i, doc in enumerate(docs):
        if doc.get("document_id") == document_id:
            merged = {**doc, **patch}
            docs[i] = merged
            updated = merged
            break
    if updated is None:
        raise HTTPException(status_code=404, detail="Document not found")
    manifest["documents"] = docs
    manifest["updated_at"] = _utc_now()
    write_engagement_manifest(engagement_id, manifest)
    return updated


def get_document_record(engagement_id: str, document_id: str) -> Dict[str, Any]:
    manifest = ensure_engagement_exists(engagement_id)
    for doc in manifest.get("documents") or []:
        if doc.get("document_id") == document_id:
            return doc
    raise HTTPException(status_code=404, detail="Document not found")


def delete_document(engagement_id: str, document_id: str) -> None:
    ensure_engagement_exists(engagement_id)
    ddir = document_dir(engagement_id, document_id)
    if ddir.exists():
        shutil.rmtree(ddir, ignore_errors=True)
    manifest = read_engagement_manifest(engagement_id)
    manifest["documents"] = [
        d for d in (manifest.get("documents") or []) if d.get("document_id") != document_id
    ]
    manifest["updated_at"] = _utc_now()
    write_engagement_manifest(engagement_id, manifest)


def document_meta_path(engagement_id: str, document_id: str) -> Path:
    return document_dir(engagement_id, document_id) / "meta.json"


def document_parsed_dir(engagement_id: str, document_id: str) -> Path:
    path = document_dir(engagement_id, document_id) / "parsed"
    path.mkdir(parents=True, exist_ok=True)
    return path


def backfill_engagement_for_session(session_id: str, manifest: Dict[str, Any]) -> str:
    """Ensure session manifest has engagement_id; create engagement if missing."""
    eid = str(manifest.get("engagement_id") or "").strip()
    if eid:
        try:
            ensure_engagement_exists(eid)
            register_session_on_engagement(eid, session_id)
            return eid
        except HTTPException:
            pass
    eid = session_id
    if not engagement_manifest_path(eid).exists():
        create_engagement_manifest(
            engagement_id=eid,
            company_name=manifest.get("company_name"),
            industry=manifest.get("industry"),
            annual_revenue=float(manifest.get("annual_revenue") or 0.0),
            currency=manifest.get("currency"),
            headcount=manifest.get("headcount"),
        )
    register_session_on_engagement(eid, session_id)
    return eid
