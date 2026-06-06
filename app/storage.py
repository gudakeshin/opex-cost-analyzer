from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import DATA_DIR, ENGAGEMENTS_DIR, MEMORY_DIR, OUTPUT_DIR, UPLOAD_DIR


def ensure_dirs() -> None:
    for path in (DATA_DIR, MEMORY_DIR, OUTPUT_DIR, UPLOAD_DIR, ENGAGEMENTS_DIR):
        path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default if default is not None else {}
    return json.loads(path.read_text(encoding="utf-8"))

