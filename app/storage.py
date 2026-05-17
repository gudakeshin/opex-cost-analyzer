from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from app.config import DATA_DIR, MEMORY_DIR, OUTPUT_DIR, UPLOAD_DIR


def ensure_dirs() -> None:
    for path in (DATA_DIR, MEMORY_DIR, OUTPUT_DIR, UPLOAD_DIR):
        path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def read_json(path: Path, default: Dict[str, Any] | None = None) -> Dict[str, Any]:
    if not path.exists():
        return default or {}
    return json.loads(path.read_text(encoding="utf-8"))

