"""Optional per-engagement GL-code -> spend-category mapping.

A chart of accounts is client-specific, so the shipped taxonomy has no generic GL ranges. An
engagement can supply its own; ingestion then classifies lines by GL code first and falls back
to keyword matching for lines without a mapped code.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

from app.services.engagements_store import engagement_dir


class GLMappingError(ValueError):
    pass


def _path(engagement_id: str):
    return engagement_dir(engagement_id) / "gl_mapping.json"


def validate_ranges(ranges: List[Dict[str, Any]], taxonomy: Dict[str, Any]) -> List[Dict[str, Any]]:
    categories = {c.get("id"): c.get("name") for c in taxonomy.get("categories", [])}
    cleaned: List[Dict[str, Any]] = []
    for i, r in enumerate(ranges):
        try:
            lo, hi = int(r["from"]), int(r["to"])
        except (KeyError, TypeError, ValueError):
            raise GLMappingError(f"Range {i + 1}: 'from' and 'to' must be whole numbers") from None
        if lo > hi:
            raise GLMappingError(f"Range {i + 1}: 'from' ({lo}) is greater than 'to' ({hi})")
        cid = str(r.get("category_id") or "")
        if cid not in categories:
            raise GLMappingError(f"Range {i + 1}: unknown category_id {cid!r}")
        cleaned.append({"from": lo, "to": hi, "category_id": cid, "category_name": categories[cid]})
    ordered = sorted(cleaned, key=lambda r: r["from"])
    for a, b in zip(ordered, ordered[1:]):
        if b["from"] <= a["to"]:
            raise GLMappingError(f"Ranges {a['from']}-{a['to']} and {b['from']}-{b['to']} overlap")
    return ordered


def load_ranges(engagement_id: str) -> List[Dict[str, Any]]:
    try:
        data = json.loads(_path(engagement_id).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    ranges = data.get("ranges") if isinstance(data, dict) else None
    return ranges if isinstance(ranges, list) else []


def save_ranges(engagement_id: str, ranges: List[Dict[str, Any]]) -> None:
    path = _path(engagement_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"ranges": ranges}, indent=2), encoding="utf-8")


def apply_to_taxonomy(taxonomy: Dict[str, Any], engagement_id: str) -> Dict[str, Any]:
    """A copy of ``taxonomy`` with this engagement's GL ranges added (unchanged when it has none)."""
    ranges = load_ranges(engagement_id)
    if not ranges:
        return taxonomy
    return {
        **taxonomy,
        "gl_code_ranges": {
            f"{r['from']}-{r['to']}": {"category_id": r["category_id"], "category_name": r["category_name"]}
            for r in ranges
        },
    }
