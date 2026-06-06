"""LLM reasoning step for opportunity identification with numeric provenance."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from app.opar.llm_provider import call_llm
from app.opar.numeric_provenance import apply_bounded_adjustment, audit_llm_numeric_adjustment
from app.opar.tools.context import ToolSessionContext

_ASSESS_SYSTEM = """You are a senior FP&A advisor reviewing deterministic savings model output.
Given benchmark gaps, root-cause signals, and document evidence, identify which opportunities are REAL
vs noise. You may adjust savings figures within ±25% of deterministic anchors when evidence supports it.

Return ONLY valid JSON:
{
  "opportunities": [
    {
      "category_id": "string",
      "category_name": "string",
      "lever": "string",
      "verdict": "proceed|probe_first|reject",
      "deterministic_savings": 0.0,
      "adjusted_savings": 0.0,
      "rationale": "string",
      "evidence_refs": ["string"]
    }
  ],
  "summary": "string"
}

Rules:
- Every adjusted_savings must reference deterministic_savings as anchor.
- reject when evidence is insufficient or gap is likely data artefact.
- probe_first when a key assumption is unverified.
"""


def assess_opportunities_with_llm(
    session: ToolSessionContext,
    *,
    focus_category: Optional[str] = None,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    savings = session.skill_outputs.get("savings-modeler", {})
    evidence = session.skill_outputs.get("evidence-gatherer", {})
    root_cause = session.skill_outputs.get("root-cause-analyzer", {})
    peer = session.skill_outputs.get("peer-benchmarker", {})

    deterministic_opps = savings.get("opportunities") or savings.get("initiatives") or []
    payload = {
        "focus_category": focus_category,
        "notes": notes,
        "deterministic_opportunities": deterministic_opps[:12],
        "root_cause_signals": _compact(root_cause),
        "benchmark_gaps": _compact(peer),
        "evidence_items": (evidence.get("evidence_items") or evidence.get("items") or [])[:8],
        "user_message": session.user_message,
    }

    raw = call_llm(
        _ASSESS_SYSTEM,
        json.dumps(payload, ensure_ascii=False, default=str),
        max_tokens=1800,
        skill_name="assess_opportunities",
    )
    if not raw:
        return _deterministic_fallback(deterministic_opps)

    parsed = _parse_json(raw)
    if not isinstance(parsed, dict):
        return _deterministic_fallback(deterministic_opps)

    tagged_opps: List[Dict[str, Any]] = []
    audit_rows: List[Dict[str, Any]] = []
    for opp in parsed.get("opportunities") or []:
        if not isinstance(opp, dict):
            continue
        anchor = float(opp.get("deterministic_savings") or opp.get("mid_case_savings") or 0)
        adjusted = float(opp.get("adjusted_savings") or anchor)
        tagged = apply_bounded_adjustment(
            anchor,
            adjusted,
            field="mid_case_savings",
            rationale=str(opp.get("rationale") or ""),
            category_id=str(opp.get("category_id") or ""),
            lever=str(opp.get("lever") or ""),
        )
        opp["savings_provenance"] = tagged
        opp["mid_case_savings"] = tagged["value"]
        tagged_opps.append(opp)
        if tagged["source"] == "llm_estimate":
            audit_rows.append(tagged)

    audit_llm_numeric_adjustment(
        session_id=session.session_id,
        engagement_id=session.engagement_id,
        adjustments=audit_rows,
        context=f"assess_opportunities focus={focus_category}",
    )

    return {
        "opportunities": tagged_opps,
        "summary": parsed.get("summary") or "",
        "source": "llm_reasoning" if raw else "deterministic_fallback",
    }


def _deterministic_fallback(opportunities: list) -> Dict[str, Any]:
    from app.opar.numeric_provenance import tag_deterministic

    tagged = []
    for opp in opportunities[:8]:
        if not isinstance(opp, dict):
            continue
        val = float(opp.get("mid_case_savings") or opp.get("savings") or 0)
        opp = dict(opp)
        opp["savings_provenance"] = tag_deterministic(val, field="mid_case_savings")
        tagged.append(opp)
    return {"opportunities": tagged, "summary": "Deterministic savings model (LLM unavailable).", "source": "deterministic"}


def _compact(obj: Any, max_len: int = 4000) -> Any:
    text = json.dumps(obj, ensure_ascii=False, default=str)
    if len(text) <= max_len:
        return obj
    return {"_truncated": True, "preview": text[:max_len]}


def _parse_json(raw: str) -> Any:
    text = raw.strip()
    if "```json" in text:
        m = re.search(r"```json\s*([\s\S]*?)```", text)
        if m:
            text = m.group(1).strip()
    elif "```" in text:
        m = re.search(r"```\s*([\s\S]*?)```", text)
        if m:
            text = m.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None
