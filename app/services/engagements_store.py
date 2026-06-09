"""File-backed engagement manifests and document storage."""
from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException
from pydantic import ValidationError

from app.config import ENGAGEMENTS_DIR, logger
from app.schemas import EngagementManifest
from app.services.engagement_sanity import should_auto_apply_company
from app.services.manifest_lock import ManifestLockError, manifest_lock
from app.storage import read_json, write_json

TABULAR_EXTENSIONS = {".csv", ".xlsx", ".xls", ".json"}
DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}
SUPPORTED_EXTENSIONS = TABULAR_EXTENSIONS | DOCUMENT_EXTENSIONS
_MANIFEST_BACKUP_NAME = "manifest.json.bak"


class ManifestReadError(Exception):
    def __init__(self, engagement_id: str, reason: str) -> None:
        self.engagement_id = engagement_id
        self.reason = reason
        super().__init__(reason)


class ManifestValidationError(Exception):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def engagement_dir(engagement_id: str) -> Path:
    return ENGAGEMENTS_DIR / engagement_id


def engagement_manifest_path(engagement_id: str) -> Path:
    return engagement_dir(engagement_id) / "manifest.json"


def document_dir(engagement_id: str, document_id: str) -> Path:
    return engagement_dir(engagement_id) / "documents" / document_id


def classify_document_role(suffix: str) -> str:
    ext = suffix.lower()
    if ext in (".csv", ".xlsx", ".xls", ".json"):
        return "spend_tabular"
    if ext == ".pdf":
        return "mixed"
    return "context_doc"


def _infer_upload_filename(raw_path: Path) -> str:
    stem = raw_path.stem
    if stem != "raw":
        return raw_path.name
    return f"upload{raw_path.suffix}"


def _read_document_meta(ddir: Path) -> Dict[str, Any]:
    meta_path = ddir / "meta.json"
    if not meta_path.is_file():
        return {}
    try:
        payload = read_json(meta_path, {})
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def write_document_meta(
    engagement_id: str,
    document_id: str,
    *,
    filename: str,
    content_type: str = "application/octet-stream",
) -> None:
    """Persist the original upload filename beside the raw blob for manifest repair."""
    ddir = document_dir(engagement_id, document_id)
    ddir.mkdir(parents=True, exist_ok=True)
    write_json(
        ddir / "meta.json",
        {"filename": filename, "content_type": content_type},
    )


def _document_record_from_disk(engagement_id: str, document_id: str) -> Optional[Dict[str, Any]]:
    ddir = document_dir(engagement_id, document_id)
    if not ddir.is_dir():
        return None
    raw_files = sorted(ddir.glob("raw.*"))
    if not raw_files:
        return None
    raw_path = raw_files[0]
    suffix = raw_path.suffix.lower()
    stat = raw_path.stat()
    meta = _read_document_meta(ddir)
    filename = str(meta.get("filename") or "").strip() or _infer_upload_filename(raw_path)
    return {
        "document_id": document_id,
        "filename": filename,
        "content_type": "application/octet-stream",
        "size_bytes": stat.st_size,
        "raw_path": str(raw_path),
        "role": classify_document_role(suffix),
        "status": "pending",
        "parse_backend": None,
        "error": None,
        "uploaded_at": _utc_now(),
        "processed_at": None,
        "text_preview": None,
        "line_count": 0,
    }


def _normalize_document_records(manifest: Dict[str, Any]) -> bool:
    """Fix inconsistent status flags left by older manifest repair/dedupe paths."""
    changed = False
    for doc in manifest.get("documents") or []:
        if not isinstance(doc, dict):
            continue
        if (
            doc.get("processed_at")
            and not doc.get("error")
            and str(doc.get("status") or "") != "ready"
        ):
            doc["status"] = "ready"
            changed = True
    if changed:
        manifest["updated_at"] = _utc_now()
    return changed


def _dedupe_manifest_documents(manifest: Dict[str, Any]) -> bool:
    """Collapse duplicate manifest rows that share the same document_id."""
    docs = [d for d in (manifest.get("documents") or []) if isinstance(d, dict)]
    if not docs:
        return False

    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for doc in docs:
        did = str(doc.get("document_id") or "").strip()
        if not did:
            continue
        grouped.setdefault(did, []).append(doc)
    if all(len(group) == 1 for group in grouped.values()):
        return False

    def _score(doc: Dict[str, Any]) -> int:
        filename = str(doc.get("filename") or "")
        score = 0
        if filename and not filename.startswith("upload."):
            score += 100
        if doc.get("status") == "ready":
            score += 50
        if doc.get("processed_at"):
            score += 10
        if doc.get("line_count"):
            score += 5
        return score

    merged: List[Dict[str, Any]] = []
    for group in grouped.values():
        best = max(group, key=_score)
        for other in group:
            if other is best:
                continue
            for key in (
                "parse_backend",
                "processed_at",
                "text_preview",
                "line_count",
                "warnings",
                "chunk_count",
                "parent_count",
                "indexed",
                "index_backend",
                "error",
            ):
                if not best.get(key) and other.get(key):
                    best[key] = other[key]
        if any(str(other.get("status") or "") == "ready" for other in group):
            best["status"] = "ready"
        merged.append(best)

    manifest["documents"] = merged
    manifest["updated_at"] = _utc_now()
    logger.warning(
        "manifest_deduped_documents engagement_id=%s before=%s after=%s",
        manifest.get("engagement_id"),
        len(docs),
        len(merged),
    )
    return True


