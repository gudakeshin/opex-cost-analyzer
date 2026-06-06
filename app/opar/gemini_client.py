"""Gemini LLM transports — plain generation and function-calling for agent loop."""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Any, Dict, List, Tuple

from app.config import (
    AGENT_THINKING_BUDGET,
    GEMINI_API_KEY,
    GEMINI_ENABLED,
    GEMINI_MODEL,
    GEMINI_THINKING_MODEL,
    GEMINI_TOOL_MODEL,
    logger,
)
from app.opar.agent_runtime import ToolCall, ToolDefinition, ToolLoopTransport

CHAT_RESPONSE_SYSTEM_PROMPT = """You are an FP&A copilot embedded in an OpEx cost intelligence platform.
Answer the user's question using ONLY the JSON context provided. Never invent numbers, suppliers, or categories.

Rules:
- Match the user's exact analytical dimension (supplier, geo, category, payment terms, etc.).
- If they ask for a supplier breakdown, list ranked suppliers with spend amounts and % of category — never substitute a category portfolio breakdown.
- If they ask for geo/region breakdown, use top_geos data.
- Use the reporting currency from session_context when formatting money (₹ Cr for INR).
- Write concise markdown: short intro, then a ranked list or table, then 1-2 insight bullets if warranted.
- If data for the requested dimension is missing, say so clearly and suggest what upload would help.
- Do not mention JSON, prompts, or internal system mechanics.
"""


def _genai_client():
    if os.getenv("PYTEST_CURRENT_TEST"):
        raise RuntimeError("Gemini calls disabled during pytest runs")
    if not GEMINI_ENABLED or not GEMINI_API_KEY:
        raise RuntimeError("Gemini not configured — set GEMINI_API_KEY")
    try:
        from google import genai  # type: ignore
    except ImportError:
        raise RuntimeError("google-genai package not installed. pip install google-genai")
    return genai.Client(api_key=GEMINI_API_KEY)


def call_gemini(
    system: str,
    user_content: str,
    max_tokens: int = 512,
    model: str | None = None,
) -> str:
    """Call Gemini via google-genai SDK and return response text."""
    from google.genai import types  # type: ignore

    active_model = model or GEMINI_MODEL
    client = _genai_client()
    response = client.models.generate_content(
        model=active_model,
        contents=user_content,
        config=types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=max_tokens,
        ),
    )
    text = getattr(response, "text", None) or ""
    logger.debug('"gemini call ok","model":"%s","tokens":%d}', active_model, max_tokens)
    return text.strip()


def call_gemini_with_thinking(
    system: str,
    user_content: str,
    max_tokens: int = 1800,
    model: str | None = None,
    thinking_budget: int | None = None,
) -> Tuple[str, str | None]:
    """Call a Gemini 2.5 reasoning model with thinking budget enabled."""
    from google.genai import types  # type: ignore

    active_model = model or GEMINI_THINKING_MODEL
    budget = thinking_budget if thinking_budget is not None else AGENT_THINKING_BUDGET
    client = _genai_client()
    response = client.models.generate_content(
        model=active_model,
        contents=user_content,
        config=types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=max_tokens,
            thinking_config=types.ThinkingConfig(thinking_budget=budget),
        ),
    )
    thinking_parts: list[str] = []
    candidate = response.candidates[0] if getattr(response, "candidates", None) else None
    if candidate and getattr(candidate, "content", None):
        for part in candidate.content.parts:
            if getattr(part, "thought", False) and getattr(part, "text", None):
                thinking_parts.append(part.text)
    text = getattr(response, "text", None) or ""
    return text.strip(), ("\n".join(thinking_parts) if thinking_parts else None)


def call_judge_llm(system: str, user_content: str, max_tokens: int = 512) -> str:
    return call_gemini(system=system, user_content=user_content, max_tokens=max_tokens)


