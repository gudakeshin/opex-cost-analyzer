from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from app.config import DATA_DIR, request_id_var


RISK_REGISTER_PATH = DATA_DIR / "risk_register.md"
_AUDIT_LOCK = threading.Lock()

# Archive the active log when it grows beyond this size (bytes).
_ROTATE_THRESHOLD_BYTES = 50 * 1024 * 1024  # 50 MB


def _rotate_audit_log(audit_path: Path) -> None:
    """Move audit.log to audit.log.<YYYYMMDD-HHMMSSz> when it exceeds the size threshold."""
    if not audit_path.exists() or audit_path.stat().st_size < _ROTATE_THRESHOLD_BYTES:
        return
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "z"
    archive = audit_path.with_name(f"{audit_path.name}.{stamp}")
    try:
        audit_path.rename(archive)
    except OSError:
        pass


def ensure_risk_register() -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if RISK_REGISTER_PATH.exists():
        return RISK_REGISTER_PATH
    content = """# Risk Register

## Benchmark Data Licensing
- Status: open
- Owner: product/legal
- Mitigation: maintain source attribution, restrict to illustrative data until licensed feeds are contracted.

## Framework Usage and IP
- Status: open
- Owner: legal
- Mitigation: convert direct references into generalized heuristics and keep citation metadata.

## Memory Privacy and Deletion
- Status: in_progress
- Owner: engineering
- Mitigation: support scope-based deletion endpoints for user/session/agent memory.
"""
    RISK_REGISTER_PATH.write_text(content, encoding="utf-8")
    return RISK_REGISTER_PATH


def _compute_chain_hash(prev_hash: str, record: Dict[str, Any]) -> str:
    """SHA-256 of (prev_hash + record JSON) — creates a tamper-evident chain."""
    payload = prev_hash + json.dumps(record, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def _read_last_chain_hash(audit_path: Path) -> str:
    """Return the chain_hash from the last line of the audit log, or genesis hash."""
    genesis = "0" * 64
    if not audit_path.exists():
        return genesis
    try:
        with audit_path.open("r", encoding="utf-8") as fh:
            last_line = ""
            for line in fh:
                stripped = line.strip()
                if stripped:
                    last_line = stripped
        if last_line:
            rec = json.loads(last_line)
            return rec.get("chain_hash", genesis)
    except Exception:
        pass
    return genesis


def append_audit_event(
    event: str,
    *,
    session_id: Optional[str] = None,
    engagement_id: Optional[str] = None,
    user_id: Optional[str] = None,
    request_id: Optional[str] = None,
    data: Any = None,
) -> Path:
    """Append a structured NDJSON audit record with tamper-evident chain hash.

    Fields in every record: ts, event, request_id, engagement_id, session_id,
    user_id, data_hash, chain_hash. Pass only the fields that apply; omitted
    fields are excluded from the record (keeping logs compact).
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    audit_path = DATA_DIR / "audit.log"

    # Auto-populate request_id from the per-request contextvar when not given.
    rid = request_id or request_id_var.get(None)

    data_hash: Optional[str] = None
    if data is not None:
        try:
            raw = json.dumps(data, sort_keys=True, default=str)
            data_hash = hashlib.sha256(raw.encode()).hexdigest()[:16]
        except Exception:
            data_hash = None

    record: Dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
    }
    if rid is not None and rid not in ("-", ""):
        record["request_id"] = rid
    if engagement_id is not None:
        record["engagement_id"] = engagement_id
    if session_id is not None:
        record["session_id"] = session_id
    if user_id is not None:
        record["user_id"] = user_id
    if data_hash is not None:
        record["data_hash"] = data_hash

    with _AUDIT_LOCK:
        _rotate_audit_log(audit_path)
        prev_hash = _read_last_chain_hash(audit_path)
        record["chain_hash"] = _compute_chain_hash(prev_hash, record)
        line = json.dumps(record, separators=(",", ":")) + "\n"
        with audit_path.open("a", encoding="utf-8") as handle:
            handle.write(line)

    return audit_path


def verify_audit_log() -> Dict[str, Any]:
    """Verify chain integrity of the audit log. Returns a summary report.

    Lines written before the structured-NDJSON format was introduced are
    treated as legacy and skipped — they are not tampered records. The chain
    starts from the first JSON line found.
    """
    audit_path = DATA_DIR / "audit.log"
    if not audit_path.exists():
        return {"status": "empty", "records": 0, "legacy_records": 0, "chain_valid": True}

    genesis = "0" * 64
    prev_hash = genesis
    count = 0
    legacy_count = 0
    broken_at: Optional[int] = None
    chain_started = False

    with audit_path.open("r", encoding="utf-8") as fh:
        for line_num, line in enumerate(fh, 1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                rec = json.loads(stripped)
            except json.JSONDecodeError:
                # Pre-Phase-4 plain-text line — skip, do not fail the chain.
                legacy_count += 1
                continue

            if not chain_started:
                # First JSON record — reset prev_hash to its own stored chain hash
                # so verification continues correctly from the log's first JSON entry.
                chain_started = True
                prev_hash = rec.get("chain_hash", genesis)
                count += 1
                continue

            stored_chain = rec.get("chain_hash", "")
            rec_without_chain = {k: v for k, v in rec.items() if k != "chain_hash"}
            expected = _compute_chain_hash(prev_hash, rec_without_chain)
            if stored_chain != expected:
                broken_at = line_num
                break
            prev_hash = stored_chain
            count += 1

    return {
        "status": "ok" if broken_at is None else "tampered",
        "records": count,
        "legacy_records": legacy_count,
        "chain_valid": broken_at is None,
        "broken_at_line": broken_at,
    }


def list_audit_events(limit: int = 50) -> list[Dict[str, Any]]:
    """Return recent audit log entries (newest first)."""
    audit_path = DATA_DIR / "audit.log"
    if not audit_path.exists():
        return []
    entries: list[Dict[str, Any]] = []
    try:
        with audit_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    rec = json.loads(stripped)
                except json.JSONDecodeError:
                    rec = {"ts": "", "event": stripped, "legacy": True}
                entries.append(rec)
    except OSError:
        return []
    return list(reversed(entries))[: max(1, min(limit, 500))]


def privacy_controls_summary() -> Dict[str, str]:
    return {
        "memory_scopes": "user/session/agent with explicit delete API",
        "retention": "session memory can be purged by API call or policy scheduler",
        "audit_log": "NDJSON tamper-evident chain; no delete API",
        "dpdp_teardown": "engagement_id scoped purge with attestation receipt",
        "status": "baseline controls implemented",
    }
