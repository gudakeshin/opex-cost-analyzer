from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple


def _extract_revenue(text: str) -> float | None:
    cleaned = text.lower().replace(",", "")
    match = re.search(r"(\d+(?:\.\d+)?)\s*(billion|million|bn|mn)?", cleaned)
    if not match:
        return None
    value = float(match.group(1))
    unit = match.group(2) or ""
    if unit in {"billion", "bn"}:
        return value * 1_000_000_000
    if unit in {"million", "mn"}:
        return value * 1_000_000
    if value >= 1000:
        return value
    return None


def _extract_timeframe_days(text: str) -> int | None:
    lowered = text.lower()
    day_match = re.search(r"(\d+)\s*day", lowered)
    week_match = re.search(r"(\d+)\s*week", lowered)
    month_match = re.search(r"(\d+)\s*month", lowered)
    if day_match:
        return int(day_match.group(1))
    if week_match:
        return int(week_match.group(1)) * 7
    if month_match:
        return int(month_match.group(1)) * 30
    return None


def _extract_industry(text: str) -> str | None:
    lowered = text.lower()
    candidates = [
        "technology",
        "financial_services",
        "manufacturing",
        "healthcare",
        "retail_consumer",
    ]
    for candidate in candidates:
        if candidate.replace("_", " ") in lowered or candidate in lowered:
            return candidate
    return None


def update_planning_state(state: Dict[str, Any], user_message: str) -> Dict[str, Any]:
    out = dict(state or {})
    out.setdefault("objective", "")
    out.setdefault("industry", "")
    out.setdefault("annual_revenue", 0.0)
    out.setdefault("timeframe_days", 0)
    out.setdefault("constraints", [])
    out.setdefault("last_question", "")
    out.setdefault("history", [])

    out["history"].append({"role": "user", "content": user_message})
    lowered = user_message.lower()
    if not out["objective"]:
        out["objective"] = user_message.strip()

    maybe_industry = _extract_industry(user_message)
    if maybe_industry:
        out["industry"] = maybe_industry

    maybe_revenue = _extract_revenue(user_message)
    if maybe_revenue:
        out["annual_revenue"] = maybe_revenue

    maybe_days = _extract_timeframe_days(user_message)
    if maybe_days:
        out["timeframe_days"] = maybe_days

    for token in ["compliance", "contract", "headcount", "procurement policy", "budget freeze"]:
        if token in lowered and token not in out["constraints"]:
            out["constraints"].append(token)

    return out


def build_planner_reply(state: Dict[str, Any], schemas: List[Dict[str, Any]]) -> Tuple[str, bool]:
    missing = []
    if not state.get("industry"):
        missing.append("industry")
    if not state.get("annual_revenue"):
        missing.append("annual_revenue")
    if not state.get("timeframe_days"):
        missing.append("timeframe_days")

    if missing:
        if "industry" in missing:
            return "To tailor the plan, what industry should I benchmark against (e.g., technology, manufacturing, healthcare)?", True
        if "annual_revenue" in missing:
            return "What is your approximate annual revenue? This is needed for benchmark normalization.", True
        return "What timeline are you targeting for initial savings realization (for example 90 days or 6 months)?", True

    schema_lines = []
    for schema in schemas:
        mapped = [f"{k}:{v}" for k, v in schema.get("semantic_map", {}).items() if v]
        schema_lines.append(f"- {schema.get('file_name')}: rows={schema.get('rows')} mapped=({', '.join(mapped)})")
    schema_summary = "\n".join(schema_lines) if schema_lines else "- No tabular schema available yet."

    response = (
        "Great, I can now produce a tailored savings plan.\n\n"
        f"Objective: {state.get('objective', 'cost optimization')}\n"
        f"Industry: {state.get('industry')}\n"
        f"Annual Revenue: ${state.get('annual_revenue'):,.0f}\n"
        f"Timeframe: {state.get('timeframe_days')} days\n"
        f"Constraints: {', '.join(state.get('constraints') or ['none provided'])}\n\n"
        "Detected upload schema:\n"
        f"{schema_summary}\n\n"
        "Next steps:\n"
        "1) Run spend profiling and taxonomy validation on uploaded files.\n"
        "2) Execute peer/internal/heuristic benchmarking with confidence bands.\n"
        "3) Build value bridge, shortlist top categories, and draft business case."
    )
    return response, False

