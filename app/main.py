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

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.metrics import http_request_duration_seconds, http_requests_total
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
from app.routers import benchmarks, chat, compliance, engagements, enterprise, outputs, pipeline, sessions, skills
from app.storage import ensure_dirs

# ---------------------------------------------------------------------------
# Module-level setup
# ---------------------------------------------------------------------------
ensure_dirs()

_SESSION_TTL_DAYS = int(os.getenv("SESSION_TTL_DAYS", "30"))
_CLEANUP_INTERVAL_H = int(os.getenv("CLEANUP_INTERVAL_HOURS", "24"))

# Shared memory store for health/usage stats (MemoryStore is stateless wrapper).
from app.memory import MemoryStore as _MemoryStore
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

# Rate limiting: 10 req/min on LLM-backed endpoints, 200/min everywhere else.
_limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])
app.state.limiter = _limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]


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
def health_ready():  # type: ignore[return]
    if not ANTHROPIC_ENABLED:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "reason": "ANTHROPIC_API_KEY not configured"},
        )
    return {"status": "ready"}


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(engagements.router)
app.include_router(sessions.router)
app.include_router(chat.router)
app.include_router(pipeline.router)
app.include_router(benchmarks.router)
app.include_router(skills.router)
app.include_router(outputs.router)
app.include_router(compliance.router)
app.include_router(enterprise.router)


# ---------------------------------------------------------------------------
# Static frontend
# ---------------------------------------------------------------------------
_frontend_dist = ROOT_DIR / "frontend" / "dist"
_frontend_static = _frontend_dist if _frontend_dist.is_dir() else ROOT_DIR / "frontend"
app.mount("/ui", StaticFiles(directory=str(_frontend_static), html=True), name="ui")
