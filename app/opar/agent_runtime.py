"""Provider-agnostic LLM tool-use loop for the agent controller.

Primary transport: Gemini function-calling (google-genai) with thinking budget.
Alternate transport: Anthropic tool_use → tool_result loop.

The transport is injectable so unit tests can replay scripted call sequences
without network access.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Protocol

from app.config import AGENT_MAX_TOOL_ITERATIONS, AGENT_TOOL_TIMEOUT_SECONDS, logger


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class ToolDefinition:
    name: str
    description: str
    input_schema: Dict[str, Any]

    def to_anthropic(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


@dataclass
class ToolLoopStep:
    iteration: int
    tool_calls: List[ToolCall] = field(default_factory=list)
    tool_results: List[Dict[str, Any]] = field(default_factory=list)
    thinking_text: str | None = None


@dataclass
class ToolLoopResult:
    final_text: str
    steps: List[ToolLoopStep] = field(default_factory=list)
    thinking_text: str | None = None
    iterations: int = 0
    stopped_reason: str = "complete"


ToolDispatchFn = Callable[[ToolCall], Any]


class ToolLoopTransport(Protocol):
    """Single LLM turn: messages + tool schemas → text and/or tool calls."""

    def generate(
        self,
        *,
        system: str,
        messages: List[Dict[str, Any]],
        tools: List[ToolDefinition],
        thinking: bool = True,
    ) -> tuple[str | None, List[ToolCall], str | None]: ...


def _compact_result(value: Any, max_chars: int = 8000) -> Any:
    if isinstance(value, str) and len(value) > max_chars:
        return value[:max_chars] + f"\n…[truncated {len(value) - max_chars} chars]"
    if isinstance(value, dict):
        text = json.dumps(value, ensure_ascii=False, default=str)
        if len(text) > max_chars:
            return {"summary": text[:max_chars], "_truncated": True}
    return value


def run_tool_loop(
    *,
    system: str,
    messages: List[Dict[str, Any]],
    tools: List[ToolDefinition],
    dispatch: ToolDispatchFn,
    transport: ToolLoopTransport,
    thinking: bool = True,
    max_iters: int | None = None,
    tool_timeout_s: float | None = None,
) -> ToolLoopResult:
    """Run think → tool call → observe → repeat until the model stops calling tools."""
    max_iterations = max_iters if max_iters is not None else AGENT_MAX_TOOL_ITERATIONS
    timeout = tool_timeout_s if tool_timeout_s is not None else AGENT_TOOL_TIMEOUT_SECONDS
    convo = list(messages)
    steps: List[ToolLoopStep] = []
    all_thinking: list[str] = []
    tool_cache: Dict[str, Any] = {}

    for iteration in range(max_iterations):
        text, tool_calls, thinking_text = transport.generate(
            system=system,
            messages=convo,
            tools=tools,
            thinking=thinking,
        )
        if thinking_text:
            all_thinking.append(thinking_text)

        if not tool_calls:
            return ToolLoopResult(
                final_text=(text or "").strip(),
                steps=steps,
                thinking_text="\n".join(all_thinking) if all_thinking else None,
                iterations=iteration + 1,
                stopped_reason="no_tool_calls",
            )

        step = ToolLoopStep(iteration=iteration, tool_calls=tool_calls, thinking_text=thinking_text)
        result_blocks: List[Dict[str, Any]] = []

        for call in tool_calls:
            cache_key = f"{call.name}:{json.dumps(call.arguments, sort_keys=True, default=str)}"
            if cache_key in tool_cache:
                payload = tool_cache[cache_key]
            else:
                t0 = time.perf_counter()
                try:
                    raw = _dispatch_with_timeout(dispatch, call, timeout)
                    payload = {"ok": True, "result": _compact_result(raw)}
                except Exception as exc:
                    logger.warning('"agent_tool_error tool=%s err=%s"', call.name, exc)
                    payload = {"ok": False, "error": str(exc)[:500]}
                payload["duration_ms"] = round((time.perf_counter() - t0) * 1000, 1)
                tool_cache[cache_key] = payload

            step.tool_results.append({"tool_call_id": call.id, "name": call.name, **payload})
            result_blocks.append(
                {
                    "type": "tool_result",
                    "tool_use_id": call.id,
                    "tool_call_id": call.id,
                    "name": call.name,
                    "content": json.dumps(payload, ensure_ascii=False, default=str),
                }
            )

        steps.append(step)
        convo.append({"role": "assistant", "content": text or "", "tool_calls": tool_calls})
        convo.append({"role": "user", "content": result_blocks})

    return ToolLoopResult(
        final_text=(text or "").strip(),
        steps=steps,
        thinking_text="\n".join(all_thinking) if all_thinking else None,
        iterations=max_iterations,
        stopped_reason="max_iterations",
    )


def _dispatch_with_timeout(dispatch: ToolDispatchFn, call: ToolCall, timeout_s: float) -> Any:
    if timeout_s <= 0:
        return dispatch(call)
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(dispatch, call)
        try:
            return future.result(timeout=timeout_s)
        except FuturesTimeoutError:
            future.cancel()
            raise TimeoutError(f"Tool {call.name} exceeded {timeout_s}s timeout")


class ScriptedTransport:
    """Test transport: replay scripted (text, tool_calls) sequences."""

    def __init__(self, script: List[tuple[str | None, List[ToolCall]]]) -> None:
        self._script = list(script)
        self._idx = 0

    def generate(
        self,
        *,
        system: str,
        messages: List[Dict[str, Any]],
        tools: List[ToolDefinition],
        thinking: bool = True,
    ) -> tuple[str | None, List[ToolCall], str | None]:
        if self._idx >= len(self._script):
            return ("Done.", [], None)
        text, calls = self._script[self._idx]
        self._idx += 1
        return text, calls, None


def make_tool_call(name: str, arguments: Dict[str, Any], call_id: str | None = None) -> ToolCall:
    return ToolCall(id=call_id or str(uuid.uuid4()), name=name, arguments=arguments)


def agent_loop_available() -> bool:
    """True when the agentic path may run (M2/M3, not pytest, controller enabled)."""
    if os.getenv("PYTEST_CURRENT_TEST"):
        return False
    from app.config import AGENT_CONTROLLER_ENABLED
    from app.opar.llm_provider import get_active_mode

    if not AGENT_CONTROLLER_ENABLED:
        return False
    return get_active_mode() in ("M2", "M3")
