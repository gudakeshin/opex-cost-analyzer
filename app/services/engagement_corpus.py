"""Load merged spend lines and document text for an engagement + session."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

from app.models import NormalizedSpendLine
from app.routers._shared import read_manifest, session_dir
from app.services.analysis import load_taxonomy
from app.services.engagements_store import (
    backfill_engagement_for_session,
    read_engagement_manifest,
)
from app.services.document_pipeline import load_cached_markdown, load_cached_spend_lines
from app.services.ingestion import parse_document, parse_spend_file, parse_spend_json


def _load_session_files(
    session_id: str,
    manifest: Dict[str, Any],
) -> Tuple[List[NormalizedSpendLine], List[str], List[Dict[str, Any]], List[str]]:
    taxonomy = load_taxonomy()
    lines: List[NormalizedSpendLine] = []
    docs_text: List[str] = []
    ingestion_reports: List[Dict[str, Any]] = []
    warnings: List[str] = []
    model_manifest = manifest.get("model_manifest") if isinstance(manifest, dict) else None

    for item in manifest.get("files", []):
        path = Path(item.get("path", ""))
        if not path.exists():
            warnings.append(f"Session file missing: {item.get('name', path.name)}")
            continue
        suffix = path.suffix.lower()
        try:
            if suffix in (".xlsx", ".xls", ".csv"):
                lines.extend(
                    parse_spend_file(path, taxonomy, workbook_manifest=model_manifest)
                )
            elif suffix == ".json":
                lines.extend(parse_spend_json(path, taxonomy))
            elif suffix in (".pdf", ".docx", ".txt"):
                text = parse_document(path)
                if text.strip():
                    docs_text.append(f"## {path.name}\n{text.strip()}")
        except Exception as exc:
            warnings.append(f"Failed to parse session file {path.name}: {exc}")

    return lines, docs_text, ingestion_reports, warnings


def load_engagement_corpus(
    engagement_id: str,
    *,
    reporting_currency: str | None = None,
) -> Tuple[List[NormalizedSpendLine], List[str], List[Dict[str, Any]], List[str]]:
    """Load ready engagement documents into spend lines and context text."""
    manifest = read_engagement_manifest(engagement_id)
    if not manifest.get("engagement_id"):
        return [], [], [], [f"Engagement {engagement_id} not found"]

    currency = reporting_currency or manifest.get("currency") or "INR"
    taxonomy = load_taxonomy()
    lines: List[NormalizedSpendLine] = []
    docs_text: List[str] = []
    reports: List[Dict[str, Any]] = []
    warnings: List[str] = []

    for doc in manifest.get("documents") or []:
        status = doc.get("status")
        doc_id = doc.get("document_id")
        filename = doc.get("filename") or "document"
        if not doc_id:
            continue
        if status == "processing":
            warnings.append(f"Document still processing: {filename}")
            continue
        if status == "failed":
            warnings.append(
                f"Document failed: {filename} — {doc.get('error') or 'unknown error'}"
            )
            continue
        if status != "ready":
            warnings.append(f"Document not ready: {filename} ({status})")
            continue

        cached_lines = load_cached_spend_lines(engagement_id, doc_id)
        if cached_lines:
            lines.extend(cached_lines)
            reports.append({
                "source_file": filename,
                "document_id": doc_id,
                "rows_parsed": len(cached_lines),
                "origin": "engagement",
            })
        markdown = load_cached_markdown(engagement_id, doc_id)
        if markdown.strip():
            docs_text.append(f"## {filename}\n{markdown.strip()}")

    return lines, docs_text, reports, warnings


def load_analysis_corpus(
    session_id: str,
) -> Tuple[List[NormalizedSpendLine], List[str], List[Dict[str, Any]], List[str], Dict[str, Any]]:
    """Merge engagement-level corpus with session-local uploads."""
    manifest = read_manifest(session_id)
    engagement_id = backfill_engagement_for_session(session_id, manifest)
    if manifest.get("engagement_id") != engagement_id:
        manifest["engagement_id"] = engagement_id
        from app.routers._shared import write_manifest
        write_manifest(session_id, manifest)

    eng_lines, eng_docs, eng_reports, eng_warnings = load_engagement_corpus(
        engagement_id,
        reporting_currency=manifest.get("currency"),
    )
    sess_lines, sess_docs, sess_reports, sess_warnings = _load_session_files(session_id, manifest)

    lines = eng_lines + sess_lines
    docs_text = eng_docs + sess_docs
    reports = eng_reports + sess_reports
    warnings = eng_warnings + sess_warnings
    return lines, docs_text, reports, warnings, manifest
