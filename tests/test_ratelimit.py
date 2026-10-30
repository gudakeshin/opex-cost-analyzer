"""Rate limiting wiring + enforcement.

conftest disables the limiter globally (RATE_LIMIT_ENABLED=false) because the
whole suite shares one client IP; these tests re-enable it briefly to prove
the middleware/decorator path actually returns 429 when breached.
"""
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from slowapi.middleware import SlowAPIMiddleware

from app.main import app
from app.ratelimit import limiter


def test_slowapi_middleware_and_limiter_registered() -> None:
    assert any(m.cls is SlowAPIMiddleware for m in app.user_middleware)
    assert app.state.limiter is limiter


def test_llm_endpoint_returns_429_beyond_limit() -> None:
    client = TestClient(app)
    # Valid-format session that doesn't exist: the handler 404s, but the
    # limit check runs first, so hits are counted without invoking any LLM.
    payload = {"message": "hello", "session_id": str(uuid.uuid4())}
    limiter.reset()
    limiter.enabled = True
    try:
        statuses = [client.post("/api/v1/chat", json=payload).status_code for _ in range(11)]
    finally:
        limiter.enabled = False
        limiter.reset()
    assert statuses[:10] == [404] * 10
    assert statuses[10] == 429


def test_nl2sql_returns_429_beyond_limit() -> None:
    client = TestClient(app)
    sid = str(uuid.uuid4())
    payload = {"question": "top suppliers", "execute": False}
    limiter.reset()
    limiter.enabled = True
    try:
        statuses = [
            client.post(f"/api/v1/query/{sid}/nl2sql", json=payload).status_code
            for _ in range(11)
        ]
    finally:
        limiter.enabled = False
        limiter.reset()
    # Session validation 404s (or 422) before LLM work; limit still counts.
    assert statuses[10] == 429
    assert all(c != 429 for c in statuses[:10])


def test_sensitivity_parse_returns_429_beyond_limit() -> None:
    client = TestClient(app)
    payload = {"session_id": str(uuid.uuid4()), "question": "what if savings drop 10%"}
    limiter.reset()
    limiter.enabled = True
    try:
        statuses = [
            client.post("/api/v1/sensitivity/parse", json=payload).status_code
            for _ in range(11)
        ]
    finally:
        limiter.enabled = False
        limiter.reset()
    assert statuses[10] == 429
    assert all(c != 429 for c in statuses[:10])


def test_analyst_and_workbench_routes_are_llm_rate_limited() -> None:
    """Heavy fixtures — assert the decorator is wired without exhausting the limit."""
    from app.routers import analyst, workbench

    # slowapi wraps the endpoint; presence of __wrapped__ proves decoration.
    assert hasattr(analyst.run_analyst_turn, "__wrapped__")
    assert hasattr(workbench.post_workbench_run, "__wrapped__")


def test_health_endpoints_exempt_from_limits() -> None:
    client = TestClient(app)
    limiter.reset()
    limiter.enabled = True
    try:
        codes = {client.get("/health").status_code for _ in range(5)}
    finally:
        limiter.enabled = False
        limiter.reset()
    assert codes == {200}


def test_multiworker_without_redis_fails_fast(monkeypatch) -> None:
    import pytest

    from app.main import _guard_multiworker_without_redis

    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("UVICORN_WORKERS", "2")
    with pytest.raises(RuntimeError, match="REDIS_URL"):
        _guard_multiworker_without_redis()

    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    _guard_multiworker_without_redis()  # no raise when Redis configured

    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("UVICORN_WORKERS", "1")
    _guard_multiworker_without_redis()  # single worker is always fine


def test_multiworker_cli_args_without_redis_fails_fast(monkeypatch) -> None:
    import sys

    import pytest

    from app.main import _guard_multiworker_without_redis

    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("UVICORN_WORKERS", raising=False)
    monkeypatch.delenv("WEB_CONCURRENCY", raising=False)

    for argv in (
        ["uvicorn", "app.main:app", "--workers", "4"],
        ["uvicorn", "app.main:app", "--workers=4"],
        ["gunicorn", "app.main:app", "-w", "4"],
    ):
        monkeypatch.setattr(sys, "argv", argv)
        with pytest.raises(RuntimeError, match="REDIS_URL"):
            _guard_multiworker_without_redis()

    monkeypatch.setattr(sys, "argv", ["uvicorn", "app.main:app", "--workers", "1"])
    _guard_multiworker_without_redis()  # single worker is always fine

    monkeypatch.setattr(sys, "argv", ["uvicorn", "app.main:app", "--workers", "4"])
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    _guard_multiworker_without_redis()  # no raise when Redis configured