def _repair_manifest_documents(
    engagement_id: str,
    manifest: Dict[str, Any],
    *,
    exclude_ids: Optional[set[str]] = None,
) -> bool:
    """Ensure every on-disk document folder appears in the manifest."""
    docs_dir = engagement_dir(engagement_id) / "documents"
    if not docs_dir.is_dir():
        return False
    known = {str(d.get("document_id")) for d in (manifest.get("documents") or [])}
    skip = exclude_ids or set()
    recovered: List[Dict[str, Any]] = []
    for path in docs_dir.iterdir():
        if not path.is_dir():
            continue
        try:
            uuid.UUID(path.name, version=4)
        except ValueError:
            continue
        if path.name in known or path.name in skip:
            continue
        record = _document_record_from_disk(engagement_id, path.name)
        if record:
            recovered.append(record)
    if not recovered:
        return False
    manifest["documents"] = list(manifest.get("documents") or []) + recovered
    manifest["updated_at"] = _utc_now()
    logger.warning(
        "manifest_recovered_orphan_documents engagement_id=%s count=%s",
        engagement_id,
        len(recovered),
    )
    return True


def _skeleton_manifest(engagement_id: str) -> Dict[str, Any]:
    now = _utc_now()
    return {
        "engagement_id": engagement_id,
        "company_name": "Recovered engagement",
        "industry": "",
        "annual_revenue": 0.0,
        "currency": "INR",
        "headcount": None,
        "detected_company_name": "",
        "detected_industry": "",
        "detected_industry_label": "",
        "detected_annual_revenue_cr": None,
        "detection_signals": {},
        "context_text_hash": "",
        "created_at": now,
        "updated_at": now,
        "session_ids": [],
        "documents": [],
    }


def _parse_manifest_file(engagement_id: str) -> Tuple[Dict[str, Any], bool, Optional[str]]:
    """Return manifest dict, needs_rewrite flag, and optional parse error."""
    path = engagement_manifest_path(engagement_id)
    if not path.exists():
        return {}, False, None
    text = path.read_text(encoding="utf-8")
    try:
        manifest = json.loads(text)
        if not isinstance(manifest, dict):
            return {}, False, "manifest root is not an object"
        needs_rewrite = False
    except json.JSONDecodeError as exc:
        if "Extra data" not in str(exc):
            return {}, False, str(exc)
        manifest, end = json.JSONDecoder().raw_decode(text)
        if not isinstance(manifest, dict):
            return {}, False, "salvaged manifest root is not an object"
        needs_rewrite = end < len(text.strip())
        logger.warning(
            "manifest_extra_data engagement_id=%s trailing_bytes=%s",
            engagement_id,
            len(text) - end,
        )
    return manifest, needs_rewrite, None


