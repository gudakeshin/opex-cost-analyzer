"""Shared API rate limiter.

A single Limiter instance lives here so both app.main (middleware + exception
handler registration) and individual routers (per-route limits on expensive
LLM-backed endpoints) can import it without circular imports.

Enforcement requires both pieces wired in app.main:
  - SlowAPIMiddleware  → applies RATE_LIMIT_DEFAULT to all undecorated routes
  - RateLimitExceeded exception handler → turns breaches into 429 responses

Configuration (env):
  RATE_LIMIT_ENABLED  "true"|"false"  — master switch (tests set false)
  RATE_LIMIT_DEFAULT  e.g. "300/minute" — every route without a decorator
  RATE_LIMIT_LLM      e.g. "10/minute"  — chat/analyze endpoints that call LLMs
  RATE_LIMIT_UPLOAD   e.g. "30/minute"  — document upload/reprocess endpoints

When REDIS_URL is set the limiter counts in Redis so limits hold across
workers/replicas; otherwise counts are per-process.
"""
from __future__ import annotations

import os

from slowapi import Limiter
from slowapi.util import get_remote_address


def _env_flag(name: str, default: str) -> bool:
    return os.getenv(name, default).strip().lower() not in {"0", "false", "no", "off"}


RATE_LIMIT_ENABLED = _env_flag("RATE_LIMIT_ENABLED", "true")
RATE_LIMIT_DEFAULT = os.getenv("RATE_LIMIT_DEFAULT", "300/minute")
RATE_LIMIT_LLM = os.getenv("RATE_LIMIT_LLM", "10/minute")
RATE_LIMIT_UPLOAD = os.getenv("RATE_LIMIT_UPLOAD", "30/minute")

_storage_uri = os.getenv("REDIS_URL", "").strip() or "memory://"

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[RATE_LIMIT_DEFAULT],
    storage_uri=_storage_uri,
    in_memory_fallback_enabled=_storage_uri != "memory://",
    enabled=RATE_LIMIT_ENABLED,
)
