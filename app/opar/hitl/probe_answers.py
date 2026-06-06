"""Persist SME probe answers and filter sme-critique output."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Set

from app.config import UPLOAD_DIR
from app.memory import MemoryStore
from app.storage import read_json

_memory = MemoryStore()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_probe_answers(session_id: str) -> List[Dict[str, Any]]:
    manifest = read_json(UPLOAD_DIR / session_id / "manifest.json", {})
    answers = manifest.get("probe_answers")
    return answers if isinstance(answers, list) else []


def get_answered_family_ids(session_id: str) -> Set[str]:
    return {
        str(a.get("probe_family_id"))
        for a in load_probe_answers(session_id)
        if isinstance(a, dict) and a.get("probe_family_id")
    }


def apply_probe_answer(session_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Append probe answer to manifest and session memory."""
    manifest_path = UPLOAD_DIR / session_id / "manifest.json"
    manifest = read_json(manifest_path, {"files": [], "industry": "", "annual_revenue": 0.0})
    answers = manifest.get("probe_answers")
    if not isinstance(answers, list):
        answers = []

    fam = str(payload.get("probe_family_id") or "")
    entry = {
        "probe_family_id": fam,
        "question": str(payload.get("question") or ""),
        "answer": str(payload.get("answer") or ""),
        "selected_option": payload.get("selected_option"),
        "scope": str(payload.get("scope") or "portfolio"),
        "applies_to_categories": payload.get("applies_to_categories") or [],
        "answered_at": _utc_now(),
    }
    answers = [a for a in answers if not (isinstance(a, dict) and str(a.get("probe_family_id")) == fam)]
    answers.append(entry)
    manifest["probe_answers"] = answers

    try:
        manifest_path.write_text(json.dumps(manifest, indent=2))
    except Exception:
        pass

    existing = _memory.get("session", session_id)
    if not isinstance(existing, dict):
        existing = {}
    existing["probe_answers"] = answers
    _memory.put("session", session_id, existing)

    return entry


def filter_sme_critique_with_answers(
    sme_output: Dict[str, Any],
    probe_answers: List[Dict[str, Any]] | None,
) -> Dict[str, Any]:
    """Remove satisfied probe families and adjust summary counts."""
    if not sme_output or not probe_answers:
        return sme_output

    answered_ids = {
        str(a.get("probe_family_id"))
        for a in probe_answers
        if isinstance(a, dict) and a.get("probe_family_id")
    }
    if not answered_ids:
        return sme_output

    out = dict(sme_output)
    critiques = []
    probe_count = 0
    savings_probe = 0.0
    ready_count = int((out.get("critique_summary") or {}).get("ready_count") or 0)
    savings_ready = float((out.get("critique_summary") or {}).get("savings_ready") or 0)

    for critique in out.get("initiative_critiques") or []:
        if not isinstance(critique, dict):
            continue
        c = dict(critique)
        remaining_probes = [
            p for p in (c.get("probe_questions") or [])
            if isinstance(p, dict) and str(p.get("probe_family_id")) not in answered_ids
        ]
        c["probe_questions"] = remaining_probes
        if c.get("sme_verdict") == "probe_first" and not remaining_probes:
            c["sme_verdict"] = "proceed"
            c["evidence_supplemented_by_user"] = True
            saving = float(c.get("modelled_saving_3yr") or 0)
            ready_count += 1
            savings_ready += saving
        elif c.get("sme_verdict") == "probe_first":
            probe_count += 1
            savings_probe += float(c.get("modelled_saving_3yr") or 0)
        critiques.append(c)

    portfolio = [
        p for p in (out.get("portfolio_probes") or [])
        if isinstance(p, dict) and str(p.get("probe_family_id")) not in answered_ids
    ]
    top = [
        p for p in (out.get("top_probes") or [])
        if isinstance(p, dict) and str(p.get("probe_family_id")) not in answered_ids
    ]

    summary = dict(out.get("critique_summary") or {})
    insufficient_count = int(summary.get("insufficient_count") or 0)
    summary.update({
        "probe_count": probe_count,
        "ready_count": ready_count,
        "savings_probe": round(savings_probe),
        "savings_ready": round(savings_ready),
        "answered_probe_families": len(answered_ids),
    })

    out["initiative_critiques"] = critiques
    out["portfolio_probes"] = portfolio
    out["top_probes"] = top[:3]
    out["critique_summary"] = summary
    return out


def apply_probe_answers_to_skill_outputs(
    skill_outputs: Dict[str, Any],
    session_id: str,
) -> Dict[str, Any]:
    """Overlay probe-answer filtering on cached skill outputs."""
    if not session_id or "sme-critique" not in skill_outputs:
        return skill_outputs
    answers = load_probe_answers(session_id)
    if not answers:
        return skill_outputs
    merged = dict(skill_outputs)
    sme = merged.get("sme-critique")
    if isinstance(sme, dict):
        merged["sme-critique"] = filter_sme_critique_with_answers(sme, answers)
    return merged
