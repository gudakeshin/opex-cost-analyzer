"""Which models actually answered during a request.

Provenance records the *configured* model. When the primary provider fails and the app falls back
to the other one, the narrative was written by a different model, so we also keep a per-request
trace of (provider, model) pairs from the usage recorder.
"""
from __future__ import annotations

import contextvars
from contextlib import contextmanager
from typing import Any, Dict, Generator, List, Optional, Tuple

_trace_var: contextvars.ContextVar[Optional[List[Tuple[str, str]]]] = contextvars.ContextVar(
    "llm_model_trace", default=None
)


@contextmanager
def trace_scope() -> Generator[None, None, None]:
    token = _trace_var.set([])
    try:
        yield
    finally:
        _trace_var.reset(token)


def record(provider: str, model: str) -> None:
    trace = _trace_var.get()
    if trace is not None and (provider, model) not in trace:
        trace.append((provider, model))


def summary() -> Dict[str, Any]:
    trace = _trace_var.get() or []
    providers = sorted({p for p, _ in trace})
    return {
        "llm_models_used": [f"{p}:{m}" for p, m in trace],
        "provider_fallback": len(providers) > 1,
    }
