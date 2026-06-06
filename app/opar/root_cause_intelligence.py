"""LLM enrichment for root-cause findings — narrative interpretation over deterministic signals."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from app.config import logger
from app.opar.llm_provider import call_llm, get_active_mode

_ROOT_CAUSE_SYSTEM = """You are an FP&A diagnostic advisor interpreting deterministic root-cause findings.

Given category-level structural diagnoses (HHI, maverick buying, cost-per-transaction), write brief
executive-readable interpretation. Do NOT invent spend amounts or suppliers not in the input.

Return ONLY valid JSON:
{
  "findings": [
    {
      "category_id": "string",
      "interpretation": "2-3 sentence causal narrative for leadership",
      "priority": "high|medium|low",
      "recommended_next_step": "string"
    }
  ]
}
Max 8 findings."""


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


def enrich_root_cause_with_llm(root_cause_output: Dict[str, Any]) -> Dict[str, Any] | None:
    """Add LLM interpretation layer; deterministic findings remain the anchor."""
    if get_active_mode() == "M1":
        return None
    findings = root_cause_output.get("root_cause_findings") or []
    if not findings:
        return None

    payload = {
        "findings": [
            {
                "category_id": f.get("category_id"),
                "category_name": f.get("category_name"),
                "root_causes": (f.get("root_causes") or [])[:3],
            }
            for f in findings[:10]
            if isinstance(f, dict)
        ]
    }

    try:
        raw = call_llm(
            _ROOT_CAUSE_SYSTEM,
            json.dumps(payload, default=str),
            max_tokens=1200,
            skill_name="root-cause-analyzer",
        )
        if not raw:
            return None
        parsed = _parse_json(raw)
        if not parsed:
            return None
        return _merge_interpretations(root_cause_output, parsed)
    except Exception as exc:
        logger.debug("root_cause_intelligence skip: %s", exc)
        return None


def _merge_interpretations(output: Dict[str, Any], parsed: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(output)
    by_cat = {
        str(i.get("category_id") or "").lower(): i
        for i in (parsed.get("findings") or [])
        if isinstance(i, dict)
    }
    enriched: List[Dict[str, Any]] = []
    for finding in out.get("root_cause_findings") or []:
        if not isinstance(finding, dict):
            continue
        row = dict(finding)
        interp = by_cat.get(str(row.get("category_id") or "").lower())
        if interp:
            row["llm_interpretation"] = interp.get("interpretation")
            row["llm_priority"] = interp.get("priority")
            row["llm_next_step"] = interp.get("recommended_next_step")
        enriched.append(row)
    out["root_cause_findings"] = enriched
    out["interpretation_source"] = "llm_enriched"
    return out