class GeminiToolTransport(ToolLoopTransport):
    """Gemini function-calling transport for ``run_tool_loop``."""

    def __init__(
        self,
        *,
        model: str | None = None,
        thinking_budget: int | None = None,
        max_output_tokens: int = 4096,
    ) -> None:
        self.model = model or GEMINI_TOOL_MODEL
        self.thinking_budget = thinking_budget if thinking_budget is not None else AGENT_THINKING_BUDGET
        self.max_output_tokens = max_output_tokens

    def generate(
        self,
        *,
        system: str,
        messages: List[Dict[str, Any]],
        tools: List[ToolDefinition],
        thinking: bool = True,
    ) -> tuple[str | None, List[ToolCall], str | None]:
        from google.genai import types  # type: ignore

        client = _genai_client()
        declarations = [
            types.FunctionDeclaration(
                name=t.name,
                description=t.description,
                parameters=t.input_schema,
            )
            for t in tools
        ]
        gemini_tools = [types.Tool(function_declarations=declarations)] if declarations else None

        contents = _messages_to_gemini_contents(messages)
        config_kwargs: Dict[str, Any] = {
            "system_instruction": system,
            "max_output_tokens": self.max_output_tokens,
        }
        if gemini_tools:
            config_kwargs["tools"] = gemini_tools
        if thinking:
            config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=self.thinking_budget)

        response = client.models.generate_content(
            model=self.model,
            contents=contents,
            config=types.GenerateContentConfig(**config_kwargs),
        )

        text_parts: list[str] = []
        thinking_parts: list[str] = []
        tool_calls: List[ToolCall] = []

        text_fallback = getattr(response, "text", None) or ""
        candidates = getattr(response, "candidates", None) or []
        candidate = candidates[0] if candidates else None
        parts = candidate.content.parts if candidate and getattr(candidate, "content", None) else []
        for part in parts:
            if getattr(part, "thought", False) and getattr(part, "text", None):
                thinking_parts.append(part.text)
            elif getattr(part, "text", None):
                text_parts.append(part.text)
            fc = getattr(part, "function_call", None)
            if fc:
                args = dict(getattr(fc, "args", None) or {})
                tool_calls.append(
                    ToolCall(
                        id=getattr(fc, "id", None) or f"{fc.name}-{len(tool_calls)}",
                        name=str(fc.name),
                        arguments=args,
                    )
                )

        return (
            "\n".join(text_parts).strip() or text_fallback.strip() or None,
            tool_calls,
            "\n".join(thinking_parts) if thinking_parts else None,
        )


def _messages_to_gemini_contents(messages: List[Dict[str, Any]]) -> list:
    """Convert generic message list to google-genai Content objects."""
    from google.genai import types  # type: ignore

    contents: list = []
    for msg in messages:
        role = msg.get("role", "user")
        gemini_role = "model" if role == "assistant" else "user"
        parts: list = []

        content = msg.get("content")
        if isinstance(content, str) and content:
            parts.append(types.Part(text=content))
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    parts.append(
                        types.Part(
                            function_response=types.FunctionResponse(
                                name=block.get("name", ""),
                                response={"result": block.get("content", "")},
                            )
                        )
                    )
                elif isinstance(block, str):
                    parts.append(types.Part(text=block))

        tool_calls = msg.get("tool_calls") or []
        for call in tool_calls:
            if isinstance(call, ToolCall):
                parts.append(
                    types.Part(
                        function_call=types.FunctionCall(
                            name=call.name,
                            args=call.arguments,
                        )
                    )
                )

        if parts:
            contents.append(types.Content(role=gemini_role, parts=parts))
    return contents


