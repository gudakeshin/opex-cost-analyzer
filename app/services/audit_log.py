"""Append-only audit log for the OpEx Intelligence Platform.

Writes every security-relevant event to a JSONL file (one JSON object per line).
The file is treated as WORM (Write Once Read Many): entries are never modified or deleted.

Format: JSON lines compatible with CEF / LEEF / SIEM ingest.
Schema per line:
  {
    "ts": "ISO-8601",
    "event_type": str,       # e.g. "pii_detected" | "band_classified" | "llm_call" | "teardown"
    "session_id": str,
    "engagement_id": str | null,
    "user_id": str | null,
    "detail": {...},         # event-specific payload
    "severity": "LOW|MEDIUM|HIGH|CRITICAL"
  }
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from app.config import ROOT_DIR, logger

_LOG_PATH = ROOT_DIR / "data" / "audit" / "audit.jsonl"
_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

_lock = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_event(
    event_type: str,
    detail: Dict[str, Any],
    *,
    session_id: str = "",
    engagement_id: Optional[str] = None,
    user_id: Optional[str] = None,
    severity: str = "LOW",
) -> None:
    """Write a single audit event to the WORM log file."""
    entry = {
        "ts": _now_iso(),
        "event_type": event_type,
        "session_id": session_id,
        "engagement_id": engagement_id,
        "user_id": user_id,
        "severity": severity,
        "detail": detail,
    }
    line = json.dumps(entry, ensure_ascii=False, default=str)
    try:
        with _lock:
            with _LOG_PATH.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
    except OSError as exc:
        # Never let audit-log failures crash the application
        logger.warning('"audit_log_write_failed: %s"', exc)


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------

def log_pii_detected(
    session_id: str,
    pii_types: list[str],
    field_names: list[str],
    row_count: int,
    *,
    engagement_id: Optional[str] = None,
    redacted: bool = True,
) -> None:
    append_event(
        "pii_detected",
        detail={
            "pii_types": pii_types,
            "field_names": field_names,
            "row_count": row_count,
            "redacted": redacted,
        },
        session_id=session_id,
        engagement_id=engagement_id,
        severity="HIGH",
    )


def log_band_classified(
    session_id: str,
    skill: str,
    band: str,
    inference_risk: float,
    *,
    engagement_id: Optional[str] = None,
) -> None:
    append_event(
        "band_classified",
        detail={"skill": skill, "band": band, "inference_risk_score": inference_risk},
        session_id=session_id,
        engagement_id=engagement_id,
        severity="LOW" if band in ("B1", "B2") else "MEDIUM",
    )


def log_llm_call(
    session_id: str,
    mode: str,
    skill: str,
    capability_level: str,
    *,
    engagement_id: Optional[str] = None,
    degraded: bool = False,
) -> None:
    append_event(
        "llm_call",
        detail={
            "mode": mode,
            "skill": skill,
            "capability_level": capability_level,
            "degraded": degraded,
        },
        session_id=session_id,
        engagement_id=engagement_id,
        severity="MEDIUM" if degraded else "LOW",
    )


def log_teardown(
    engagement_id: str,
    records_deleted: int,
    sessions_deleted: list[str],
    *,
    user_id: Optional[str] = None,
) -> None:
    append_event(
        "teardown",
        detail={
            "records_deleted": records_deleted,
            "sessions_deleted": sessions_deleted,
        },
        engagement_id=engagement_id,
        user_id=user_id,
        severity="HIGH",
    )


def log_mode_degradation(
    session_id: str,
    skill: str,
    mode: str,
    reason: str,
    *,
    engagement_id: Optional[str] = None,
) -> None:
    append_event(
        "mode_degradation",
        detail={"skill": skill, "mode": mode, "reason": reason},
        session_id=session_id,
        engagement_id=engagement_id,
        severity="MEDIUM",
    )


def replay_log(
    *,
    event_type: Optional[str] = None,
    session_id: Optional[str] = None,
    engagement_id: Optional[str] = None,
    limit: int = 1000,
) -> list[Dict[str, Any]]:
    """Read audit log and return filtered entries (newest-first, up to limit).

    Suitable for SIEM replay testing.
    """
    if not _LOG_PATH.exists():
        return []
    entries: list[Dict[str, Any]] = []
    try:
        with _LOG_PATH.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event_type and entry.get("event_type") != event_type:
                    continue
                if session_id and entry.get("session_id") != session_id:
                    continue
                if engagement_id and entry.get("engagement_id") != engagement_id:
                    continue
                entries.append(entry)
    except OSError:
        return []
    return list(reversed(entries))[:limit]
