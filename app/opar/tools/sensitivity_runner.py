"""Agent-facing sensitivity / what-if execution."""
from __future__ import annotations

from typing import Any, Dict, List

from app.opar.tools.context import ToolSessionContext
from app.opar.tools.scenario_parser import (
    is_builtin_preset,
    is_macro_preset,
    normalize_preset,
    parse_what_if_request,
)
from app.services.sensitivity import compute_sensitivity


def _portfolio_rates(session: ToolSessionContext) -> tuple[float, float]:
    session.load_session_data()
    wacc = float(session.manifest.get("wacc") or 0.10)
    tax = float(session.manifest.get("effective_tax_rate") or 0.0)
    return wacc, tax


def _ensure_value_modeling(session: ToolSessionContext) -> None:
    if "value-bridge-calculator" not in session.skill_outputs:
        session.invoke_skill("value-bridge-calculator")
    if "savings-modeler" not in session.skill_outputs:
        session.invoke_skill("savings-modeler")


def run_sensitivity_for_session(
    session: ToolSessionContext,
    *,
    scenarios: List[Dict[str, Any]] | None = None,
    drivers: Dict[str, float] | None = None,
    preset: str | None = None,
    natural_language: str | None = None,
) -> Dict[str, Any]:
    """Run compute_sensitivity and/or scenario-modeler with prerequisites."""
    _ensure_value_modeling(session)

    bridge = session.skill_outputs.get("value-bridge-calculator")
    if not bridge:
        raise RuntimeError("value-bridge-calculator did not produce output")

    savings_model = session.skill_outputs.get("savings-modeler")
    wacc, tax = _portfolio_rates(session)

    parsed_nl: Dict[str, Any] | None = None
    custom_scenarios = list(scenarios or [])
    driver_inputs = dict(drivers or {})

    if natural_language:
        parsed_nl = parse_what_if_request(session, natural_language)
        custom_scenarios.extend(parsed_nl.get("scenarios") or [])
        for k, v in (parsed_nl.get("drivers") or {}).items():
            driver_inputs.setdefault(k, v)

    preset_key = normalize_preset(preset)
    macro_output: Dict[str, Any] | None = None
    if preset_key and is_macro_preset(preset_key):
        macro_output = session.invoke_skill("scenario-modeler")
        macro_scenarios = macro_output.get("scenarios") or []
        filtered = [
            s for s in macro_scenarios
            if str(s.get("scenario_id") or s.get("name") or "").lower() == preset_key
        ]
        return {
            "engine": "scenario-modeler",
            "preset": preset_key,
            "macro_scenarios": filtered or macro_scenarios,
            "full_output": macro_output,
            "parsed_nl": parsed_nl,
        }

    result = compute_sensitivity(
        bridge,
        savings_model=savings_model,
        discount_rate=wacc,
        effective_tax_rate=tax,
        drivers=driver_inputs or None,
        custom_scenarios=custom_scenarios or None,
    )

    if preset_key and is_builtin_preset(preset_key):
        built = [s for s in result.get("scenarios", []) if s.get("name") == preset_key]
        result = {**result, "preset": preset_key, "preset_scenarios": built}

    session.skill_outputs["sensitivity-analyzer"] = result

    return {
        "engine": "compute_sensitivity",
        "preset": preset_key,
        "parsed_nl": parsed_nl,
        "drivers": driver_inputs,
        "custom_scenario_count": len(custom_scenarios),
        **result,
    }
