"""Engagement document ingestion: classify, parse, cache artifacts."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.config import logger
from app.models import NormalizedSpendLine
from app.services.engagements_store import (
    SUPPORTED_EXTENSIONS,
    document_dir,
    document_parsed_dir,
    update_document_record,
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

        elif suffix == ".txt":
            text = raw_path.read_text(encoding="utf-8", errors="ignore")
            (parsed_dir / "markdown.md").write_text(text, encoding="utf-8")
            role = "context_doc"
            parse_backend = "native"
            text_preview = text[:500]

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
            # Attempt tabular extraction from markdown tables (simple heuristic: skip for now)

        else:
            raise ValueError(f"Unsupported file type: {suffix}")

        meta_patch = {
            "status": "ready",
            "role": role,
            "parse_backend": parse_backend,
            "error": None,
            "processed_at": _utc_now(),
            "text_preview": text_preview,
            "line_count": line_count,
            "warnings": warnings,
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
