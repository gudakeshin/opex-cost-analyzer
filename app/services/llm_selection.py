"""Per-request LLM model selection and catalog for the UI dropdown."""

from __future__ import annotations

import contextvars
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Callable, Generator, Literal, ParamSpec, TypeVar, cast

from app.config import (
    ANTHROPIC_ENABLED,
    ANTHROPIC_MODEL,
    GEMINI_ENABLED,
    GEMINI_MODEL,
    GEMINI_THINKING_MODEL,
    LLM_PROVIDER,
)

__all__ = [
    "LlmModelOption",
    "MODEL_CATALOG",
    "Provider",
    "available_models",
    "default_model_id",
    "get_resolved_llm_model",
    "get_resolved_llm_provider",
    "model_for_provider",
    "llm_model_override_var",
    "llm_selection_context",
    "normalize_model_id",
    "provider_for_model",
    "submit_with_context",
]

Provider = Literal["anthropic", "gemini"]

llm_model_override_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "llm_model_override",
    default=None,
)


@dataclass(frozen=True)
class LlmModelOption:
    id: str
    label: str
    provider: Provider
    description: str = ""


MODEL_CATALOG: tuple[LlmModelOption, ...] = (
    LlmModelOption(
        "claude-sonnet-4-6",
        "Claude Sonnet 4.6",
        "anthropic",
        "Balanced speed and depth",
    ),
    LlmModelOption(
        "claude-sonnet-4-5-20250929",
        "Claude Sonnet 4.5",
        "anthropic",
        "Previous generation Sonnet",
    ),
    LlmModelOption(
        "gemini-2.5-flash",
        "Gemini 2.5 Flash",
        "gemini",
        "Fast responses",
    ),
    LlmModelOption(
        "gemini-2.5-pro",
        "Gemini 2.5 Pro",
        "gemini",
        "Deeper reasoning",
    ),
)


def provider_for_model(model_id: str) -> Provider:
    if model_id.startswith("gemini"):
        return "gemini"
    return "anthropic"


def available_models() -> list[dict[str, str]]:
    """Models the deployment can call (filtered by configured API keys)."""
    out: list[dict[str, str]] = []
    for entry in MODEL_CATALOG:
        if entry.provider == "anthropic" and not ANTHROPIC_ENABLED:
            continue
        if entry.provider == "gemini" and not GEMINI_ENABLED:
            continue
        out.append(
            {
                "id": entry.id,
                "label": entry.label,
                "provider": entry.provider,
                "description": entry.description,
            }
        )
    return out


def default_model_id() -> str:
    """Env-default model for the active provider."""
    models = available_models()
    if not models:
        return ANTHROPIC_MODEL if ANTHROPIC_ENABLED else GEMINI_MODEL
    for row in models:
        if row["provider"] == LLM_PROVIDER:
            return row["id"]
    return models[0]["id"]


def normalize_model_id(model_id: str | None) -> str | None:
    if not model_id or not str(model_id).strip():
        return None
    candidate = str(model_id).strip()
    allowed = {row["id"] for row in available_models()}
    return candidate if candidate in allowed else None


def get_resolved_llm_provider() -> str:
    override = llm_model_override_var.get(None)
    if override:
        return provider_for_model(override)
    return LLM_PROVIDER


def model_for_provider(provider: Provider, *, thinking: bool = False) -> str:
    """Model ID for a specific provider.

    User overrides apply only when they match *provider* so cross-provider fallbacks
    never send a Claude model name to Gemini (or vice versa).
    """
    override = llm_model_override_var.get(None)
    if override and provider_for_model(override) == provider:
        if thinking and provider == "gemini" and override == GEMINI_MODEL:
            return GEMINI_THINKING_MODEL
        return override
    if provider == "gemini":
        return GEMINI_THINKING_MODEL if thinking else GEMINI_MODEL
    return ANTHROPIC_MODEL


def get_resolved_llm_model(*, thinking: bool = False, provider: Provider | None = None) -> str:
    active = provider or get_resolved_llm_provider()  # type: ignore[arg-type]
    if active not in ("anthropic", "gemini"):
        active = "anthropic"
    return model_for_provider(cast(Provider, active), thinking=thinking)


@contextmanager
def llm_selection_context(model_id: str | None) -> Generator[None, None, None]:
    """Set per-request model override for the duration of an OPAR/chat call."""
    token = llm_model_override_var.set(normalize_model_id(model_id))
    try:
        yield
    finally:
        llm_model_override_var.reset(token)


P = ParamSpec("P")
R = TypeVar("R")


def submit_with_context(
    executor: ThreadPoolExecutor,
    fn: Callable[P, R],
    /,
    *args: P.args,
    **kwargs: P.kwargs,
) -> Future[R]:
    """Submit ``fn`` to a thread pool while preserving contextvars (e.g. LLM model override)."""
    ctx = contextvars.copy_context()
    return executor.submit(lambda: ctx.run(fn, *args, **kwargs))
