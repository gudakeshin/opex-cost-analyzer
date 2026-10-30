"""LLM provider error classification — permanent failures should not be retried."""
from __future__ import annotations



class ProviderPermanentError(Exception):
    """Base for non-retryable provider failures (billing, auth, hard rate limits)."""

    skip_reason: str = "provider_failed"

    def __init__(self, message: str, *, skip_reason: str | None = None) -> None:
        super().__init__(message)
        if skip_reason:
            self.skip_reason = skip_reason


class ProviderBillingError(ProviderPermanentError):
    skip_reason = "provider_billing"


class ProviderAuthError(ProviderPermanentError):
    skip_reason = "provider_auth"


class ProviderRateLimitError(ProviderPermanentError):
    skip_reason = "provider_rate_limit"


def _message_text(exc: BaseException) -> str:
    parts = [str(exc)]
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict) and err.get("message"):
            parts.append(str(err["message"]))
    return " ".join(parts).lower()


def classify_provider_error(exc: BaseException) -> ProviderPermanentError | None:
    """Map a provider SDK exception to a permanent error class, or None if retryable."""
    text = _message_text(exc)
    status = getattr(exc, "status_code", None)

    if status in (401, 403) or "authentication" in text or "invalid api key" in text or "invalid x-api-key" in text:
        return ProviderAuthError(str(exc), skip_reason="provider_auth")
    if (
        status == 400
        and any(tok in text for tok in ("credit", "billing", "balance", "payment", "purchase"))
    ) or "credit balance" in text:
        return ProviderBillingError(str(exc), skip_reason="provider_billing")
    if status == 429 or "rate limit" in text or "too many requests" in text:
        return ProviderRateLimitError(str(exc), skip_reason="provider_rate_limit")
    return None


def classify_anthropic_exception(exc: BaseException) -> ProviderPermanentError | None:
    """Classify Anthropic SDK errors; returns permanent error or None."""
    name = type(exc).__name__
    if name in {"AuthenticationError", "PermissionDeniedError"}:
        return ProviderAuthError(str(exc), skip_reason="provider_auth")
    if name == "BadRequestError":
        return classify_provider_error(exc) or None
    if name == "RateLimitError":
        return ProviderRateLimitError(str(exc), skip_reason="provider_rate_limit")
    return classify_provider_error(exc)


def is_permanent_skip_reason(reason: str | None) -> bool:
    return reason in {
        "provider_billing",
        "provider_auth",
        "provider_rate_limit",
        "provider_unavailable",
    }
