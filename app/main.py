"""FastAPI application factory.

All route logic lives in app/routers/. This module is responsible only for:
  - creating the FastAPI app instance
  - registering middleware (CORS, request-ID correlation)
  - registering routers
  - startup tasks (periodic session cleanup)
  - health/readiness endpoints
  - serving the compiled React frontend as static files
"""
from __future__ import annotations

import asyncio
import os
import re
import time
import uuid
from typing import Any

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.metrics import http_request_duration_seconds, http_requests_total
from app.ratelimit import RATE_LIMIT_ENABLED, limiter
from app.config import (
    ANTHROPIC_ENABLED,
    APP_NAME,
    APP_VERSION,
    QDRANT_ENABLED,
    ROOT_DIR,
    logger,
    request_id_var,
)
from app.opar.memory_adapter import get_memory_adapter_status
from app.services.document_index import get_document_index_status
from app.routers import benchmarks, chat, compliance, connectors, engagements, enterprise, llm, outputs, pipeline, sessions, skills
from app.security.auth import auth_enabled, enforce_resource_owner, require_auth
from app.storage import ensure_dirs
from app.memory import MemoryStore as _MemoryStore

# ---------------------------------------------------------------------------
# Module-level setup
# ---------------------------------------------------------------------------
ensure_dirs()


def _guard_multiworker_without_redis() -> None:
    """Fail fast on a known-corrupting config: >1 worker without Redis.

    Session/manifest locks fall back to in-process locks when REDIS_URL is
    unset; two workers then interleave read-modify-write cycles on the same
    JSON manifests. UVICORN_WORKERS (our Dockerfile) and WEB_CONCURRENCY
    (gunicorn convention) are the explicit signals we can check.
    """
    if os.getenv("REDIS_URL", "").strip():
        return
    for var in ("UVICORN_WORKERS", "WEB_CONCURRENCY"):
        raw = os.getenv(var, "").strip()
        if raw.isdigit() and int(raw) > 1:
            raise RuntimeError(
                f"{var}={raw} requires REDIS_URL: without Redis, session/manifest "
                "locks are per-process and concurrent workers corrupt JSON state. "
                "Set REDIS_URL or run a single worker."
            )


_guard_multiworker_without_redis()

_SESSION_TTL_DAYS = int(os.getenv("SESSION_TTL_DAYS", "30"))
_CLEANUP_INTERVAL_H = int(os.getenv("CLEANUP_INTERVAL_HOURS", "24"))

# Shared memory store for health/usage stats (MemoryStore is stateless wrapper).
_memory_store = _MemoryStore()


async def _periodic_cleanup() -> None:
    while True:
        await asyncio.sleep(_CLEANUP_INTERVAL_H * 3600)
        try:
            _memory_store.cleanup_expired_sessions(ttl_days=_SESSION_TTL_DAYS)
        except Exception as exc:
            logger.warning('"cleanup_error error=%s"', exc)


# ---------------------------------------------------------------------------
# App instance
# ---------------------------------------------------------------------------
app = FastAPI(title=APP_NAME, version=APP_VERSION)

# Rate limiting (app/ratelimit.py): RATE_LIMIT_LLM on LLM-backed endpoints via
# per-route decorators, RATE_LIMIT_DEFAULT everywhere else via SlowAPIMiddleware.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
app.add_middleware(SlowAPIMiddleware)
if not RATE_LIMIT_ENABLED:
    logger.warning('"rate_limiting DISABLED via RATE_LIMIT_ENABLED — do not run in production"')


@app.on_event("startup")
async def _on_startup() -> None:
    logger.info('"app_startup version=%s"', APP_VERSION)
    asyncio.create_task(_periodic_cleanup())


# CORS
_cors_origins_raw = os.environ.get(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://localhost:5173,http://localhost:8000",
)
_cors_origins = [o.strip() for o in _cors_origins_raw.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization", "X-Request-ID", "X-Eval-Key"],
)


@app.middleware("http")
async def _correlation_id_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
    rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    token = request_id_var.set(rid)
    try:
        response = await call_next(request)
    finally:
        request_id_var.reset(token)
    response.headers["X-Request-ID"] = rid
    # Inject Deprecation header on unversioned /api/ paths so callers know to migrate.
    path = request.url.path
    if path.startswith("/api/") and not path.startswith("/api/v1/"):
        response.headers["Deprecation"] = "true"
        response.headers["Sunset"] = "2027-01-01"
    return response


# Collapse path parameters so /api/sessions/abc-123 → /api/sessions/{session_id}
_PATH_PARAM_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|"
    r"\b\d{5,}\b",
    re.IGNORECASE,
)


def _endpoint_label(path: str) -> str:
    return _PATH_PARAM_RE.sub("{id}", path)


@app.middleware("http")
async def _prometheus_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
    start = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - start
    label = _endpoint_label(request.url.path)
    http_requests_total.labels(
        method=request.method, endpoint=label, status=str(response.status_code)
    ).inc()
    http_request_duration_seconds.labels(method=request.method, endpoint=label).observe(duration)
    return response


