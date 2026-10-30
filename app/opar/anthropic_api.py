"""Shared Anthropic API helpers — adaptive thinking, structured JSON outputs."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Literal

from app.config import ANTHROPIC_API_KEY, ANTHROPIC_ENABLED
from app.metrics import record_llm_usage
from app.services.llm_selection import get_resolved_llm_model

Effort = Literal["low", "medium", "high", "max"]

CACHE_CONTROL_EPHEMERAL: dict[str, str] = {"type": "ephemeral"}

# Model families without adaptive thinking — these still use thinking.budget_tokens.
_LEGACY_THINKING_MODEL_PREFIXES: tuple[str, ...] = (
    "claude-haiku-4-5",
    "claude-sonnet-4-5",
    "claude-3",
)

# Model families that reject output_config.effort (Haiku 4.5, Sonnet 4.5, 3.x).
_EFFORT_UNSUPPORTED_MODEL_PREFIXES: tuple[str, ...] = _LEGACY_THINKING_MODEL_PREFIXES


def _uses_legacy_thinking(model: str) -> bool:
    return model.startswith(_LEGACY_THINKING_MODEL_PREFIXES)


def _supports_effort(model: str) -> bool:
    return not model.startswith(_EFFORT_UNSUPPORTED_MODEL_PREFIXES)


def anthropic_usage_fields(usage: Any) -> tuple[int, int, int, int]:
    """Return (input, output, cache_read, cache_creation) from an Anthropic usage object."""
    if usage is None:
        return 0, 0, 0, 0
    return (
        int(getattr(usage, "input_tokens", 0) or 0),
        int(getattr(usage, "output_tokens", 0) or 0),
        int(getattr(usage, "cache_read_input_tokens", 0) or 0),
        int(getattr(usage, "cache_creation_input_tokens", 0) or 0),
    )


def record_anthropic_usage(usage: Any, model: str) -> None:
    """Record Anthropic usage including prompt-cache token breakdown."""
    inp, out, cache_read, cache_create = anthropic_usage_fields(usage)
    record_llm_usage(
        "anthropic",
        model,
        inp,
        out,
        cache_read_input_tokens=cache_read,
        cache_creation_input_tokens=cache_create,
    )


def cached_system_blocks(system: str) -> list[dict[str, Any]]:
    """System prompt as a cacheable prefix block."""
    return [
        {
            "type": "text",
            "text": system,
            "cache_control": CACHE_CONTROL_EPHEMERAL,
        }
    ]


def cached_text_block(text: str, *, cache: bool = False) -> dict[str, Any]:
    block: dict[str, Any] = {"type": "text", "text": text}
    if cache:
        block["cache_control"] = CACHE_CONTROL_EPHEMERAL
    return block


def build_chat_user_content_blocks(cached_context_json: str, turn_context_json: str) -> list[dict[str, Any]]:
    """User message blocks: stable session prefix (cached) + per-turn suffix."""
    return [
        cached_text_block(
            f"Analysis context (stable for this session):\n{cached_context_json}",
            cache=True,
        ),
        cached_text_block(
            "Answer the user's question using the analysis context above. Return markdown only.\n\n"
            f"Current turn:\n{turn_context_json}",
        ),
    ]


def apply_tool_cache_breakpoint(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Mark the last tool definition as a cache breakpoint."""
    if not tools:
        return tools
    out = list(tools)
    out[-1] = {**out[-1], "cache_control": CACHE_CONTROL_EPHEMERAL}
    return out


def thinking_effort_from_budget(budget_tokens: int) -> Effort:
    if budget_tokens >= 7000:
        return "high"
    if budget_tokens >= 4500:
        return "medium"
    return "low"


def anthropic_thinking_kwargs(*, model: str, budget_tokens: int = 8000) -> dict[str, Any]:
    """Build thinking config for messages.create / tool transport."""
    if _uses_legacy_thinking(model):
        return {"thinking": {"type": "enabled", "budget_tokens": budget_tokens}}
    return {"thinking": {"type": "adaptive"}}


def anthropic_output_config(
    *,
    model: str,
    schema: Dict[str, Any] | None = None,
    budget_tokens: int = 8000,
) -> dict[str, Any]:
    """Build output_config with optional JSON schema and effort from budget.

    effort is omitted on models that reject it (Haiku 4.5, Sonnet 4.5, 3.x).
    """
    cfg: dict[str, Any] = {}
    if _supports_effort(model):
        cfg["effort"] = thinking_effort_from_budget(budget_tokens)
    if schema is not None:
        cfg["format"] = {"type": "json_schema", "schema": schema}
    if not cfg:
        return {}
    return {"output_config": cfg}


def anthropic_max_tokens_for_thinking(
    max_tokens: int,
    *,
    model: str,
    budget_tokens: int = 8000,
    thinking: bool = True,
) -> int:
    """Legacy models need max_tokens > thinking budget; adaptive models do not."""
    if thinking and _uses_legacy_thinking(model):
        return max(max_tokens, budget_tokens + 2048)
    return max_tokens


def call_anthropic_structured_json(
    system: str,
    user_content: str,
    schema: Dict[str, Any],
    *,
    max_tokens: int = 512,
    model: str | None = None,
    thinking: bool = False,
    budget_tokens: int = 8000,
    http_timeout_s: float | None = None,
) -> Dict[str, Any] | List[Any] | None:
    """Call Anthropic with JSON-schema structured output; returns parsed object or None."""
    if os.getenv("PYTEST_CURRENT_TEST"):
        raise RuntimeError("Claude calls disabled during pytest runs")
    if not ANTHROPIC_ENABLED or not ANTHROPIC_API_KEY:
        raise RuntimeError("Anthropic not configured")

    active_model = model or get_resolved_llm_model(provider="anthropic")
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("anthropic package not installed")

    if http_timeout_s is None:
        from app.config import llm_synthesis_timeout_seconds

        http_timeout_s = float(llm_synthesis_timeout_seconds()) + 15.0
    timeout = http_timeout_s
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, timeout=timeout)

    kwargs: dict[str, Any] = {
        "model": active_model,
        "max_tokens": anthropic_max_tokens_for_thinking(
            max_tokens, model=active_model, budget_tokens=budget_tokens, thinking=thinking
        ),
        "system": system,
        "messages": [{"role": "user", "content": user_content}],
        **anthropic_output_config(model=active_model, schema=schema, budget_tokens=budget_tokens),
    }
    if thinking:
        kwargs.update(anthropic_thinking_kwargs(model=active_model, budget_tokens=budget_tokens))

    response = client.messages.create(**kwargs)
    record_anthropic_usage(getattr(response, "usage", None), active_model)

    text = ""
    for block in response.content:
        if getattr(block, "type", None) == "text":
            text = getattr(block, "text", "") or ""
            break
    if not text.strip():
        return None
    parsed = json.loads(text)
    if isinstance(parsed, (dict, list)):
        return parsed
    return None
