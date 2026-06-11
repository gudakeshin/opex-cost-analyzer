"""Engagement document ingestion: classify, parse, cache artifacts."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from app.config import logger
from app.models import NormalizedSpendLine
from app.services.engagements_store import (
    SUPPORTED_EXTENSIONS,
    add_document_record,
    document_dir,
    document_parsed_dir,
    get_document_record,
    read_engagement_manifest,
    update_document_record,
    write_parent_nodes,
)
from app.services.ingestion import (
    parse_document,
    parse_spend_file_with_report,
    parse_spend_json_with_report,
)
from app.services.llamaparse_client import is_llamaparse_available, parse_file_to_markdown


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _serialize_lines(lines: List[NormalizedSpendLine]) -> List[Dict[str, Any]]:
    return [ln.model_dump(mode="json") for ln in lines]


def _deserialize_lines(payload: List[Dict[str, Any]]) -> List[NormalizedSpendLine]:
    return [NormalizedSpendLine.model_validate(item) for item in payload]


def index_document_nodes(
    engagement_id: str,
    document_id: str,
    markdown: str,
    filename: str,
) -> Dict[str, int]:
    """Hierarchically chunk markdown, store parents, embed children. Returns counts."""
    from app.services.chunking import split_markdown_hierarchical
    from app.services.document_index import get_document_index

    parents, children = split_markdown_hierarchical(
        markdown, doc_id=document_id, engagement_id=engagement_id, filename=filename
    )
    write_parent_nodes(engagement_id, document_id, parents)
    get_document_index().index_document(engagement_id, document_id, children)
    return {"parent_count": len(parents), "chunk_count": len(children)}


def reindex_engagement(engagement_id: str) -> Dict[str, Any]:
    """Backfill: re-chunk + re-index every ready context document from cached markdown."""
    manifest = read_engagement_manifest(engagement_id)
    summary: Dict[str, Any] = {"engagement_id": engagement_id, "documents": 0, "chunks": 0, "parents": 0}
    for doc in manifest.get("documents") or []:
        doc_id = doc.get("document_id")
        if not doc_id or doc.get("status") != "ready":
            continue
        markdown = load_cached_markdown(engagement_id, doc_id)
        if not markdown.strip():
            continue
        stats = index_document_nodes(
            engagement_id, doc_id, markdown, doc.get("filename") or doc_id
        )
        summary["documents"] += 1
        summary["chunks"] += stats["chunk_count"]
        summary["parents"] += stats["parent_count"]
    return summary


def ingest_markdown_document(
    engagement_id: str,
    markdown: str,
    filename: str,
    *,
    reporting_currency: str = "INR",
    content_type: str = "text/markdown",
) -> str:
    """Write an in-memory markdown doc into the engagement folder and run the
    standard parse + index pipeline synchronously. Returns the new document_id.

    Mirrors the upload flow in ``app/routers/engagements.py`` so the document is
    indistinguishable from a user-uploaded one and is picked up by analysis via
    ``load_engagement_corpus``.
    """
    from app.services.analysis import load_taxonomy

    document_id = str(uuid.uuid4())
    ddir = document_dir(engagement_id, document_id)
    raw_path = ddir / "raw.md"
    payload = markdown.encode("utf-8")

    # Register manifest + meta before raw bytes land on disk (see engagements upload).
    add_document_record(
        engagement_id,
        document_id=document_id,
        filename=filename,
        content_type=content_type,
        size_bytes=len(payload),
        raw_path=str(raw_path),
    )
    raw_path.write_bytes(payload)

    process_engagement_document(
        engagement_id,
        document_id,
        taxonomy=load_taxonomy(),
        reporting_currency=reporting_currency,
    )
    return document_id


def process_engagement_document(
    engagement_id: str,
    document_id: str,
    *,
    taxonomy: Dict[str, Any],
    reporting_currency: str = "INR",
) -> Dict[str, Any]:
    """Run full parse pipeline for one engagement document (sync)."""
    ddir = document_dir(engagement_id, document_id)
    raw_files = list(ddir.glob("raw.*"))
    if not raw_files:
        update_document_record(
            engagement_id,
            document_id,
            {"status": "failed", "error": "Raw file missing", "processed_at": _utc_now()},
        )
        return {"status": "failed", "error": "Raw file missing"}

    raw_path = raw_files[0]
    suffix = raw_path.suffix.lower()
    update_document_record(
        engagement_id,
        document_id,
        {"status": "processing", "error": None},
    )

    parsed_dir = document_parsed_dir(engagement_id, document_id)
    warnings: List[str] = []
    role = "context_doc"
    parse_backend = "native"
    text_preview = ""
    line_count = 0
    parsed_markdown = ""

    try:
        if suffix in (".csv", ".xlsx", ".xls"):
            lines, report = parse_spend_file_with_report(
                raw_path, taxonomy, reporting_currency=reporting_currency
            )
            role = "spend_tabular"
            parse_backend = "native"
            line_count = len(lines)
            (parsed_dir / "spend_lines.json").write_text(
                json.dumps(_serialize_lines(lines), indent=2),
                encoding="utf-8",
            )
            (parsed_dir / "ingestion_report.json").write_text(
                json.dumps(report, indent=2),
                encoding="utf-8",
            )
            text_preview = f"Parsed {line_count} spend lines from {raw_path.name}"

        elif suffix == ".json":
            lines, report = parse_spend_json_with_report(
                raw_path, taxonomy, reporting_currency=reporting_currency
            )
            role = "spend_tabular"
            parse_backend = "native"
            line_count = len(lines)
            (parsed_dir / "spend_lines.json").write_text(
                json.dumps(_serialize_lines(lines), indent=2),
                encoding="utf-8",
            )
            (parsed_dir / "ingestion_report.json").write_text(
                json.dumps(report, indent=2),
                encoding="utf-8",
            )
            text_preview = f"Parsed {line_count} spend lines from JSON"

        elif suffix in (".txt", ".md"):
            text = raw_path.read_text(encoding="utf-8", errors="ignore")
            (parsed_dir / "markdown.md").write_text(text, encoding="utf-8")
            role = "context_doc"
            parse_backend = "native"
            text_preview = text[:500]
            parsed_markdown = text

        elif suffix == ".docx":
            markdown = ""
            backend = "legacy"
            if is_llamaparse_available():
                result = parse_file_to_markdown(raw_path)
                if result.get("ok"):
                    markdown = str(result.get("markdown") or "")
                    backend = "llamaparse"
                else:
                    warnings.append(str(result.get("error") or "LlamaParse failed"))
            if not markdown.strip():
                markdown = parse_document(raw_path)
                backend = "legacy" if backend == "legacy" else "llamaparse+legacy"
            (parsed_dir / "markdown.md").write_text(markdown, encoding="utf-8")
            role = "context_doc"
            parse_backend = backend
            text_preview = markdown[:500]
            parsed_markdown = markdown

        elif suffix == ".pdf":
            markdown = ""
            backend = "legacy"
            if is_llamaparse_available():
                result = parse_file_to_markdown(raw_path)
                if result.get("ok"):
                    markdown = str(result.get("markdown") or "")
                    backend = "llamaparse"
                else:
                    warnings.append(str(result.get("error") or "LlamaParse failed"))
            if not markdown.strip():
                markdown = parse_document(raw_path)
                backend = "legacy" if not is_llamaparse_available() else "llamaparse+legacy"
            (parsed_dir / "markdown.md").write_text(markdown, encoding="utf-8")
            role = "mixed"
            parse_backend = backend
            text_preview = markdown[:500]
            parsed_markdown = markdown
            # Attempt tabular extraction from markdown tables (simple heuristic: skip for now)

        else:
            raise ValueError(f"Unsupported file type: {suffix}")

        index_stats: Dict[str, Any] = {
            "chunk_count": 0,
            "parent_count": 0,
            "indexed": False,
            "index_backend": None,
        }
        if parsed_markdown.strip():
            try:
                from app.services.document_index import get_document_index_status

                friendly_name = get_document_record(engagement_id, document_id).get("filename") or raw_path.name
                counts = index_document_nodes(
                    engagement_id, document_id, parsed_markdown, friendly_name
                )
                index_stats = {
                    **counts,
                    "indexed": True,
                    "index_backend": get_document_index_status().get("backend"),
                }
            except Exception as exc:
                warnings.append(f"Document indexing failed: {exc}")

        meta_patch = {
            "status": "ready",
            "role": role,
            "parse_backend": parse_backend,
            "error": None,
            "processed_at": _utc_now(),
            "text_preview": text_preview,
            "line_count": line_count,
            "warnings": warnings,
            **index_stats,
        }
        update_document_record(engagement_id, document_id, meta_patch)
        append_meta = {**meta_patch, "document_id": document_id}
        logger.info(
            '"document_parsed engagement_id=%s document_id=%s role=%s lines=%d"',
            engagement_id,
            document_id,
            role,
            line_count,
        )
        return append_meta

    except Exception as exc:
        logger.warning(
            "document_parse_failed engagement_id=%s document_id=%s error=%s",
            engagement_id,
            document_id,
            exc,
        )
        update_document_record(
            engagement_id,
            document_id,
            {
                "status": "failed",
                "error": str(exc)[:500],
                "processed_at": _utc_now(),
            },
        )
        return {"status": "failed", "error": str(exc)[:500]}


def load_cached_spend_lines(engagement_id: str, document_id: str) -> List[NormalizedSpendLine]:
    path = document_parsed_dir(engagement_id, document_id) / "spend_lines.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        return []
    return _deserialize_lines(data)


def load_cached_markdown(engagement_id: str, document_id: str) -> str:
    parsed = document_parsed_dir(engagement_id, document_id)
    for name in ("markdown.md", "text.md"):
        path = parsed / name
        if path.exists():
            return path.read_text(encoding="utf-8", errors="ignore")
    return ""


def validate_upload_suffix(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type '{suffix}'. Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )
    return suffix
