"""Layer 2: Trace load/save/summarize utilities.

EvalTrace is written by app/opar/act.py when enable_tracing=True.
These helpers load, inspect, and summarize those traces for evaluation.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from app.config import UPLOAD_DIR
from app.opar.models import EvalTrace, SkillTrace


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def trace_path(session_id: str) -> Path:
    return UPLOAD_DIR / session_id / "eval_trace.json"


def load_trace(session_id: str) -> Optional[EvalTrace]:
    """Load a persisted EvalTrace for a session. Returns None if not found."""
    p = trace_path(session_id)
    if not p.exists():
        return None
    try:
        return EvalTrace.model_validate_json(p.read_text())
    except Exception:
        return None


def save_trace(trace: EvalTrace) -> Path:
    """Explicitly save an EvalTrace (useful for test fixtures)."""
    out = trace_path(trace.session_id)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(trace.model_dump_json(indent=2))
    return out


# ---------------------------------------------------------------------------
# Summarization
# ---------------------------------------------------------------------------

def summarize_trace(trace: EvalTrace) -> str:
    """Return a markdown table summarising each skill's trace entry.

    Columns: skill | group | duration_ms | output_keys | error
    """
    rows = [
        "| skill | group | duration_ms | output_keys | error |",
        "|---|---|---|---|---|",
    ]
    for st in trace.skill_traces:
        keys = ", ".join(sorted(st.output.keys())) if st.output else "—"
        err = st.error or "—"
        rows.append(
            f"| {st.skill_name} | {st.parallel_group} "
            f"| {st.duration_ms:.1f} | {keys} | {err} |"
        )
    header = (
        f"**EvalTrace** — session `{trace.session_id}` | "
        f"turn `{trace.turn_id}` | "
        f"total {trace.total_duration_ms:.0f} ms | "
        f"{len(trace.skill_traces)} skill(s)\n\n"
    )
    return header + "\n".join(rows)


# ---------------------------------------------------------------------------
# Trace assertions (for Layer 2 tests)
# ---------------------------------------------------------------------------

def assert_trace_complete(trace: EvalTrace, expected_skill_names: list[str]) -> list[str]:
    """Return list of expected skills missing from the trace (empty = all present)."""
    traced = {st.skill_name for st in trace.skill_traces}
    return [s for s in expected_skill_names if s not in traced]


def get_skill_trace(trace: EvalTrace, skill_name: str) -> Optional[SkillTrace]:
    """Retrieve the SkillTrace for a given skill, or None."""
    for st in trace.skill_traces:
        if st.skill_name == skill_name:
            return st
    return None
