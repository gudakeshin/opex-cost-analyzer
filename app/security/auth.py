"""Bearer-token authentication and resource-ownership checks.

Configuration (env, read per-request so tests and live config reloads work):
  AUTH_ENABLED      "true"|"false" (default false) — master switch. When false
                    the API is open; app startup logs a prominent warning.
  API_AUTH_TOKENS   comma-separated tokens, each either "principal:token" or a
                    bare "token" (principal defaults to "default"). Example:
                      API_AUTH_TOKENS=alice:s3cr3t-a,bob:s3cr3t-b

Wiring: app.main attaches `require_auth` as a dependency on every router, so
all /api/* endpoints demand `Authorization: Bearer <token>` when enabled.
Health/metrics/static UI stay open.

Ownership: resources created while authenticated are stamped with the
principal (`owner` field). `check_owner` raises 403 when another principal
touches them. Records without an owner (legacy, or created while auth was
disabled) are accessible to any authenticated caller.
"""
from __future__ import annotations

import os
import secrets

from fastapi import HTTPException, Request

from app.config import logger


def auth_enabled() -> bool:
    return os.getenv("AUTH_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def _parse_tokens() -> dict[str, str]:
    """Return {token: principal} from API_AUTH_TOKENS."""
    out: dict[str, str] = {}
    for entry in os.getenv("API_AUTH_TOKENS", "").split(","):
        entry = entry.strip()
        if not entry:
            continue
        principal, sep, token = entry.partition(":")
        if sep and token.strip():
            out[token.strip()] = principal.strip() or "default"
        else:
            out[entry] = "default"
    return out


async def require_auth(request: Request) -> None:
    """Router-level dependency: validate the bearer token, record the principal."""
    if not auth_enabled():
        request.state.principal = None
        return

    tokens = _parse_tokens()
    if not tokens:
        # Enabled but unconfigured: deny everything rather than fail open.
        logger.error('"auth_enabled_without_tokens — set API_AUTH_TOKENS"')
        raise HTTPException(status_code=401, detail="Authentication is enabled but no API tokens are configured")

    header = request.headers.get("Authorization", "")
    scheme, _, supplied = header.partition(" ")
    supplied = supplied.strip()
    if scheme.lower() != "bearer" or not supplied:
        raise HTTPException(
            status_code=401,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    for token, principal in tokens.items():
        if secrets.compare_digest(supplied, token):
            request.state.principal = principal
            return
    raise HTTPException(
        status_code=401,
        detail="Invalid bearer token",
        headers={"WWW-Authenticate": "Bearer"},
    )


def current_principal(request: Request) -> str | None:
    return getattr(request.state, "principal", None)


def check_owner(request: Request, owner: object) -> None:
    """403 when an authenticated principal touches another principal's resource.

    No-op when auth is disabled or the resource has no owner (legacy records).
    """
    if not auth_enabled() or not owner:
        return
    if current_principal(request) != str(owner):
        raise HTTPException(status_code=403, detail="Forbidden: resource belongs to another principal")


def visible_to_principal(request: Request, owner: object) -> bool:
    """List-endpoint filter: legacy unowned records are visible to everyone."""
    if not auth_enabled() or not owner:
        return True
    return current_principal(request) == str(owner)


def check_session_owner(request: Request, session_id: str) -> None:
    """Ownership check for endpoints that carry session_id in the body."""
    if not auth_enabled():
        return
    from app.routers._shared import read_manifest

    check_owner(request, read_manifest(session_id).get("owner"))


async def enforce_resource_owner(request: Request) -> None:
    """Router-level dependency: 403 cross-principal access on path-param resources.

    Covers every route with an {engagement_id} or {session_id} path parameter;
    no-ops elsewhere. Malformed IDs and missing resources are left for the
    endpoint's own validation (400/404).
    """
    if not auth_enabled():
        return

    engagement_id = request.path_params.get("engagement_id")
    if engagement_id:
        from app.routers._shared import _UUID_RE
        from app.services.engagements_store import read_engagement_manifest

        if _UUID_RE.match(str(engagement_id)):
            try:
                manifest = read_engagement_manifest(str(engagement_id), auto_repair=False)
            except Exception:
                manifest = {}
            check_owner(request, (manifest or {}).get("owner"))

    session_id = request.path_params.get("session_id")
    if session_id:
        from app.routers._shared import _UUID_RE, read_manifest

        if _UUID_RE.match(str(session_id)):
            check_owner(request, read_manifest(str(session_id)).get("owner"))
