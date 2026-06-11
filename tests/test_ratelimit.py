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