def synthesize_chat_response_gemini(
    context: Dict[str, Any],
    *,
    thinking_enabled: bool = False,
) -> Tuple[str | None, str | None]:
    if not GEMINI_ENABLED:
        return None, None
    user_prompt = (
        "Answer the user's question from this context. Return markdown only.\n"
        f"{json.dumps(context, ensure_ascii=False)}"
    )
    timeout_s = 35 if thinking_enabled else 8
    max_tokens = 2048 if thinking_enabled else 1024
    executor = ThreadPoolExecutor(max_workers=1)
    if thinking_enabled:
        future = executor.submit(
            call_gemini_with_thinking,
            CHAT_RESPONSE_SYSTEM_PROMPT,
            user_prompt,
            max_tokens,
        )
    else:
        future = executor.submit(
            call_gemini,
            CHAT_RESPONSE_SYSTEM_PROMPT,
            user_prompt,
            max_tokens,
        )
    try:
        result = future.result(timeout=timeout_s)
        if thinking_enabled:
            text, thinking = result
            return (text or "").strip() or None, thinking
        return (result or "").strip() or None, None
    except FuturesTimeoutError:
        future.cancel()
        executor.shutdown(wait=False, cancel_futures=True)
        logger.warning('"synthesize_chat_response_gemini timeout after %ss"', timeout_s)
        return None, None
    except Exception as exc:
        logger.warning('"synthesize_chat_response_gemini failed error=%s"', exc)
        return None, None
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def synthesize_analysis_gemini(
    user_message: str,
    manifest: Dict[str, Any],
    model_manifest: Dict[str, Any] | None,
    skill_outputs: Dict[str, Any],
    docs_text: List[str],
    transaction_examples: Dict[str, List[Dict[str, Any]]] | None = None,
    strict_mode: bool = False,
    thinking_enabled: bool = False,
    thinking_budget_tokens: int = 8000,
    deep_research_summary: str | None = None,
    retrieved_context: List[str] | None = None,
) -> Tuple[Dict[str, Any] | None, str | None]:
    """Synthesize executive recommendations via Gemini (mirrors synthesize_analysis_claude)."""
    if not GEMINI_ENABLED:
        return None, None

    from app.opar.claude_client import (
        ANALYSIS_SYNTHESIS_SYSTEM_PROMPT,
        _extract_json,
        _slim_skill_outputs,
        _slim_sme_critique,
        _slim_transaction_examples,
        _truncate_doc_chunks,
    )

    payload = {
        "user_message": user_message,
        "session_context": {
            "company_name": manifest.get("company_name"),
            "industry": manifest.get("industry"),
            "annual_revenue": manifest.get("annual_revenue"),
            "currency": manifest.get("currency"),
        },
        "model_manifest": model_manifest or {},
        "skill_outputs": _slim_skill_outputs(skill_outputs),
        "document_chunks": retrieved_context if retrieved_context else _truncate_doc_chunks(docs_text, max_chunks=2),
        "transaction_examples_by_category": _slim_transaction_examples(transaction_examples),
    }
    if deep_research_summary:
        payload["deep_research_context"] = deep_research_summary
    sme_data = _slim_sme_critique(skill_outputs.get("sme-critique"))
    if sme_data:
        payload["sme_critique_data"] = sme_data

    strict_hint = ""
    if strict_mode:
        strict_hint = (
            "\nSTRICT QUALITY MODE:\n"
            "- At least 3 business_levers.\n"
            "- Each business lever must include specific operational/commercial changes.\n"
            "- Include at least 2 executive_callouts with concrete numbers.\n"
            "- Include at least 3 quick_wins_from_data.\n"
            "- If the user question targets a specific category: `category_focus_section` MUST be "
            "a decision-memo-quality analysis of at least 250 words. Write 3-5 paragraphs. "
            "Name the exact suppliers and amounts from the data. Do NOT write a single sentence. "
            "Explain the causal mechanism, not just the gap. "
            "Make it self-contained — a CFO must be able to act on it without reading anything else.\n"
        )
    user_prompt = (
        "Synthesize recommendations from this JSON context:\n"
        f"{json.dumps(payload, ensure_ascii=False)}\n"
        f"{strict_hint}"
    )
    timeout_s = 35 if thinking_enabled else 8
    max_tokens = 1800
    executor = ThreadPoolExecutor(max_workers=1)
    if thinking_enabled:
        future = executor.submit(
            call_gemini_with_thinking,
            ANALYSIS_SYNTHESIS_SYSTEM_PROMPT,
            user_prompt,
            max_tokens,
            thinking_budget=thinking_budget_tokens,
        )
    else:
        future = executor.submit(
            call_gemini,
            ANALYSIS_SYNTHESIS_SYSTEM_PROMPT,
            user_prompt,
            max_tokens,
        )
    try:
        result = future.result(timeout=timeout_s)
        if thinking_enabled:
            raw, thinking_text = result
        else:
            raw, thinking_text = result, None
    except FuturesTimeoutError:
        future.cancel()
        executor.shutdown(wait=False, cancel_futures=True)
        logger.warning('"synthesize_analysis_gemini timeout after %ss"', timeout_s)
        return None, None
    except Exception as exc:
        logger.warning('"synthesize_analysis_gemini failed error=%s"', exc)
        return None, None
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    try:
        data = _extract_json(raw)
    except Exception:
        return None, thinking_text
    if isinstance(data, dict):
        return data, thinking_text
    return None, thinking_text

