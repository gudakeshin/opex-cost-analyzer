"""In-process registry of analysis runs: one active run per session, cooperative cancel.

Cancellation is cooperative. ``request_cancel`` sets a flag; the pipeline checks it at its
progress checkpoints (between stages) and raises ``AnalysisCancelled``, so a run stops
between steps and never leaves half-written results. A stage that is already executing
finishes first.

State is per process. With more than one worker, runs and cancels are only visible to the
worker that started them (the same limitation as the in-process session locks).
"""
from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

ACTIVE = ("running", "cancelling")
TERMINAL = ("completed", "failed", "cancelled")
_KEEP_FINISHED = 200


class AnalysisCancelled(Exception):
    """Raised inside the pipeline when a cancel was requested."""


class AnalysisAlreadyRunning(Exception):
    def __init__(self, run_id: str) -> None:
        super().__init__(f"An analysis is already running (run {run_id}).")
        self.run_id = run_id


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class AnalysisRun:
    run_id: str
    session_id: str
    status: str = "running"
    started_at: str = field(default_factory=_now)
    finished_at: Optional[str] = None
    error: Optional[str] = None
    cancel_event: threading.Event = field(default_factory=threading.Event, repr=False)
    task: Optional["asyncio.Task[Any]"] = field(default=None, repr=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "session_id": self.session_id,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
        }


_lock = threading.Lock()
_runs: Dict[str, AnalysisRun] = {}
_active_by_session: Dict[str, str] = {}


def start(session_id: str, run_id: str) -> AnalysisRun:
    """Register a new run, or raise ``AnalysisAlreadyRunning`` if the session has one."""
    with _lock:
        existing = _active_by_session.get(session_id)
        if existing and _runs.get(existing) and _runs[existing].status in ACTIVE:
            raise AnalysisAlreadyRunning(existing)
        run = AnalysisRun(run_id=run_id, session_id=session_id)
        _runs[run_id] = run
        _active_by_session[session_id] = run_id
        finished = [r for r in _runs.values() if r.status in TERMINAL]
        for old in sorted(finished, key=lambda r: r.finished_at or "")[:-_KEEP_FINISHED]:
            _runs.pop(old.run_id, None)
        return run


def attach_task(run_id: str, task: "asyncio.Task[Any]") -> None:
    with _lock:
        run = _runs.get(run_id)
        if run:
            run.task = task  # keeps a reference so a background task is not garbage-collected


def get(run_id: str) -> Optional[AnalysisRun]:
    with _lock:
        return _runs.get(run_id)


def active_for_session(session_id: str) -> Optional[AnalysisRun]:
    with _lock:
        run_id = _active_by_session.get(session_id)
        run = _runs.get(run_id) if run_id else None
        return run if run and run.status in ACTIVE else None


def request_cancel(run_id: str) -> Optional[AnalysisRun]:
    """Ask a running analysis to stop at its next checkpoint. Returns the run, or None if unknown."""
    with _lock:
        run = _runs.get(run_id)
        if run and run.status == "running":
            run.status = "cancelling"
            run.cancel_event.set()
        return run


def check_cancel(run_id: str) -> None:
    """Called from pipeline checkpoints; raises ``AnalysisCancelled`` once a cancel was requested."""
    run = get(run_id)
    if run and run.cancel_event.is_set():
        raise AnalysisCancelled(run_id)


def finish(run_id: str, status: str, error: Optional[str] = None) -> None:
    with _lock:
        run = _runs.get(run_id)
        if not run:
            return
        run.status = status
        run.error = error
        run.finished_at = _now()
        if _active_by_session.get(run.session_id) == run_id:
            _active_by_session.pop(run.session_id, None)
        run.task = None
