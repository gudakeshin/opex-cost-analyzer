"""Google Interactions API wrapper for the Deep Research feature.

Requires the `google-genai` package (distinct from `google-generativeai`).
Uses the same GEMINI_API_KEY.  Raises RuntimeError gracefully when the
package is absent or the key is missing so callers can surface a clear error.
"""
from __future__ import annotations

from typing import Any, Dict

from app.config import DEEP_RESEARCH_ENABLED, GEMINI_API_KEY, logger

_DEEP_RESEARCH_MODEL = "deep-research-preview-04-2026"


def _client():
    """Return a configured google.genai Client. Raises RuntimeError if unavailable."""
    if not DEEP_RESEARCH_ENABLED or not GEMINI_API_KEY:
        raise RuntimeError("Deep Research is not configured — set GEMINI_API_KEY")
    try:
        from google import genai  # type: ignore
    except ImportError:
        raise RuntimeError(
            "google-genai package is not installed. Run: pip install google-genai"
        )
    return genai.Client(api_key=GEMINI_API_KEY)


def start_deep_research(query: str) -> str:
    """Submit a background deep research job. Returns the interaction_id."""
    client = _client()
    interaction = client.interactions.create(
        input=query,
        agent=_DEEP_RESEARCH_MODEL,
        background=True,
        store=True,
    )
    interaction_id = str(interaction.id)
    logger.info('"deep_research_started","interaction_id":"%s"', interaction_id)
    return interaction_id


def poll_deep_research(interaction_id: str) -> Dict[str, Any]:
    """Poll the status of a deep research job.

    Returns a dict with keys:
        status       — "in_progress" | "completed" | "failed"
        output_text  — full report text (only when completed)
        sources      — list of citation dicts (only when completed)
    """
    client = _client()
    result = client.interactions.get(interaction_id)
    status = str(getattr(result, "status", "in_progress")).lower()
    output_text = getattr(result, "output_text", None) or ""
    citations = getattr(result, "citations", None) or []
    sources: list = []
    for c in citations:
        if isinstance(c, dict):
            sources.append(c)
        else:
            sources.append({
                "title": getattr(c, "title", None),
                "url": getattr(c, "url", None) or getattr(c, "uri", None),
            })
    logger.info(
        '"deep_research_polled","interaction_id":"%s","status":"%s"',
        interaction_id,
        status,
    )
    return {"status": status, "output_text": output_text, "sources": sources}
