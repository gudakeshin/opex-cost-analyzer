"""Test helpers for session-local file seeding (replaces deprecated upload API in tests)."""
from __future__ import annotations

from pathlib import Path
from typing import Any


def seed_session_upload(
    session_id: str,
    filename: str,
    content: bytes,
    content_type: str = "application/octet-stream",
) -> None:
    from app.routers._shared import read_manifest, session_dir, write_manifest
    from app.services.ingestion import infer_tabular_schema

    sdir = session_dir(session_id)
    sdir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(filename).name
    out_path = sdir / safe_name
    out_path.write_bytes(content)
    entry: dict[str, Any] = {
        "name": safe_name,
        "content_type": content_type,
        "size_bytes": len(content),
        "path": str(out_path),
    }
    suffix = out_path.suffix.lower()
    if suffix in (".csv", ".xlsx", ".xls"):
        entry["schema"] = infer_tabular_schema(out_path)
    elif suffix == ".json":
        entry["schema"] = {"format": "json"}
    manifest = read_manifest(session_id)
    manifest.setdefault("files", []).append(entry)
    write_manifest(session_id, manifest)
