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
    """Rule-based extraction of portfolio driver overrides."""
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
    elif re.search(r"\b(slip|delay|delayed)\b", q):
        drivers["timeline_compression_factor"] = 1.25

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

    timeline_factor = 1.0
    if re.search(r"\b(slip|delay|delayed|months late)\b", q):
        timeline_factor = 1.5
    m = re.search(r"timeline\s+(?:factor|×|x)\s*(\d+(?:\.\d+)?)", q)
    if m:
        timeline_factor = float(m.group(1))

    exec_rate: float | None = None
    m = re.search(r"(\d+(?:\.\d+)?)\s*%\s+execut", q)
    if m:
        val = float(m.group(1))
        exec_rate = val / 100.0 if val > 1 else val

    if cat_id or savings_delta or timeline_factor != 1.0 or exec_rate is not None:
        scenarios.append({
            "name": "custom_nl",
            "target": "category" if cat_id else "portfolio",
            "id": cat_id,
            "savings_pct_delta": savings_delta,
            "timeline_factor": timeline_factor,
            "execution_rate": exec_rate,
        })
    return scenarios


def _llm_parse_scenarios(
    question: str,
    categories: List[Dict[str, str]],
) -> List[Dict[str, Any]]:
    from app.opar.llm_provider import call_llm

    system = (
        "Parse a what-if question into JSON: "
        '{"scenarios": [{"name": str, "target": "portfolio"|"category", '
        '"id": str|null, "savings_pct_delta": float, "timeline_factor": float, '
        '"execution_rate": float|null}], "drivers": {}}. '
        "savings_pct_delta is fractional (-0.1 = -10%). "
        "Only use category ids/names from the provided list. "
        "Return ONLY JSON."
    )
    user = json.dumps(
        {"question": question, "categories": categories[:30]},
        ensure_ascii=False,
    )
    raw = call_llm(system, user, max_tokens=600, skill_name="scenario_parser")
    if not raw:
        return []
    try:
        from app.opar.claude_client import _extract_json

        data = _extract_json(raw)
        if isinstance(data, dict):
            return list(data.get("scenarios") or [])
    except Exception:
        logger.warning("scenario_parser: LLM JSON parse failed")
    return []


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
        try:
            validated.append(
                CustomScenarioSpec(
                    name=str(raw.get("name") or "custom"),
                    target=target,
                    id=str(target_id) if target_id else None,
                    savings_pct_delta=float(raw.get("savings_pct_delta") or 0.0),
                    timeline_factor=float(raw.get("timeline_factor") or 1.0),
                    execution_rate=float(raw["execution_rate"]) if raw.get("execution_rate") is not None else None,
                )
            )
        except Exception as exc:
            errors.append(str(exc))
    return validated, errors


def parse_what_if_request(
    session: ToolSessionContext,
    question: str,
) -> Dict[str, Any]:
    """NL → drivers + custom scenarios with validation."""
    question = (question or "").strip()
    categories = _session_categories(session)
    drivers = parse_drivers_from_nl(question)
    scenarios = _rule_based_scenarios(question, categories)
    if not scenarios:
        scenarios = _llm_parse_scenarios(question, categories)
    validated, errors = validate_custom_scenarios(scenarios, categories)
    return {
        "question": question,
        "drivers": drivers,
        "scenarios": [s.model_dump() for s in validated],
        "validation_errors": errors,
        "known_categories": categories[:20],
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
