"""Ingest spend via source-system connectors into a session corpus."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from app.config import logger
from app.models import NormalizedSpendLine
from app.routers._shared import read_manifest, session_dir, validate_session_id, write_manifest
from app.services.analysis import run_core_pipeline
from app.services.connector_registry import build_connector


def _write_connector_spend_file(session_id: str, connector_type: str, lines: List[NormalizedSpendLine]) -> Path:
    out_path = session_dir(session_id) / f"connector_{connector_type}_spend.json"
    payload = [line.model_dump() for line in lines]
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def ingest_via_connector(
    session_id: str,
    connector_type: str,
    *,
    source_file: str,
    source_system_id: str | None = None,
    credentials: Dict[str, str] | None = None,
    fetch_kwargs: Dict[str, Any] | None = None,
    run_analysis: bool = False,
) -> Dict[str, Any]:
    """Run a connector against a session-local file and register normalized spend."""
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

    connector = build_connector(
        connector_type,
        source_system_id=source_system_id,
        credentials=credentials,
    )
    if not connector.authenticate():
        raise RuntimeError(f"Connector authentication failed: {connector_type}")

    fetch_args = {"file_path": str(source_path)}
    if fetch_kwargs:
        fetch_args.update(fetch_kwargs)
    result = connector.fetch(**fetch_args)
    if not result.success:
        raise ValueError("; ".join(result.errors) or "Connector fetch returned no spend lines")

    out_path = _write_connector_spend_file(session_id, connector_type, result.lines)
    manifest = read_manifest(session_id)
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
    manifest.setdefault("connector_ingests", []).append(
        {
            "connector_type": connector_type,
            "source_file": source_path.name,
            "normalized_file": out_path.name,
            "row_count": len(result.lines),
            "source_system_id": result.source_system_id or connector.source_system_id,
            "ingested_at": datetime.now(timezone.utc).isoformat(),
            "errors": result.errors[:5],
        }
    )
    write_manifest(session_id, manifest)
    logger.info(
        '"connector_ingest session_id=%s type=%s rows=%d"',
        session_id,
        connector_type,
        len(result.lines),
    )

    response: Dict[str, Any] = {
        "session_id": session_id,
        "connector_type": connector_type,
        "row_count": len(result.lines),
        "normalized_file": out_path.name,
        "source_system_id": result.source_system_id or connector.source_system_id,
        "warnings": result.errors[:5],
    }
    if run_analysis:
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
            engagement_id=manifest.get("engagement_id"),
        )
        response["analysis"] = analysis
    return response
