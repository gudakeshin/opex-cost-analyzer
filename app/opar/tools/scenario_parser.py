"""Parse natural-language what-if questions into structured scenario specs."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Tuple

from app.config import logger
from app.opar.tools.context import ToolSessionContext
from app.schemas import CustomScenarioSpec

_VALID_TARGETS = frozenset({"portfolio", "category"})
_DRIVER_KEYS = (
    "headcount_growth_pct",
    "revenue_growth_pct",
    "execution_rate_pct",
    "timeline_compression_factor",
)

_PRESET_ALIASES = {
    "inr_depreciation": "fx_stress",
    "wage_shock": "wage_inflation",
    "commodity": "commodity_spike",
    "exec_slip": "execution_slip",
    "macro_fx": "fx_stress",
}

_BUILTIN_PRESETS = frozenset({
    "conservative",
    "base",
    "accelerated",
    "delayed",
    "partial_success",
    "volume_growth",
    "bounce_back",
    "regulatory_headwind",
})

_MACRO_PRESETS = frozenset({
    "fx_stress",
    "wage_inflation",
    "commodity_spike",
    "execution_slip",
    "upside",
})


def _session_categories(session: ToolSessionContext) -> List[Dict[str, str]]:
    cats: List[Dict[str, str]] = []
    profiler = session.skill_outputs.get("spend-profiler") or {}
    for row in profiler.get("category_profile") or profiler.get("top_categories") or []:
        cid = str(row.get("category_id") or row.get("id") or "")
        cname = str(row.get("category_name") or row.get("name") or "")
        if cid or cname:
            cats.append({"category_id": cid, "category_name": cname})
    if cats:
        return cats
    savings = session.skill_outputs.get("savings-modeler") or {}
    seen: set[str] = set()
    for init in savings.get("initiatives") or []:
        cid = str(init.get("category_id") or init.get("category") or "")
        cname = str(init.get("category_name") or init.get("category") or "")
        key = cid or cname
        if key and key not in seen:
            seen.add(key)
            cats.append({"category_id": cid, "category_name": cname})
    if cats:
        return cats
    session.load_session_data()
    return cats


def _match_category(question: str, categories: List[Dict[str, str]]) -> str | None:
    q = question.lower()
    for cat in categories:
        for field in ("category_name", "category_id"):
            val = str(cat.get(field) or "").strip()
            if len(val) >= 3 and val.lower() in q:
                return cat.get("category_id") or cat.get("category_name") or val
    return None


def parse_drivers_from_nl(question: str) -> Dict[str, float]:
    """Rule-based extraction of portfolio driver overrides (fast path)."""
    q = question.lower()
    drivers: Dict[str, float] = {}

    m = re.search(r"execution(?:\s+rate)?\s+(?:drops?\s+to|at|of)\s+(\d+(?:\.\d+)?)\s*%", q)
    if not m:
        m = re.search(r"(\d+(?:\.\d+)?)\s*%\s+execution", q)
    if m:
        val = float(m.group(1))
        drivers["execution_rate_pct"] = val / 100.0 if val > 1 else val

    m = re.search(r"headcount\s+(?:grows?|growth)\s+(\d+(?:\.\d+)?)\s*%", q)
    if m:
        drivers["headcount_growth_pct"] = float(m.group(1)) / 100.0

    m = re.search(r"revenue\s+(?:grows?|growth)\s+(\d+(?:\.\d+)?)\s*%", q)
    if m:
        drivers["revenue_growth_pct"] = float(m.group(1)) / 100.0

    m = re.search(r"timeline\s+(?:slip|delay|extends?)\s+(\d+(?:\.\d+)?)\s*x", q)
    if m:
        drivers["timeline_compression_factor"] = float(m.group(1))
    elif re.search(r"\b(slip|slips|delay|delayed)\b", q):
        drivers["timeline_compression_factor"] = 1.25

    m = re.search(r"supplier\s+prices?\s+(?:rise|increase|up)\s+(\d+(?:\.\d+)?)\s*%", q)
    if m:
        drivers["supplier_price_inflation_pct"] = float(m.group(1)) / 100.0

    return drivers


def _rule_based_scenarios(
    question: str,
    categories: List[Dict[str, str]],
) -> List[Dict[str, Any]]:
    q = question.lower()
    scenarios: List[Dict[str, Any]] = []
    cat_id = _match_category(question, categories)

    savings_delta = 0.0
    m = re.search(r"savings\s+(?:drop|fall|decline|reduce)\s+(\d+(?:\.\d+)?)\s*%", q)
    if m:
        savings_delta = -float(m.group(1)) / 100.0
    m = re.search(r"(\d+(?:\.\d+)?)\s*%\s+(?:lower|less)\s+savings", q)
    if m:
        savings_delta = -float(m.group(1)) / 100.0

    spend_pool_delta = 0.0
    m = re.search(r"supplier\s+prices?\s+(?:rise|increase|up)\s+(\d+(?:\.\d+)?)\s*%", q)
    if m:
        spend_pool_delta = float(m.group(1)) / 100.0

    timeline_factor = 1.0
    if re.search(r"\b(slip|slips|delay|delayed|months late)\b", q):
        timeline_factor = 1.5
    m = re.search(r"timeline\s+(?:factor|×|x)\s*(\d+(?:\.\d+)?)", q)
    if m:
        timeline_factor = float(m.group(1))

    exec_rate: float | None = None
    m = re.search(r"(\d+(?:\.\d+)?)\s*%\s+execut", q)
    if m:
        val = float(m.group(1))
        exec_rate = val / 100.0 if val > 1 else val

    bounce_back: str | None = None
    if "high bounce" in q or "high bounce-back" in q:
        bounce_back = "high"
    elif "low bounce" in q:
        bounce_back = "low"

    if (
        cat_id
        or savings_delta
        or spend_pool_delta
        or timeline_factor != 1.0
        or exec_rate is not None
        or bounce_back
    ):
        scenarios.append({
            "name": "custom_nl",
            "target": "category" if cat_id else "portfolio",
            "id": cat_id,
            "savings_pct_delta": savings_delta,
            "spend_pool_delta_pct": spend_pool_delta,
            "timeline_factor": timeline_factor,
            "execution_rate": exec_rate,
            "bounce_back_override": bounce_back,
        })
    return scenarios


def _llm_parse_what_if(
    question: str,
    categories: List[Dict[str, str]],
) -> Dict[str, Any]:
    from app.opar.llm_provider import call_llm_structured
    from app.opar.llm_schemas import SCENARIO_PARSE_SCHEMA

    system = (
        "Parse a what-if question into structured scenario specs and portfolio driver overrides. "
        "savings_pct_delta, addressable_spend_delta_pct, and spend_pool_delta_pct are fractional "
        "(-0.1 = -10%). cost_driver_deltas maps named drivers (e.g. supplier_price_inflation_pct) "
        "to fractional deltas. bounce_back_override is high|medium|low when specified. "
        "Only use category ids/names from the provided list."
    )
    user = json.dumps(
        {"question": question, "categories": categories[:30]},
        ensure_ascii=False,
    )
    data = call_llm_structured(
        system,
        user,
        SCENARIO_PARSE_SCHEMA,
        max_tokens=800,
        skill_name="scenario_parser",
    )
    if isinstance(data, dict):
        return {
            "scenarios": list(data.get("scenarios") or []),
            "drivers": dict(data.get("drivers") or {}),
        }
    return {"scenarios": [], "drivers": {}}


def validate_custom_scenarios(
    specs: List[Dict[str, Any]],
    categories: List[Dict[str, str]],
) -> Tuple[List[CustomScenarioSpec], List[str]]:
    """Validate and normalize scenario dicts against session categories."""
    valid_ids = {c.get("category_id") or "" for c in categories}
    valid_ids |= {c.get("category_name") or "" for c in categories}
    valid_ids.discard("")

    validated: List[CustomScenarioSpec] = []
    errors: List[str] = []
    for raw in specs:
        target = str(raw.get("target") or "portfolio")
        if target not in _VALID_TARGETS:
            errors.append(f"Unsupported target '{target}' — use portfolio or category")
            target = "portfolio"
        target_id = raw.get("id")
        if target == "category" and target_id:
            tid = str(target_id)
            if tid not in valid_ids and not any(
                tid.lower() in (c.get("category_name") or "").lower() for c in categories
            ):
                errors.append(f"Unknown category '{target_id}' — not in session data")
                continue
        bounce = raw.get("bounce_back_override")
        if bounce is not None and str(bounce).lower() not in ("high", "medium", "low"):
            errors.append(f"Invalid bounce_back_override '{bounce}' — use high, medium, or low")
            bounce = None
        try:
            validated.append(
                CustomScenarioSpec(
                    name=str(raw.get("name") or "custom"),
                    target=target,
                    id=str(target_id) if target_id else None,
                    savings_pct_delta=float(raw.get("savings_pct_delta") or 0.0),
                    timeline_factor=float(raw.get("timeline_factor") or 1.0),
                    execution_rate=float(raw["execution_rate"]) if raw.get("execution_rate") is not None else None,
                    addressable_spend_delta_pct=float(raw.get("addressable_spend_delta_pct") or 0.0),
                    spend_pool_delta_pct=float(raw.get("spend_pool_delta_pct") or 0.0),
                    bounce_back_override=str(bounce).lower() if bounce else None,
                    cost_driver_deltas={
                        str(k): float(v)
                        for k, v in (raw.get("cost_driver_deltas") or {}).items()
                        if isinstance(v, (int, float))
                    },
                )
            )
        except Exception as exc:
            errors.append(str(exc))
    return validated, errors


def parse_what_if_request(
    session: ToolSessionContext,
    question: str,
) -> Dict[str, Any]:
    """NL → drivers + custom scenarios with validation (LLM primary, regex fast-path)."""
    question = (question or "").strip()
    categories = _session_categories(session)

    llm_parsed = _llm_parse_what_if(question, categories)
    drivers = dict(llm_parsed.get("drivers") or {})
    scenarios = list(llm_parsed.get("scenarios") or [])

    for key, val in parse_drivers_from_nl(question).items():
        drivers.setdefault(key, val)

    if not scenarios:
        scenarios = _rule_based_scenarios(question, categories)

    for spec in scenarios:
        for key, val in (spec.get("cost_driver_deltas") or {}).items():
            drivers.setdefault(str(key), float(val))

    validated, errors = validate_custom_scenarios(scenarios, categories)
    return {
        "question": question,
        "drivers": drivers,
        "scenarios": [s.model_dump() for s in validated],
        "validation_errors": errors,
        "known_categories": categories[:20],
        "parse_source": "llm" if llm_parsed.get("scenarios") else "regex",
    }


def normalize_preset(preset: str | None) -> str | None:
    if not preset:
        return None
    key = preset.strip().lower().replace(" ", "_")
    return _PRESET_ALIASES.get(key, key)


def is_macro_preset(preset: str) -> bool:
    return normalize_preset(preset) in _MACRO_PRESETS


def is_builtin_preset(preset: str) -> bool:
    return normalize_preset(preset) in _BUILTIN_PRESETS
