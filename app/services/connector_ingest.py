"""Ingest spend via source-system connectors into a session corpus."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import logger
from app.memory import MemoryStore
from app.models import NormalizedSpendLine
from app.routers._shared import read_manifest, session_dir, validate_session_id, write_manifest
from app.services.analysis import run_core_pipeline, run_incremental_pipeline
from app.services.connector_registry import build_connector
from app.services.connector_sync import get_watermark, set_watermark
from app.services.jobs import update_job_progress

_memory = MemoryStore()


def _write_connector_spend_file(session_id: str, connector_type: str, lines: List[NormalizedSpendLine]) -> Path:
    out_path = session_dir(session_id) / f"connector_{connector_type}_spend.json"
    payload = [line.model_dump() for line in lines]
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def _tag_lines_with_file_hash(lines: List[NormalizedSpendLine], source_path: Path) -> None:
    digest = hashlib.sha256(source_path.read_bytes()).hexdigest()[:16]
    for line in lines:
        if not line.source_file_hash:
            line.source_file_hash = digest


def _write_engagement_store(engagement_id: str, connector_type: str, lines: List[NormalizedSpendLine]) -> bool:
    try:
        from app.services.spend_store import write_document_spend_lines

        doc_id = f"connector_{connector_type}"
        return write_document_spend_lines(engagement_id, doc_id, lines)
    except Exception:
        logger.warning(
            '"connector_spend_store_write_failed engagement_id=%s type=%s"',
            engagement_id,
            connector_type,
            exc_info=True,
        )
        return False


def ingest_via_connector(
    session_id: str,
    connector_type: str,
    *,
    source_file: str,
    source_system_id: str | None = None,
    credentials: Dict[str, str] | None = None,
    fetch_kwargs: Dict[str, Any] | None = None,
    run_analysis: bool = False,
    delta_sync: bool = False,
    job_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Run a connector and register normalized spend (optionally incremental)."""
    validate_session_id(session_id)
    try:
        build_connector(connector_type)
    except KeyError as exc:
        raise KeyError(str(exc)) from exc

    sdir = session_dir(session_id)
    if not sdir.exists():
        raise FileNotFoundError(f"Session not found: {session_id}")

    source_path = (sdir / Path(source_file).name).resolve()
    if not str(source_path).startswith(str(sdir.resolve())):
        raise ValueError("source_file must resolve inside the session directory")
    if not source_path.exists():
        raise FileNotFoundError(f"Source file not found in session: {source_file}")

    manifest = read_manifest(session_id)
    engagement_id = str(manifest.get("engagement_id") or session_id)

    fetch_args: Dict[str, Any] = {"file_path": str(source_path)}
    if fetch_kwargs:
        fetch_args.update(fetch_kwargs)

    watermark_before = None
    if delta_sync:
        watermark_before = get_watermark(engagement_id, connector_type)
        since = (watermark_before or {}).get("last_sync_at")
        if since and "since" not in fetch_args:
            fetch_args["since"] = since

    if job_id:
        update_job_progress(job_id, 15, message=f"Fetching from {connector_type}")

    connector = build_connector(
        connector_type,
        source_system_id=source_system_id,
        credentials=credentials,
    )
    if not connector.authenticate():
        raise RuntimeError(f"Connector authentication failed: {connector_type}")

    result = connector.fetch(**fetch_args)
    if not result.success:
        raise ValueError("; ".join(result.errors) or "Connector fetch returned no spend lines")

    _tag_lines_with_file_hash(result.lines, source_path)

    if job_id:
        update_job_progress(job_id, 50, message=f"Merging {len(result.lines)} lines")

    _write_engagement_store(engagement_id, connector_type, result.lines)
    out_path = _write_connector_spend_file(session_id, connector_type, result.lines)

    files = list(manifest.get("files") or [])
    files = [f for f in files if f.get("name") != out_path.name]
    files.append(
        {
            "name": out_path.name,
            "content_type": "application/json",
            "size_bytes": out_path.stat().st_size,
            "path": str(out_path),
            "origin": "connector",
            "connector_type": connector_type,
            "source_file": source_path.name,
        }
    )
    manifest["files"] = files
    ingest_record = {
        "connector_type": connector_type,
        "source_file": source_path.name,
        "normalized_file": out_path.name,
        "row_count": len(result.lines),
        "source_system_id": result.source_system_id or connector.source_system_id,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "errors": result.errors[:5],
        "delta_sync": delta_sync,
        "since": fetch_args.get("since"),
    }
    manifest.setdefault("connector_ingests", []).append(ingest_record)
    write_manifest(session_id, manifest)

    sync_at = datetime.now(timezone.utc).isoformat()
    watermark_after = set_watermark(
        engagement_id,
        connector_type,
        last_sync_at=sync_at,
        cursor={"row_count": len(result.lines), "source_file": source_path.name},
    )

    logger.info(
        '"connector_ingest session_id=%s type=%s rows=%d delta=%s"',
        session_id,
        connector_type,
        len(result.lines),
        delta_sync,
    )

    response: Dict[str, Any] = {
        "session_id": session_id,
        "engagement_id": engagement_id,
        "connector_type": connector_type,
        "row_count": len(result.lines),
        "normalized_file": out_path.name,
        "source_system_id": result.source_system_id or connector.source_system_id,
        "warnings": result.errors[:5],
        "delta_sync": delta_sync,
        "watermark": watermark_after,
    }

    existing = _memory.get("session", session_id)
    if existing and existing.get("normalized_spend"):
        if job_id:
            update_job_progress(job_id, 70, message="Running incremental merge")
        inc = run_incremental_pipeline(session_id=session_id, new_lines=result.lines)
        response["incremental"] = inc
    elif run_analysis:
        if job_id:
            update_job_progress(job_id, 70, message="Running analysis pipeline")
        industry = str(manifest.get("industry") or "")
        annual_revenue = float(manifest.get("annual_revenue") or 0.0)
        reporting_currency = str(manifest.get("currency") or "INR")
        analysis = run_core_pipeline(
            session_id=session_id,
            lines=result.lines,
            docs_text=[],
            industry=industry,
            annual_revenue=annual_revenue,
            company_name=manifest.get("company_name"),
            reporting_currency=reporting_currency,
            engagement_id=engagement_id,
        )
        response["analysis"] = analysis

    if watermark_before:
        response["previous_sync_at"] = watermark_before.get("last_sync_at")
    return response
