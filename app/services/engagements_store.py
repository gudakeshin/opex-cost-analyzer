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
    if engagement_id:
        try:
            uuid.UUID(engagement_id, version=4)
        except ValueError as exc:
            raise ValueError(f"Invalid engagement_id (must be UUID v4): {engagement_id!r}") from exc
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
        # Auto-detected recommendations from uploaded documents (see
        # engagement_detection.detect_engagement_profile). Kept separate from the
        # user-facing company_name/industry so the UI can show a "Recommended"
        # badge even after the user overrides.
        "detected_company_name": "",
        "detected_industry": "",
        "detected_industry_label": "",
        "detection_signals": {},
        "context_text_hash": "",
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
        "session_ids": [],
        "documents": [],
    }
    write_engagement_manifest(eid, manifest)
    return manifest


def update_engagement_detection(engagement_id: str, detection: Dict[str, Any]) -> Dict[str, Any]:
    """Persist auto-detected company/industry on the engagement manifest.

    The detected values are always stored (so the UI can surface a recommendation
    and flag overrides), but the user-facing ``company_name``/``industry`` fields
    are only auto-filled when the user has *not* already set them — a placeholder
    ``"New engagement"`` company or an empty industry. An explicit user choice is
    never overwritten.
    """
    manifest = read_engagement_manifest(engagement_id)
    if not manifest.get("engagement_id"):
        return {}

    detected_company = str(detection.get("detected_company_name") or "").strip()
    detected_industry = str(detection.get("detected_industry") or "").strip()

    manifest["detected_company_name"] = detected_company
    manifest["detected_industry"] = detected_industry
    manifest["detected_industry_label"] = str(detection.get("detected_industry_label") or "")
    manifest["detection_signals"] = {
        "industry_source": str(detection.get("industry_source") or ""),
        "industry_llm": str(detection.get("industry_llm") or ""),
        "industry_spend": str(detection.get("industry_spend") or ""),
        "source_documents": detection.get("source_documents") or {},
    }
    manifest["context_text_hash"] = str(detection.get("context_text_hash") or "")

    # Auto-apply only when the user hasn't made an explicit choice.
    current_company = str(manifest.get("company_name") or "").strip()
    if detected_company and current_company in ("", "New engagement"):
        manifest["company_name"] = detected_company
    current_industry = str(manifest.get("industry") or "").strip()
    if detected_industry and not current_industry:
        manifest["industry"] = detected_industry

    manifest["updated_at"] = _utc_now()
    write_engagement_manifest(engagement_id, manifest)
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
            "detected_company_name": manifest.get("detected_company_name") or "",
            "detected_industry": manifest.get("detected_industry") or "",
            "detected_industry_label": manifest.get("detected_industry_label") or "",
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


def parent_nodes_path(engagement_id: str, document_id: str) -> Path:
    """Filesystem doc store for hierarchical parent nodes (keyed by parent_id)."""
    return document_parsed_dir(engagement_id, document_id) / "parent_nodes.json"


def write_parent_nodes(engagement_id: str, document_id: str, parents: List[Any]) -> None:
    """Persist parent nodes as a JSON KV map {parent_id: parent_dict}."""
    store: Dict[str, Any] = {}
    for p in parents:
        d = p.to_dict() if hasattr(p, "to_dict") else dict(p)
        store[d["parent_id"]] = d
    write_json(parent_nodes_path(engagement_id, document_id), store)


def load_parent_nodes(engagement_id: str, document_id: str) -> Dict[str, Any]:
    data = read_json(parent_nodes_path(engagement_id, document_id), {})
    return data if isinstance(data, dict) else {}


def load_parent_node(engagement_id: str, document_id: str, parent_id: str) -> Optional[Dict[str, Any]]:
    return load_parent_nodes(engagement_id, document_id).get(parent_id)


def child_nodes_path(engagement_id: str, document_id: str) -> Path:
    """Local store of child (leaf) nodes — used by the keyword fallback + reindex."""
    return document_parsed_dir(engagement_id, document_id) / "child_nodes.json"


def write_child_nodes(engagement_id: str, document_id: str, children: List[Any]) -> None:
    payload = [c.to_dict() if hasattr(c, "to_dict") else dict(c) for c in children]
    write_json(child_nodes_path(engagement_id, document_id), payload)


def load_child_nodes(engagement_id: str, document_id: str) -> List[Dict[str, Any]]:
    data = read_json(child_nodes_path(engagement_id, document_id), [])
    return data if isinstance(data, list) else []


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
