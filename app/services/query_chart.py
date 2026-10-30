"""Chart-spec inference for ad-hoc query results.

Deterministic heuristics pick the chart type and shape the data into the
frontend ChartSpec contract (frontend/src/types/index.ts). An optional single
fast-model call may refine the type/title; when it returns nothing the
heuristic spec stands unchanged, so the feature works fully offline.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

MAX_CHART_ROWS = 40
MAX_PIE_ROWS = 12

_TEMPORAL_COLS = {"fiscal_period", "fiscal_year", "period", "month", "quarter", "date", "year"}
_CURRENCY_HINTS = ("spend", "amount", "savings", "npv", "cost", "total", "value")
_SHARE_HINTS = ("share", "mix", "split", "proportion", "percent of", "%")

_CHART_REFINE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "type": {"type": "string", "enum": ["bar", "line", "pie"]},
        "title": {"type": "string", "maxLength": 90},
    },
    "required": ["type", "title"],
    "additionalProperties": False,
}


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _column_kinds(columns: List[str], rows: List[List[Any]]) -> Dict[str, str]:
    """Classify each column as numeric or categorical from its first non-null value."""
    kinds: Dict[str, str] = {}
    for idx, name in enumerate(columns):
        kind = "categorical"
        for row in rows:
            value = row[idx] if idx < len(row) else None
            if value is None:
                continue
            kind = "numeric" if _is_number(value) else "categorical"
            break
        kinds[name] = kind
    return kinds


def _unit_for(series_names: List[str]) -> str:
    for name in series_names:
        lowered = name.lower()
        if any(h in lowered for h in _CURRENCY_HINTS):
            return "currency"
    if any(n.lower() in ("lines", "count", "n", "rows") for n in series_names):
        return "count"
    return "count"


def _pick_primary_metric(numeric: List[str]) -> str:
    """Pick one series to chart. Mixing a currency column with a tiny count
    column (e.g. spend + lines) on one linear axis compresses the currency
    bars to near-invisible slivers, so ad-hoc charts default to a single
    metric — the FDE picks the field name, so prefer the value-bearing one."""
    for name in numeric:
        if any(h in name.lower() for h in _CURRENCY_HINTS):
            return name
    for name in numeric:
        if name.lower() not in ("lines", "count", "n", "rows"):
            return name
    return numeric[0]


def _title_from_question(question: str) -> str:
    text = (question or "").strip().rstrip("?.")
    if not text:
        return "Query result"
    text = text[0].upper() + text[1:]
    return text if len(text) <= 80 else text[:77] + "…"


def chart_spec_for_result(
    columns: List[str],
    rows: List[List[Any]],
    question: str = "",
    *,
    llm_polish: bool = False,
    model: str | None = None,
) -> Optional[Dict[str, Any]]:
    """Build a ChartSpec dict for a query result, or None when a table is better.

    None when: no rows, more than MAX_CHART_ROWS rows, no numeric column, or
    two or more categorical columns (a chart would need pivoting the FDE
    didn't ask for).
    """
    if not columns or not rows or len(rows) > MAX_CHART_ROWS:
        return None
    kinds = _column_kinds(columns, rows)
    categorical = [c for c in columns if kinds[c] == "categorical"]
    numeric = [c for c in columns if kinds[c] == "numeric"]
    if not numeric or len(categorical) != 1:
        return None

    x_key = categorical[0]
    series_cols = [_pick_primary_metric(numeric)]
    question_lower = (question or "").lower()
    if x_key.lower() in _TEMPORAL_COLS:
        chart_type = "line"
    elif (
        len(rows) <= MAX_PIE_ROWS
        and len(series_cols) == 1
        and any(h in question_lower for h in _SHARE_HINTS)
    ):
        chart_type = "pie"
    else:
        chart_type = "bar"

    col_index = {name: idx for idx, name in enumerate(columns)}
    data = [
        {name: (row[col_index[name]] if col_index[name] < len(row) else None)
         for name in [x_key, *series_cols]}
        for row in rows
    ]
    spec: Dict[str, Any] = {
        "id": f"query_chart_{uuid.uuid4().hex[:8]}",
        "type": chart_type,
        "title": _title_from_question(question),
        "x_key": x_key,
        "unit": _unit_for(series_cols),
        "series": [
            {"key": name, "name": name.replace("_", " ").title()} for name in series_cols
        ],
        "data": data,
        "source_skill": "ad_hoc_query",
    }

    if llm_polish:
        refined = _refine_with_llm(spec, question, model=model)
        if refined:
            spec["type"] = refined.get("type") or spec["type"]
            spec["title"] = (refined.get("title") or spec["title"]).strip() or spec["title"]
    return spec


def _refine_with_llm(
    spec: Dict[str, Any], question: str, *, model: str | None = None
) -> Optional[Dict[str, Any]]:
    from app.opar.llm_provider import call_llm_structured

    preview = spec["data"][:5]
    data = call_llm_structured(
        "Pick the best chart type (bar/line/pie) and a short business-facing title "
        "for this ad-hoc spend query result. Prefer the given type unless clearly wrong.",
        f"Question: {question}\nCurrent type: {spec['type']}\nx: {spec['x_key']}\n"
        f"Series: {[s['key'] for s in spec['series']]}\nSample rows: {preview}",
        _CHART_REFINE_SCHEMA,
        max_tokens=120,
        skill_name="query_chart",
        model=model,
    )
    return data if isinstance(data, dict) else None
