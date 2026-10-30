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


# Above this, the per-document JSON cache is skipped: the Parquet store is the
# only cache, and load_cached_spend_lines reads it back. Below it, both are
# written so environments without duckdb/pyarrow keep working unchanged.
_JSON_CACHE_MAX_LINES = 100_000


def _should_stream_csv(raw_path: Path) -> bool:
    """Stream CSVs too big for the in-memory parser, when the store can take them."""
    from app.services.ingestion import _ROW_MAX, estimate_csv_rows
    from app.services.spend_store import is_available

    if not is_available():
        return False
    try:
        return estimate_csv_rows(raw_path) > _ROW_MAX
    except OSError:
        return False


def _stream_csv_document(
    engagement_id: str,
    document_id: str,
    raw_path: Path,
    *,
    taxonomy: Dict[str, Any],
    reporting_currency: str,
) -> tuple[int, Dict[str, Any]]:
    """Chunk a large CSV straight into the Parquet spend store.

    Peak memory is one chunk (100k lines); no spend_lines.json is written —
    load_cached_spend_lines reads the Parquet store instead.
    """
    from app.services.ingestion import iter_spend_csv_chunks
    from app.services.spend_store import SpendStore

    total = SpendStore(engagement_id).write_document_batches(
        document_id,
        iter_spend_csv_chunks(
            raw_path, taxonomy, reporting_currency=reporting_currency
        ),
    )
    report = {
        "source_file": raw_path.name,
        "sheets_ingested": [
            {"sheet": raw_path.stem, "rows": total, "strategy": "csv_streamed"}
        ],
        "sheets_skipped": [],
        "rows_ingested": total,
        "streamed": True,
    }
    return total, report


def _cache_spend_lines(
    engagement_id: str,
    document_id: str,
    parsed_dir: Path,
    lines: List[NormalizedSpendLine],
) -> None:
    from app.services.spend_store import write_document_spend_lines

    parquet_ok = write_document_spend_lines(engagement_id, document_id, lines)
    try:
        from app.services.cache import CostRoomCache

        CostRoomCache().invalidate(engagement_id)
    except Exception:
        pass
    if len(lines) <= _JSON_CACHE_MAX_LINES or not parquet_ok:
        (parsed_dir / "spend_lines.json").write_text(
            json.dumps(_serialize_lines(lines), indent=2),
            encoding="utf-8",
        )
    else:
        (parsed_dir / "spend_lines.json").unlink(missing_ok=True)


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
    from app.services.gl_mapping import apply_to_taxonomy

    taxonomy = apply_to_taxonomy(taxonomy, engagement_id)  # adds this engagement's GL ranges, if any
    try:
        column_overrides = dict(get_document_record(engagement_id, document_id).get("column_overrides") or {})
    except Exception:
        column_overrides = {}
    warnings: List[str] = []
    role = "context_doc"
    parse_backend = "native"
    text_preview = ""
    line_count = 0
    parsed_markdown = ""

    try:
        if suffix == ".csv" and _should_stream_csv(raw_path):
            line_count, report = _stream_csv_document(
                engagement_id, document_id, raw_path,
                taxonomy=taxonomy, reporting_currency=reporting_currency,
            )
            role = "spend_tabular"
            parse_backend = "native_streamed"
            (parsed_dir / "ingestion_report.json").write_text(
                json.dumps(report, indent=2),
                encoding="utf-8",
            )
            text_preview = f"Parsed {line_count} spend lines from {raw_path.name} (streamed)"

        elif suffix in (".csv", ".xlsx", ".xls"):
            lines, report = parse_spend_file_with_report(
                raw_path, taxonomy, reporting_currency=reporting_currency,
                column_overrides=column_overrides or None,
            )
            role = "spend_tabular"
            parse_backend = "native"
            line_count = len(lines)
            _cache_spend_lines(engagement_id, document_id, parsed_dir, lines)
            (parsed_dir / "ingestion_report.json").write_text(
                json.dumps(report, indent=2),
                encoding="utf-8",
            )
            text_preview = f"Parsed {line_count} spend lines from {raw_path.name}"

        elif suffix == ".json":
            lines, report = parse_spend_json_with_report(
                raw_path, taxonomy, reporting_currency=reporting_currency,
                column_overrides=column_overrides or None,
            )
            role = "spend_tabular"
            parse_backend = "native"
            line_count = len(lines)
            _cache_spend_lines(engagement_id, document_id, parsed_dir, lines)
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
        # Large documents are cached in Parquet only (see _cache_spend_lines).
        from app.services.spend_store import SpendStore, is_available

        if is_available():
            try:
                return SpendStore(engagement_id).document_lines(document_id)
            except Exception:
                logger.warning(
                    '"spend_store_read_failed engagement_id=%s document_id=%s"',
                    engagement_id, document_id, exc_info=True,
                )
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        return []
    return _deserialize_lines(data)


def load_cached_ingestion_report(engagement_id: str, document_id: str) -> Dict[str, Any]:
    """The ingest report written when the document was parsed ({} when absent or unreadable)."""
    path = document_parsed_dir(engagement_id, document_id) / "ingestion_report.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


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
