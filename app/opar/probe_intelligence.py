"""Gemini-assisted portfolio probe composer — clusters and rewrites SME probes."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from app.config import GEMINI_ENABLED, logger
from app.opar.gemini_client import call_gemini

_PROBE_SYSTEM = """You are an FP&A advisor preparing human-in-the-loop assumption probes.
Given a list of portfolio-level probe families (already deduplicated by family id), refine wording only.
Do NOT split one family into multiple questions. Do NOT invent new probe families.

Return ONLY valid JSON:
{
  "portfolio_probes": [
    {
      "probe_family_id": "transaction_volume",
      "question": "one clear question",
      "reasoning": "why this matters",
      "scope": "portfolio",
      "applies_to_categories": ["HR", "Travel"],
      "options": ["option A", "option B"]
    }
  ]
}
Keep applies_to_categories exactly as provided per family. Max 5 probes."""


def _parse_json_object(raw: str) -> Dict[str, Any] | None:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def enrich_portfolio_probes_with_gemini(
    portfolio_probes: List[Dict[str, Any]],
) -> List[Dict[str, Any]] | None:
    """Rewrite portfolio probes for clarity; return None to keep deterministic output."""
    if not GEMINI_ENABLED or not portfolio_probes:
        return None
    payload = {
        "portfolio_probes": [
            {
                "probe_family_id": p.get("probe_family_id"),
                "question": p.get("question"),
                "why_critical": p.get("why_critical"),
                "scope": p.get("scope"),
                "applies_to_categories": p.get("affected_categories") or [],
                "saving_at_stake": p.get("saving_at_stake"),
            }
            for p in portfolio_probes
        ]
    }
    try:
        raw = call_gemini(
            system=_PROBE_SYSTEM,
            user_content=json.dumps(payload, default=str),
            max_tokens=1200,
        )
        parsed = _parse_json_object(raw)
        if not parsed or not isinstance(parsed.get("portfolio_probes"), list):
            return None
        return _merge_gemini_probes(portfolio_probes, parsed["portfolio_probes"])
    except Exception as exc:
        logger.debug("probe_intelligence gemini skip: %s", exc)
        return None


def _merge_gemini_probes(
    original: List[Dict[str, Any]],
    refined: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    by_id = {str(p.get("probe_family_id")): p for p in original if p.get("probe_family_id")}
    out: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for item in refined:
        if not isinstance(item, dict):
            continue
        fam = str(item.get("probe_family_id") or "")
        if not fam or fam in seen or fam not in by_id:
            continue
        seen.add(fam)
        base = dict(by_id[fam])
        if item.get("question"):
            base["question"] = str(item["question"])
        if item.get("reasoning"):
            base["why_critical"] = str(item["reasoning"])
        cats = item.get("applies_to_categories")
        if isinstance(cats, list) and cats:
            base["affected_categories"] = [str(c) for c in cats]
        opts = item.get("options")
        if isinstance(opts, list) and opts:
            base["options"] = [str(o) for o in opts[:4]]
        base["scope"] = str(item.get("scope") or base.get("scope") or "portfolio")
        out.append(base)
    for fam, probe in by_id.items():
        if fam not in seen:
            out.append(probe)
    out.sort(key=lambda p: float(p.get("saving_at_stake") or 0), reverse=True)
    return out[:5]


def synthesize_probe_answer_acknowledgment(
    *,
    probe_family_id: str,
    answer: str,
    applies_to_categories: List[str],
    remaining_count: int,
) -> str | None:
    """Lightweight Gemini acknowledgment after a probe answer."""
    if not GEMINI_ENABLED:
        return None
    prompt = json.dumps({
        "probe_family_id": probe_family_id,
        "user_answer": answer,
        "applies_to_categories": applies_to_categories,
        "remaining_probe_families": remaining_count,
    })
    try:
        return call_gemini(
            system=(
                "Acknowledge the user's assumption probe answer in 2-3 sentences. "
                "State which categories inherit this answer. "
                "If probes remain, note how many without re-asking. Use markdown. No JSON."
            ),
            user_content=prompt,
            max_tokens=300,
        )
    except Exception:
        return None