def _validate_and_normalize(payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return EngagementManifest.model_validate(payload).model_dump(mode="json")
    except ValidationError as exc:
        logger.error("manifest_validation_failed errors=%s", exc.errors())
        raise ManifestValidationError(str(exc)) from exc


def _backup_manifest(path: Path) -> None:
    if not path.exists():
        return
    backup_path = path.with_name(_MANIFEST_BACKUP_NAME)
    shutil.copy2(path, backup_path)


def _write_manifest_payload(engagement_id: str, payload: Dict[str, Any]) -> None:
    """Validate, backup, and atomically persist a manifest (caller must hold lock)."""
    path = engagement_manifest_path(engagement_id)
    normalized = _validate_and_normalize(payload)
    _backup_manifest(path)
    write_json(path, normalized)


def write_engagement_manifest(engagement_id: str, payload: Dict[str, Any]) -> None:
    try:
        with manifest_lock.acquire(engagement_id):
            _write_manifest_payload(engagement_id, payload)
    except ManifestLockError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ManifestValidationError as exc:
        raise HTTPException(status_code=500, detail=f"Invalid engagement manifest: {exc}") from exc


def read_engagement_manifest(engagement_id: str, *, auto_repair: bool = True) -> Dict[str, Any]:
    manifest, needs_rewrite, parse_error = _parse_manifest_file(engagement_id)
    if parse_error:
        if auto_repair:
            return repair_engagement_manifest(engagement_id)
        raise ManifestReadError(engagement_id, parse_error)

    if not manifest.get("engagement_id"):
        if auto_repair and engagement_dir(engagement_id).exists():
            return repair_engagement_manifest(engagement_id)
        return manifest if isinstance(manifest, dict) else {}

    repaired_orphans = _repair_manifest_documents(engagement_id, manifest)
    deduped = _dedupe_manifest_documents(manifest)
    normalized = _normalize_document_records(manifest)
    if auto_repair and (needs_rewrite or repaired_orphans or deduped or normalized):
        write_engagement_manifest(engagement_id, manifest)
    return manifest


def repair_engagement_manifest(engagement_id: str) -> Dict[str, Any]:
    """Rebuild manifest from salvageable JSON plus on-disk document folders."""
    manifest, _, parse_error = _parse_manifest_file(engagement_id)
    if parse_error or not manifest.get("engagement_id"):
        logger.warning(
            "manifest_full_repair engagement_id=%s parse_error=%s",
            engagement_id,
            parse_error,
        )
        manifest = _skeleton_manifest(engagement_id)
    _repair_manifest_documents(engagement_id, manifest)
    _dedupe_manifest_documents(manifest)
    _normalize_document_records(manifest)
    write_engagement_manifest(engagement_id, manifest)
    return manifest


def ensure_engagement_exists(engagement_id: str) -> Dict[str, Any]:
    try:
        manifest = read_engagement_manifest(engagement_id)
    except ManifestReadError as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Engagement manifest is corrupt ({exc.reason}). "
                f"POST /api/v1/engagements/{engagement_id}/repair-manifest to rebuild."
            ),
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Engagement manifest could not be loaded: {exc}",
        ) from exc
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
        "detected_company_name": "",
        "detected_industry": "",
        "detected_industry_label": "",
        "detected_annual_revenue_cr": None,
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
    """Persist auto-detected company/industry on the engagement manifest."""
    manifest = read_engagement_manifest(engagement_id)
    if not manifest.get("engagement_id"):
        return {}

    detected_company = str(detection.get("detected_company_name") or "").strip()
    from app.services.engagement_sanity import is_placeholder_industry
    from app.services.sector_packs import resolve_sector_pack_id

    prior_detected_industry = str(manifest.get("detected_industry") or "").strip()
    detected_industry = resolve_sector_pack_id(
        str(detection.get("detected_industry") or "").strip()
    )
    detected_revenue_raw = detection.get("detected_annual_revenue_cr")
    detected_revenue_cr: Optional[float] = None
    if detected_revenue_raw is not None:
        try:
            detected_revenue_cr = float(detected_revenue_raw)
            if detected_revenue_cr <= 0:
                detected_revenue_cr = None
        except (TypeError, ValueError):
            detected_revenue_cr = None

    manifest["detected_company_name"] = detected_company
    manifest["detected_industry"] = detected_industry
    manifest["detected_industry_label"] = str(detection.get("detected_industry_label") or "")
    manifest["detected_annual_revenue_cr"] = detected_revenue_cr
    manifest["detection_signals"] = {
        "industry_source": str(detection.get("industry_source") or ""),
        "industry_llm": str(detection.get("industry_llm") or ""),
        "industry_spend": str(detection.get("industry_spend") or ""),
        "company_llm": str(detection.get("company_llm") or ""),
        "revenue_llm": detection.get("revenue_llm"),
        "source_documents": detection.get("source_documents") or {},
    }
    manifest["context_text_hash"] = str(detection.get("context_text_hash") or "")

    current_company = str(manifest.get("company_name") or "").strip()
    if detected_company and current_company in ("", "New engagement") and should_auto_apply_company(detected_company):
        manifest["company_name"] = detected_company
    current_industry = str(manifest.get("industry") or "").strip()
    if (
        detected_industry
        and is_placeholder_industry(current_industry)
        and not prior_detected_industry
    ):
        manifest["industry"] = detected_industry
    current_revenue = float(manifest.get("annual_revenue") or 0.0)
    if detected_revenue_cr is not None and current_revenue <= 0:
        manifest["annual_revenue"] = detected_revenue_cr * 10_000_000

    manifest["updated_at"] = _utc_now()
    write_engagement_manifest(engagement_id, manifest)
    return manifest


