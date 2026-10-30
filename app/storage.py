from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from app.config import DATA_DIR, ENGAGEMENTS_DIR, MEMORY_DIR, OUTPUT_DIR, UPLOAD_DIR, logger


def ensure_dirs() -> None:
    for path in (DATA_DIR, MEMORY_DIR, OUTPUT_DIR, UPLOAD_DIR, ENGAGEMENTS_DIR):
        path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: Any) -> None:
    """Atomically write JSON so concurrent readers never see partial files."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2)
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default if default is not None else {}
    text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        # Salvage the first complete JSON value when a concurrent write appended garbage.
        if "Extra data" not in str(exc):
            raise
        payload, end = json.JSONDecoder().raw_decode(text)
        trailing = len(text) - end
        if trailing > 0:
            logger.warning(
                "json_extra_data path=%s trailing_bytes=%s",
                path,
                trailing,
            )
        return payload

