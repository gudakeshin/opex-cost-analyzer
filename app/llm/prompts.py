"""Central prompt registry.

Every major LLM prompt used in the platform is registered here with:
  - name        — stable identifier used in provenance records
  - version     — bump when the prompt text changes materially
  - model_hint  — model family this prompt is tuned for ("claude", "gemini", "any")
  - text        — the actual prompt string (imported from its owning module)

Usage
-----
    from app.llm.prompts import prompt_version, get_prompt

    version = prompt_version("intent_classify")   # "1.3"
    spec    = get_prompt("agent_system")           # PromptSpec
    text    = spec.text

Versioning convention
---------------------
  <major>.<minor>
  Major: breaking change to output schema or intent taxonomy
  Minor: wording clarification, added examples, no structural change

The version is persisted alongside every LLM-derived output via
app/opar/reflect_persistence.py::record_advisory_provenance so a client
recommendation can always be traced to the exact prompt that produced it.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PromptSpec:
    name: str
    version: str
    model_hint: str  # "claude" | "gemini" | "any"
    text: str


def _load_registry() -> dict[str, PromptSpec]:
    """Lazy-import each prompt from its owning module and register it."""
    specs: dict[str, PromptSpec] = {}

    # Intent classifier — LLM-first routing over ~19 intent taxonomy.
    # History: 1.0 (keyword-only), 1.1 (LLM-first + capabilities), 1.2 (savings_plan added),
    #          1.3 (query_capabilities output field).
    try:
        from app.opar.claude_client import INTENT_CLASSIFY_PROMPT
        specs["intent_classify"] = PromptSpec(
            name="intent_classify",
            version="1.3",
            model_hint="claude",
            text=INTENT_CLASSIFY_PROMPT,
        )
    except ImportError:
        pass

    # Analysis synthesis — executive FP&A narrative from validated skill outputs.
    # History: 1.0 (initial), 1.1 (INR/₹Cr framing), 1.2 (multi-currency).
    try:
        from app.opar.claude_client import ANALYSIS_SYNTHESIS_SYSTEM_PROMPT
        specs["analysis_synthesis"] = PromptSpec(
            name="analysis_synthesis",
            version="1.2",
            model_hint="claude",
            text=ANALYSIS_SYNTHESIS_SYSTEM_PROMPT,
        )
    except ImportError:
        pass

    # Chat response — provider-agnostic FP&A Q&A synthesis.
    # History: 1.0 (Gemini-only), 1.1 (Claude + Gemini), 1.2 (full spend_data context).
    try:
        from app.opar.gemini_client import CHAT_RESPONSE_SYSTEM_PROMPT
        specs["chat_response"] = PromptSpec(
            name="chat_response",
            version="1.2",
            model_hint="any",
            text=CHAT_RESPONSE_SYSTEM_PROMPT,
        )
    except ImportError:
        pass

    # Agent system — agentic tool-loop investigator (M2/M3 path).
    # History: 1.0 (initial), 1.1 (evidence-first mandate), 1.2 (find_skills + provenance rules).
    try:
        from app.opar.agent_controller import _AGENT_SYSTEM
        specs["agent_system"] = PromptSpec(
            name="agent_system",
            version="1.2",
            model_hint="claude",
            text=_AGENT_SYSTEM,
        )
    except ImportError:
        pass

    # SME critique — Deloitte-framing evidence maturity reviewer.
    # History: 1.0 (initial), 1.1 (portfolio_probes output field).
    try:
        from app.opar.sme_intelligence import _SME_SYSTEM
        specs["sme_system"] = PromptSpec(
            name="sme_system",
            version="1.1",
            model_hint="claude",
            text=_SME_SYSTEM,
        )
    except ImportError:
        pass

    # Probe intelligence — HITL assumption probe generator.
    # History: 1.0 (initial).
    try:
        from app.opar.probe_intelligence import _PROBE_SYSTEM
        specs["probe_system"] = PromptSpec(
            name="probe_system",
            version="1.0",
            model_hint="claude",
            text=_PROBE_SYSTEM,
        )
    except ImportError:
        pass

    return specs


_REGISTRY: dict[str, PromptSpec] | None = None


def _get_registry() -> dict[str, PromptSpec]:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = _load_registry()
    return _REGISTRY


def get_prompt(name: str) -> PromptSpec | None:
    """Return the PromptSpec for *name*, or None if not registered."""
    return _get_registry().get(name)


def prompt_version(name: str) -> str:
    """Return the version string for *name*, or 'unknown' if not registered."""
    spec = get_prompt(name)
    return spec.version if spec else "unknown"


def registered_prompts() -> list[str]:
    """Return the list of registered prompt names."""
    return sorted(_get_registry().keys())


def prompt_version_map() -> dict[str, str]:
    """Return {name: version} for all registered prompts — for provenance records."""
    return {name: spec.version for name, spec in _get_registry().items()}
