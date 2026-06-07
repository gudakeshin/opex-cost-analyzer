"""LLM enrichment for SME critique — reasoning layer over deterministic maturity scores."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from app.config import GEMINI_ENABLED, logger
from app.opar.gemini_client import call_gemini
from app.opar.llm_provider import call_llm, get_active_mode

_SME_SYSTEM = """You are a Deloitte senior manager reviewing savings initiative evidence maturity.

Given deterministic SME critique output (maturity scores, verdicts, gaps), add judgment:
- Confirm or downgrade verdicts when evidence gaps create material risk.
- Write sme_qualification_notes per initiative flagged probe_first or insufficient_data.
- Do NOT invent numbers; reference only provided initiative data.

Return ONLY valid JSON:
{
  "initiative_adjustments": [
    {
      "category_id": "string",
      "lever": "string",
      "adjusted_verdict": "proceed|probe_first|insufficient_data",
      "qualification_note": "string",
      "maturity_rationale": "string"
    }
  ],
  "portfolio_note": "string"
}
Max 6 initiative_adjustments."""


def _parse_json(raw: str) -> Dict[str, Any] | None:
    text = (raw or "").strip()
    if "```" in text:
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if m:
            text = m.group(1).strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def enrich_sme_critique_with_llm(critique: Dict[str, Any]) -> Dict[str, Any] | None:
    """Apply LLM judgment over deterministic SME critique. Returns merged critique or None."""
    if get_active_mode() == "M1":
        return None
    initiatives = critique.get("initiative_critiques") or []
    if not initiatives:
        return None

    payload = {
        "critique_summary": critique.get("critique_summary"),
        "initiatives": [
            {
                "category_id": i.get("category_id"),
                "lever": i.get("lever"),
                "sme_verdict": i.get("sme_verdict"),
                "evidence_maturity": i.get("evidence_maturity"),
                "maturity_score": i.get("maturity_score"),
                "gaps": i.get("gaps"),
                "critical_risk": i.get("critical_risk"),
                "modelled_saving_3yr": i.get("modelled_saving_3yr"),
            }
            for i in initiatives[:10]
            if isinstance(i, dict)
        ],
    }

    try:
        if GEMINI_ENABLED:
            raw: str | None = call_gemini(_SME_SYSTEM, json.dumps(payload, default=str), max_tokens=1400)
        else:
            raw = call_llm(_SME_SYSTEM, json.dumps(payload, default=str), max_tokens=1400, skill_name="sme-critique")
        if not raw:
            return None
        parsed = _parse_json(raw)
        if not parsed:
            return None
        return _merge_adjustments(critique, parsed)
    except Exception as exc:
        logger.debug("sme_intelligence skip: %s", exc)
        return None


def _merge_adjustments(critique: Dict[str, Any], parsed: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(critique)
    adjustments = parsed.get("initiative_adjustments") or []
    by_key = {
        (str(a.get("category_id") or "").lower(), str(a.get("lever") or "")): a
        for a in adjustments
        if isinstance(a, dict)
    }
    merged: List[Dict[str, Any]] = []
    for item in out.get("initiative_critiques") or []:
        if not isinstance(item, dict):
            continue
        key = (str(item.get("category_id") or "").lower(), str(item.get("lever") or ""))
        adj = by_key.get(key)
        row = dict(item)
        if adj:
            note = str(adj.get("qualification_note") or "").strip()
            if note:
                row["llm_qualification_note"] = note
            rationale = str(adj.get("maturity_rationale") or "").strip()
            if rationale:
                row["llm_maturity_rationale"] = rationale
            verdict = adj.get("adjusted_verdict")
            if verdict in ("proceed", "probe_first", "insufficient_data"):
                row["sme_verdict"] = verdict
                row["verdict_source"] = "llm_enriched"
        merged.append(row)
    out["initiative_critiques"] = merged
    if parsed.get("portfolio_note"):
        out["llm_portfolio_note"] = parsed["portfolio_note"]
    out["sme_enrichment_source"] = "llm_reasoning"
    return out
