"""LlamaParse cloud client with graceful fallback when unavailable."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from app.config import (
    LLAMA_CLOUD_API_KEY,
    LLAMAPARSE_ENABLED,
    LLAMAPARSE_PREMIUM_MODE,
    LLAMAPARSE_RESULT_TYPE,
    logger,
)


def is_llamaparse_available() -> bool:
    return LLAMAPARSE_ENABLED and bool(LLAMA_CLOUD_API_KEY)


def parse_file_to_markdown(file_path: Path) -> Dict[str, Any]:
    """Parse a document via LlamaParse; returns markdown text and metadata."""
    if not is_llamaparse_available():
        return {
            "ok": False,
            "error": "LlamaParse is not configured (set LLAMA_CLOUD_API_KEY)",
            "markdown": "",
        }
    try:
        from llama_parse import LlamaParse  # type: ignore[import-untyped]
    except ImportError as exc:
        return {"ok": False, "error": f"llama-parse package not installed: {exc}", "markdown": ""}

    try:
        parser_kwargs: Dict[str, Any] = {
            "api_key": LLAMA_CLOUD_API_KEY,
            "result_type": LLAMAPARSE_RESULT_TYPE,
            "verbose": False,
        }
        if LLAMAPARSE_PREMIUM_MODE:
            parser_kwargs["premium_mode"] = True
        parser = LlamaParse(**parser_kwargs)
        documents = parser.load_data(str(file_path))
        parts = []
        for doc in documents or []:
            text = getattr(doc, "text", None) or str(doc)
            if text and text.strip():
                parts.append(text.strip())
        markdown = "\n\n".join(parts)
        return {
            "ok": bool(markdown.strip()),
            "markdown": markdown,
            "page_count": len(documents or []),
            "backend": "llamaparse",
        }
    except Exception as exc:
        logger.warning("LlamaParse failed for %s: %s", file_path.name, exc)
        return {"ok": False, "error": str(exc)[:500], "markdown": ""}
