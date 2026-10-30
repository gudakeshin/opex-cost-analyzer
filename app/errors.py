"""Machine-readable error codes for API responses.

Every HTTP error keeps its human-readable ``detail`` and also carries a stable ``code`` clients can
branch on without parsing prose, e.g. ``{"detail": "Session not found", "code": "not_found"}``.
Use ``ApiError`` where a more specific code than the status-derived default is useful.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import HTTPException

_CODE_BY_STATUS: Dict[int, str] = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    410: "gone",
    413: "payload_too_large",
    422: "validation_error",
    429: "rate_limited",
    500: "internal_error",
    502: "bad_gateway",
    503: "unavailable",
    504: "gateway_timeout",
}


class ApiError(HTTPException):
    """HTTPException with an explicit machine-readable ``code``."""

    def __init__(self, status_code: int, detail: Any, code: str, headers: Optional[Dict[str, str]] = None) -> None:
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        self.code = code


def error_code(status_code: int, exc: Optional[BaseException] = None) -> str:
    explicit = getattr(exc, "code", None)
    if isinstance(explicit, str) and explicit:
        return explicit
    return _CODE_BY_STATUS.get(status_code, f"http_{status_code}")