def register_session_on_engagement(engagement_id: str, session_id: str) -> None:
    with manifest_lock.acquire(engagement_id):
        manifest, _, parse_error = _parse_manifest_file(engagement_id)
        if parse_error or not manifest.get("engagement_id"):
            raise HTTPException(status_code=404, detail="Engagement not found")
        sessions = list(manifest.get("session_ids") or [])
        if session_id not in sessions:
            sessions.append(session_id)
            manifest["session_ids"] = sessions
            manifest["updated_at"] = _utc_now()
            _write_manifest_payload(engagement_id, manifest)


def _corrupt_engagement_summary(engagement_id: str, reason: str) -> Dict[str, Any]:
    return {
        "engagement_id": engagement_id,
        "company_name": "Unavailable",
        "industry": "",
        "currency": "INR",
        "annual_revenue": None,
        "created_at": None,
        "updated_at": None,
        "session_count": 0,
        "document_count": 0,
        "documents_ready": 0,
        "detected_company_name": "",
        "detected_industry": "",
        "detected_industry_label": "",
        "detected_annual_revenue_cr": None,
        "manifest_status": "corrupt",
        "manifest_error": reason[:200],
    }


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
        try:
            manifest = read_engagement_manifest(path.name, auto_repair=False)
            if not manifest.get("engagement_id"):
                summaries.append(_corrupt_engagement_summary(path.name, "missing engagement_id"))
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
                "detected_annual_revenue_cr": manifest.get("detected_annual_revenue_cr"),
                "manifest_status": "ok",
            })
        except ManifestReadError as exc:
            logger.warning("manifest_list_read_error engagement_id=%s reason=%s", path.name, exc.reason)
            summaries.append(_corrupt_engagement_summary(path.name, exc.reason))
        except HTTPException as exc:
            logger.warning("manifest_list_http_error engagement_id=%s detail=%s", path.name, exc.detail)
            summaries.append(_corrupt_engagement_summary(path.name, str(exc.detail)))
        except Exception as exc:
            logger.exception("manifest_list_read_failed engagement_id=%s", path.name)
            summaries.append(_corrupt_engagement_summary(path.name, str(exc)))
    summaries.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
    return summaries


def add_document_record(
    engagement_id: str,
    *,
    document_id: str,
    filename: str,
    content_type: str,
    size_bytes: int,
    raw_path: str,
    _already_locked: bool = False,
) -> Dict[str, Any]:
    def _apply() -> Dict[str, Any]:
        manifest, _, parse_error = _parse_manifest_file(engagement_id)
        if parse_error or not manifest.get("engagement_id"):
            raise HTTPException(status_code=404, detail="Engagement not found")
        _repair_manifest_documents(engagement_id, manifest, exclude_ids={document_id})
        write_document_meta(
            engagement_id,
            document_id,
            filename=filename,
            content_type=content_type,
        )
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
        _write_manifest_payload(engagement_id, manifest)
        return record

    try:
        if _already_locked:
            return _apply()
        with manifest_lock.acquire(engagement_id):
            return _apply()
    except ManifestLockError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ManifestValidationError as exc:
        raise HTTPException(status_code=500, detail=f"Invalid engagement manifest: {exc}") from exc


def update_document_record(engagement_id: str, document_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
    try:
        with manifest_lock.acquire(engagement_id):
            manifest, _, parse_error = _parse_manifest_file(engagement_id)
            if parse_error or not manifest.get("engagement_id"):
                raise HTTPException(status_code=404, detail="Engagement not found")
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
            _write_manifest_payload(engagement_id, manifest)
            return updated
    except ManifestLockError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ManifestValidationError as exc:
        raise HTTPException(status_code=500, detail=f"Invalid engagement manifest: {exc}") from exc


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
    with manifest_lock.acquire(engagement_id):
        manifest, _, parse_error = _parse_manifest_file(engagement_id)
        if parse_error or not manifest.get("engagement_id"):
            return
        manifest["documents"] = [
            d for d in (manifest.get("documents") or []) if d.get("document_id") != document_id
        ]
        manifest["updated_at"] = _utc_now()
        _write_manifest_payload(engagement_id, manifest)


def delete_engagement(engagement_id: str) -> None:
    """Remove the engagement's manifest, documents, and on-disk directory."""
    edir = engagement_dir(engagement_id)
    if edir.exists():
        shutil.rmtree(edir, ignore_errors=True)


def document_meta_path(engagement_id: str, document_id: str) -> Path:
    return document_dir(engagement_id, document_id) / "meta.json"


def document_parsed_dir(engagement_id: str, document_id: str) -> Path:
    path = document_dir(engagement_id, document_id) / "parsed"
    path.mkdir(parents=True, exist_ok=True)
    return path


def parent_nodes_path(engagement_id: str, document_id: str) -> Path:
    return document_parsed_dir(engagement_id, document_id) / "parent_nodes.json"


def write_parent_nodes(engagement_id: str, document_id: str, parents: List[Any]) -> None:
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