@app.get("/metrics", include_in_schema=False)
@limiter.exempt
def prometheus_metrics() -> Response:
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.exception_handler(Exception)
async def _global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    from fastapi import HTTPException
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})
    trace_id = request_id_var.get(request.headers.get("X-Request-ID", "unknown"))
    logger.exception('"unhandled_exception trace_id=%s path=%s"', trace_id, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"error": "internal_server_error", "trace_id": trace_id, "detail": str(exc)},
    )


# ---------------------------------------------------------------------------
# Health endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
@limiter.exempt
def health():  # type: ignore[return]
    mem_status = get_memory_adapter_status()
    doc_status = get_document_index_status()
    usage = _memory_store.usage_stats()
    return {
        "status": "ok",
        "version": APP_VERSION,
        "connectors": {
            "memory_backend": mem_status.get("backend"),
            "qdrant_configured": QDRANT_ENABLED,
            "qdrant_active": mem_status.get("qdrant_active"),
            "memory_status_reason": mem_status.get("reason"),
            "document_index_backend": doc_status.get("backend"),
            "document_index_reason": doc_status.get("reason"),
            "anthropic_configured": ANTHROPIC_ENABLED,
        },
        "storage": usage,
    }


@app.get("/health/ready")
@limiter.exempt
async def health_ready() -> JSONResponse:  # type: ignore[return]
    """Dependency-aware readiness probe.

    Returns 200 only when every hard dependency is reachable.
    Soft dependencies (Qdrant, Redis) are reported but do not fail the probe.
    """
    checks: dict[str, Any] = {}
    failing: list[str] = []

    # --- Anthropic (hard dependency) ---
    if ANTHROPIC_ENABLED:
        try:
            from app.config import ANTHROPIC_API_KEY
            import anthropic as _anthropic
            _client = _anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
            await asyncio.wait_for(_client.models.list(), timeout=5.0)
            checks["anthropic"] = "ok"
        except Exception as _exc:
            checks["anthropic"] = f"unreachable: {_exc}"
            failing.append("anthropic")
    else:
        checks["anthropic"] = "not_configured"
        failing.append("anthropic")

    # --- Redis (soft dependency: only required for multi-worker) ---
    redis_url = os.getenv("REDIS_URL", "").strip()
    if redis_url:
        try:
            import redis.asyncio as aioredis  # type: ignore[import]
            _r = aioredis.from_url(redis_url, socket_connect_timeout=3)
            await asyncio.wait_for(_r.ping(), timeout=3.0)
            await _r.aclose()
            checks["redis"] = "ok"
        except Exception as _exc:
            checks["redis"] = f"unreachable: {_exc}"
            # Redis is only hard-required when multi-worker
            for _v in ("UVICORN_WORKERS", "WEB_CONCURRENCY"):
                _w = os.getenv(_v, "1")
                if _w.isdigit() and int(_w) > 1:
                    failing.append("redis")
                    break
    else:
        checks["redis"] = "not_configured"

    # --- Qdrant (soft dependency) ---
    if QDRANT_ENABLED:
        try:
            from app.opar.memory_adapter import get_memory_adapter_status
            _s = get_memory_adapter_status()
            if _s.get("qdrant_active"):
                checks["qdrant"] = "ok"
            else:
                checks["qdrant"] = f"degraded: {_s.get('reason', 'unknown')}"
        except Exception as _exc:
            checks["qdrant"] = f"unreachable: {_exc}"
    else:
        checks["qdrant"] = "not_configured"

    if failing:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "failing": failing, "checks": checks},
        )
    return JSONResponse(content={"status": "ready", "checks": checks})


# ---------------------------------------------------------------------------
# Routers — every API router sits behind bearer-token auth (app/security/auth.py).
# Health, /metrics, and the static UI mount stay open.
# ---------------------------------------------------------------------------
if not auth_enabled():
    logger.warning(
        '"api_auth DISABLED (AUTH_ENABLED=false) — every endpoint is open; '
        'do not expose this deployment beyond localhost"'
    )

# require_auth runs first (sets request.state.principal), then the ownership
# check for any route carrying {engagement_id}/{session_id} path params.
_auth = [Depends(require_auth), Depends(enforce_resource_owner)]
app.include_router(engagements.router, dependencies=_auth)
app.include_router(sessions.router, dependencies=_auth)
app.include_router(connectors.router, dependencies=_auth)
app.include_router(chat.router, dependencies=_auth)
app.include_router(llm.router, dependencies=_auth)
app.include_router(pipeline.router, dependencies=_auth)
app.include_router(benchmarks.router, dependencies=_auth)
app.include_router(skills.router, dependencies=_auth)
app.include_router(outputs.router, dependencies=_auth)
app.include_router(compliance.router, dependencies=_auth)
app.include_router(enterprise.router, dependencies=_auth)


# ---------------------------------------------------------------------------
# Static frontend
# ---------------------------------------------------------------------------
_frontend_dist = ROOT_DIR / "frontend" / "dist"
_frontend_static = _frontend_dist if _frontend_dist.is_dir() else ROOT_DIR / "frontend"
app.mount("/ui", StaticFiles(directory=str(_frontend_static), html=True), name="ui")
