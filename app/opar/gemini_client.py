"""Gemini LLM client — drop-in provider alternative to Claude.

Reads GEMINI_API_KEY and GEMINI_MODEL from config. Call call_gemini() anywhere
that previously called _call_claude() or the Anthropic SDK directly.
"""
from __future__ import annotations

import os
from typing import Tuple

from app.config import GEMINI_API_KEY, GEMINI_ENABLED, GEMINI_MODEL, logger


def call_gemini(
    system: str,
    user_content: str,
    max_tokens: int = 512,
    model: str | None = None,
) -> str:
    """Call Gemini and return response text. Raises RuntimeError on failure."""
    if os.getenv("PYTEST_CURRENT_TEST"):
        raise RuntimeError("Gemini calls disabled during pytest runs")
    if not GEMINI_ENABLED or not GEMINI_API_KEY:
        raise RuntimeError("Gemini not configured — set GEMINI_API_KEY")
    try:
        import google.generativeai as genai  # type: ignore
    except ImportError:
        raise RuntimeError("google-generativeai package not installed. pip install google-generativeai")

    active_model = model or GEMINI_MODEL
    genai.configure(api_key=GEMINI_API_KEY)
    model_obj = genai.GenerativeModel(
        model_name=active_model,
        system_instruction=system,
    )
    response = model_obj.generate_content(
        user_content,
        generation_config={"max_output_tokens": max_tokens},
    )
    text = response.text or ""
    logger.debug('"gemini call ok","model":"%s","tokens":%d}', active_model, max_tokens)
    return text.strip()


def call_gemini_with_thinking(
    system: str,
    user_content: str,
    max_tokens: int = 1800,
) -> Tuple[str, None]:
    """Gemini Flash-Lite has no extended thinking — delegates to call_gemini().

    Returns (response_text, None) to match _call_claude_with_thinking() signature.
    """
    text = call_gemini(system=system, user_content=user_content, max_tokens=max_tokens * 2)
    return text, None


def call_judge_llm(system: str, user_content: str, max_tokens: int = 512) -> str:
    """Eval-judge entry point — identical contract to call_gemini()."""
    return call_gemini(system=system, user_content=user_content, max_tokens=max_tokens)
