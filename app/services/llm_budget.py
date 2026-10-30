"""Per-engagement LLM spend tracking and an optional hard cap.

Cost is estimated from token usage (see ``app.metrics``) and attributed to the engagement
in scope for the current request. When ``LLM_MAX_COST_USD_PER_ENGAGEMENT`` is set and an
engagement has reached it, further LLM calls raise ``LLMBudgetExceeded``; callers already
treat provider-permanent errors as "skip synthesis", so the app falls back to its
deterministic narrative instead of spending more.

Unset (the default) means no cap; usage is still recorded. Figures are estimates from
list prices, not billing data.
"""
from __future__ import annotations

import contextvars
import json
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generator, Optional

from app import config

_scope_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("llm_budget_scope", default=None)
_lock = threading.Lock()


def _store_path() -> Path:
    return config.DATA_DIR / "llm_usage.json"


def _load() -> Dict[str, Any]:
    try:
        data = json.loads(_store_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"scopes": {}}
    return data if isinstance(data, dict) and isinstance(data.get("scopes"), dict) else {"scopes": {}}


def _save(data: Dict[str, Any]) -> None:
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)


def cap_usd() -> Optional[float]:
    cap = config.LLM_MAX_COST_USD_PER_ENGAGEMENT
    return cap if cap and cap > 0 else None


def resolve_scope(session_id: Optional[str]) -> Optional[str]:
    """Engagement id for a session (falls back to the session id itself)."""
    if not session_id:
        return None
    try:
        from app.routers._shared import read_manifest

        return str(read_manifest(session_id).get("engagement_id") or session_id)
    except Exception:
        return session_id


@contextmanager
def budget_scope(scope: Optional[str]) -> Generator[None, None, None]:
    token = _scope_var.set(scope)
    try:
        yield
    finally:
        _scope_var.reset(token)


def current_scope() -> Optional[str]:
    return _scope_var.get()


def add_spend(cost_usd: float, scope: Optional[str] = None) -> None:
    """Attribute an LLM call's estimated cost to the engagement in scope (no-op without one)."""
    key = scope or _scope_var.get()
    if not key or cost_usd <= 0:
        return
    with _lock:
        data = _load()
        entry = data["scopes"].setdefault(key, {"cost_usd": 0.0, "calls": 0})
        entry["cost_usd"] = round(float(entry.get("cost_usd", 0.0)) + float(cost_usd), 6)
        entry["calls"] = int(entry.get("calls", 0)) + 1
        entry["updated_at"] = datetime.now(timezone.utc).isoformat()
        _save(data)


def status(scope: str) -> Dict[str, Any]:
    with _lock:
        entry = _load()["scopes"].get(scope, {})
    spent = float(entry.get("cost_usd", 0.0))
    cap = cap_usd()
    return {
        "scope": scope,
        "spent_usd": round(spent, 4),
        "calls": int(entry.get("calls", 0)),
        "cap_usd": cap,
        "remaining_usd": round(max(cap - spent, 0.0), 4) if cap else None,
        "exceeded": bool(cap and spent >= cap),
        "estimate_note": "Estimated from token usage at list prices; not billing data.",
    }


def check_budget() -> None:
    """Raise ``LLMBudgetExceeded`` if the engagement in scope has used up its cap."""
    cap = cap_usd()
    scope = _scope_var.get()
    if not cap or not scope:
        return
    spent = status(scope)["spent_usd"]
    if spent >= cap:
        from app.opar.llm_errors import LLMBudgetExceeded

        raise LLMBudgetExceeded(
            f"LLM budget for this engagement is used up (~${spent:.2f} of ${cap:.2f}). "
            "Raise LLM_MAX_COST_USD_PER_ENGAGEMENT to continue live synthesis."
        )
