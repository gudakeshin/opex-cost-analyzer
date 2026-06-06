"""Apply user clarification answers and derive waiver flags for Observe gate."""

from __future__ import annotations

import json
import re
from typing import Any

from app.config import UPLOAD_DIR
from app.memory import MemoryStore
from app.opar.hitl.clarification_tool import ClarificationAnswer
from app.storage import read_json, write_json

_memory = MemoryStore()

_WAIVER_OPTION_PATTERNS = [
    re.compile(r"proxy|indicative|limited data|lower confidence|proceed with caveats", re.I),
    re.compile(r"industry median|benchmark defaults|use defaults", re.I),
]

_WAIVER_FREE_TEXT_PATTERNS = [
    re.compile(r"\bignore\b.*\b(variance|subsidiary|entity|segment)\b", re.I),
    re.compile(r"\bexclude\b.*\b(subsidiary|entity|segment|division)\b", re.I),
    re.compile(r"\bproceed\b.*\b(indicative|proxy|limited)\b", re.I),
    re.compile(r"\bwonder cement\b", re.I),
]

_DEFER_OPTION_PATTERNS = [
    re.compile(r"upload|attach|provide.*file|spend file", re.I),
    re.compile(r"session settings|enter.*revenue|select industry|settings above", re.I),
    re.compile(r"defer|wait until|until data", re.I),
]


def option_implies_deferral(selected_option: str | None) -> bool:
    if not selected_option:
        return False
    return any(p.search(selected_option) for p in _DEFER_OPTION_PATTERNS)


def _option_implies_waiver(selected_option: str | None) -> bool:
    if not selected_option:
        return False
    return any(p.search(selected_option) for p in _WAIVER_OPTION_PATTERNS)


def _free_text_implies_waiver(free_text: str | None) -> bool:
    if not free_text:
        return False
    return any(p.search(free_text) for p in _WAIVER_FREE_TEXT_PATTERNS)


def should_waive_spend_requirement(answer: ClarificationAnswer) -> bool:
    """True when user explicitly chooses to proceed with caveats or business override."""
    if _option_implies_waiver(answer.selected_option):
        return True
    if answer.free_text and _free_text_implies_waiver(answer.free_text):
        return True
    if answer.free_text and not answer.selected_option:
        # Free-text-only response treated as business override to proceed.
        return True
    return False


def apply_clarification_answer(
    session_id: str,
    answer: ClarificationAnswer,
) -> dict[str, Any]:
    """Persist user answer to manifest and session memory; return observe overrides."""
    manifest_path = UPLOAD_DIR / session_id / "manifest.json"
    manifest = read_json(manifest_path, {"files": [], "industry": "", "annual_revenue": 0.0})

    waive = should_waive_spend_requirement(answer)
    override_note = (answer.free_text or "").strip()
    if answer.selected_option:
        selection_note = f"User selected: {answer.selected_option}"
        override_note = f"{selection_note}. {override_note}".strip() if override_note else selection_note

    if waive:
        manifest["analysis_mode"] = "indicative_proxy"
        manifest["waive_spend_requirement"] = True
    if override_note:
        manifest["business_override_note"] = override_note

    try:
        manifest_path.write_text(json.dumps(manifest, indent=2))
    except Exception:
        pass

    existing = _memory.get("session", session_id)
    if not isinstance(existing, dict):
        existing = {}
    if override_note:
        existing["business_override_note"] = override_note
    if waive:
        existing["analysis_mode"] = "indicative_proxy"
    _memory.put("session", session_id, existing)

    return {
        "clarification_answer": answer.model_dump(),
        "clarification_resolved": True,
        "waive_spend_requirement": waive,
        "business_override_note": override_note or None,
        "defer_only": option_implies_deferral(answer.selected_option) and not waive,
    }
