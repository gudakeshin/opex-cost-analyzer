"""LLM provider abstraction supporting M1 / M2 / M3 modes.

M1 — Deterministic-only: no LLM calls; all functions return None or degraded fallback.
M2 — Regional Managed LLM: Anthropic API (default), or Bedrock-Mumbai / Azure-India.
M3 — On-prem LLM: Ollama endpoint (local Llama / Mistral).

The active mode is set per-session via the ``LLM_MODE`` environment variable or
can be overridden at call time.

Per-skill capability levels (from skills/_capability_matrix.json):
  "full"     — skill output is unaffected by LLM quality
  "partial"  — LLM contributes but deterministic fallback covers >60% of signal
  "degraded" — LLM is the primary signal source; M1 returns skeletal output

When a skill runs degraded, a banner is attached to the output and a
mode_degradation audit event is fired.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

from app.config import ANTHROPIC_API_KEY, ANTHROPIC_ENABLED, GEMINI_ENABLED, LLM_PROVIDER, ROOT_DIR, logger

# ---------------------------------------------------------------------------
# Mode resolution
# ---------------------------------------------------------------------------

_VALID_MODES = {"M1", "M2", "M3"}
_DEFAULT_MODE = "M2"


def get_active_mode() -> str:
    mode = os.getenv("LLM_MODE", _DEFAULT_MODE).upper()
    return mode if mode in _VALID_MODES else _DEFAULT_MODE


# ---------------------------------------------------------------------------
# Capability matrix loader
# ---------------------------------------------------------------------------

_MATRIX_PATH = ROOT_DIR / "skills" / "_capability_matrix.json"
_matrix_cache: Optional[Dict[str, Any]] = None


def _load_matrix() -> Dict[str, Any]:
    global _matrix_cache
    if _matrix_cache is None:
        if _MATRIX_PATH.exists():
            try:
                _matrix_cache = json.loads(_MATRIX_PATH.read_text(encoding="utf-8"))
            except Exception:
                _matrix_cache = {}
        else:
            _matrix_cache = {}
    return _matrix_cache


def skill_capability(skill_name: str, mode: Optional[str] = None) -> str:
    """Return capability level for skill+mode: 'full' | 'partial' | 'degraded'."""
    mode = (mode or get_active_mode()).upper()
    matrix = _load_matrix()
    skills = matrix.get("skills", {})
    row = skills.get(skill_name, {})
    return row.get(mode, "full")  # default full (deterministic skills)


def is_degraded(skill_name: str, mode: Optional[str] = None) -> bool:
    return skill_capability(skill_name, mode) == "degraded"


# ---------------------------------------------------------------------------
# Degradation banner
# ---------------------------------------------------------------------------

_DEGRADED_BANNER_KEY = "_mode_degradation"


def attach_degradation_banner(
    output: Dict[str, Any],
    skill_name: str,
    mode: str,
    capability: str,
) -> Dict[str, Any]:
    """Attach a machine-readable degradation annotation to a skill output."""
    if capability != "full":
        output[_DEGRADED_BANNER_KEY] = {
            "skill": skill_name,
            "mode": mode,
            "capability": capability,
            "message": (
                f"Running in mode {mode}: LLM-driven insights for '{skill_name}' are "
                f"{capability}. Deterministic outputs are available but narrative depth "
                "is reduced."
            ),
        }
    return output


# ---------------------------------------------------------------------------
# Provider calls
# ---------------------------------------------------------------------------

class LLMUnavailableInMode(RuntimeError):
    """Raised when an LLM call is attempted in M1 mode."""


def call_llm(
    system: str,
    user_content: str,
    *,
    max_tokens: int = 512,
    mode: Optional[str] = None,
    skill_name: str = "unknown",
) -> Optional[str]:
    """Call the active LLM provider and return the raw text response.

    Returns None if:
    - mode is M1 (deterministic-only)
    - provider is disabled / unavailable
    Raises nothing — callers should handle None gracefully.
    """
    active_mode = (mode or get_active_mode()).upper()

    if active_mode == "M1":
        logger.info('"llm_provider mode=M1 skill=%s: LLM call suppressed"', skill_name)
        return None

    if active_mode == "M2":
        return _call_m2(system, user_content, max_tokens=max_tokens, skill_name=skill_name)

    if active_mode == "M3":
        return _call_m3(system, user_content, max_tokens=max_tokens, skill_name=skill_name)

    return None


def _call_m2(
    system: str,
    user_content: str,
    *,
    max_tokens: int,
    skill_name: str,
) -> Optional[str]:
    """Call M2 LLM — Gemini when configured, else Anthropic Claude."""
    if os.getenv("PYTEST_CURRENT_TEST"):
        return None

    if LLM_PROVIDER == "gemini" and GEMINI_ENABLED:
        try:
            from app.opar.gemini_client import call_gemini
            return call_gemini(system=system, user_content=user_content, max_tokens=max_tokens)
        except Exception as exc:
            logger.warning('"llm_provider M2 Gemini call failed: %s"', exc)
            return None

    if not ANTHROPIC_ENABLED or not ANTHROPIC_API_KEY:
        return None
    try:
        import anthropic  # type: ignore
    except ImportError:
        logger.warning('"llm_provider: anthropic package not installed"')
        return None
    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_content}],
        )
        return getattr(response.content[0], "text", "").strip() if response.content else None
    except Exception as exc:
        logger.warning('"llm_provider M2 call failed: %s"', exc)
        return None


def get_tool_loop_transport():
    """Return the configured tool-loop transport for M2 agent paths."""
    from app.config import ANTHROPIC_ENABLED, GEMINI_ENABLED, LLM_PROVIDER

    if os.getenv("PYTEST_CURRENT_TEST"):
        return None
    if LLM_PROVIDER == "gemini" and GEMINI_ENABLED:
        from app.opar.gemini_client import GeminiToolTransport

        return GeminiToolTransport()
    if ANTHROPIC_ENABLED:
        from app.opar.claude_client import ClaudeToolTransport

        return ClaudeToolTransport()
    return None


def call_llm_with_tools(
    system: str,
    messages: list[dict[str, Any]],
    tools: list[Any],
    dispatch: Any,
    *,
    mode: Optional[str] = None,
    thinking: bool = True,
) -> Optional[Any]:
    """Run an agent tool loop via the active provider. Returns None in M1/pytest."""
    active_mode = (mode or get_active_mode()).upper()
    if active_mode == "M1" or os.getenv("PYTEST_CURRENT_TEST"):
        return None
    transport = get_tool_loop_transport()
    if transport is None:
        return None
    from app.opar.agent_runtime import run_tool_loop

    return run_tool_loop(
        system=system,
        messages=messages,
        tools=tools,
        dispatch=dispatch,
        transport=transport,
        thinking=thinking,
    )


def _call_m3(
    system: str,
    user_content: str,
    *,
    max_tokens: int,
    skill_name: str,
) -> Optional[str]:
    """Call on-prem LLM via Ollama (M3)."""
    ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
    model = os.getenv("OLLAMA_MODEL", "llama3")
    if os.getenv("PYTEST_CURRENT_TEST"):
        return None
    try:
        import urllib.request
        import json as _json

        payload = _json.dumps({
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
            "stream": False,
            "options": {"num_predict": max_tokens},
        }).encode()
        req = urllib.request.Request(
            f"{ollama_url}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = _json.loads(resp.read().decode())
            return data.get("message", {}).get("content", "").strip() or None
    except Exception as exc:
        logger.warning('"llm_provider M3 Ollama call failed: %s"', exc)
        return None


# ---------------------------------------------------------------------------
# Mode summary (for frontend banners)
# ---------------------------------------------------------------------------

def mode_summary(mode: Optional[str] = None) -> Dict[str, Any]:
    """Return a dict describing current mode and which skills are degraded."""
    active = (mode or get_active_mode()).upper()
    matrix = _load_matrix()
    skills = matrix.get("skills", {})
    degraded_skills = [s for s, caps in skills.items() if caps.get(active) == "degraded"]
    partial_skills = [s for s, caps in skills.items() if caps.get(active) == "partial"]
    mode_meta = matrix.get("modes", {}).get(active, {})
    return {
        "mode": active,
        "label": mode_meta.get("label", active),
        "llm_available": mode_meta.get("llm_available", active != "M1"),
        "degraded_skills": degraded_skills,
        "partial_skills": partial_skills,
        "degradation_banner": (
            f"Running in mode {active}. "
            f"{len(degraded_skills)} skill(s) return reduced-quality output: "
            f"{', '.join(degraded_skills[:4]) or 'none'}."
            if degraded_skills
            else None
        ),
    }
