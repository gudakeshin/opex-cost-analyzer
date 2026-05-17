"""Layer 1: Golden dataset runner.

Loads a golden fixture JSON file, constructs NormalizedSpendLine inputs,
invokes the target skill directly (no OPAR), and checks all assertions.

Golden fixture schema
---------------------
{
  "description": "Human-readable scenario",
  "skill": "bva-analyzer",           // matches _invoke_skill task names
  "input_lines": [ { ...NormalizedSpendLine fields... } ],
  "extra_kwargs": {},                 // optional extra kwargs forwarded to skill
  "assertions": {
    "required_keys":  ["key1", ...], // top-level keys that must exist in output
    "forbidden_keys": ["key1", ...], // top-level keys that must NOT exist (optional)
    "<key>": <value>,                // assert output[key] == value  (bool/str/int)
    "min_<key>":  <int>,             // assert len(output[key]) >= value
    "contains_<key>": "<substr>",   // assert substr in str(output[key])
  }
}
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

from app.models import NormalizedSpendLine
from app.skills import engine as skill_engine
from app.skills.model_contextualizer import interpret_structure_heuristic


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class GoldenResult:
    fixture: str
    skill: str
    passed: bool
    failures: List[str] = field(default_factory=list)
    output: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Skill invocation dispatcher
# ---------------------------------------------------------------------------

_SKILL_DISPATCH = {
    "spend-profiler":             lambda lines, _kw: skill_engine.spend_profiler(lines),
    "bva-analyzer":               lambda lines, kw:  skill_engine.bva_analyzer(lines),
    "temporal-analyzer":          lambda lines, kw:  skill_engine.temporal_analyzer(lines),
    "payment-terms-optimizer":    lambda lines, kw:  skill_engine.payment_terms_optimizer(
                                      lines,
                                      wacc=kw.get("wacc", 0.08),
                                      industry=kw.get("industry", ""),
                                  ),
    "root-cause-analyzer":        lambda lines, kw:  skill_engine.root_cause_analyzer(
                                      kw.get("profile", {}),
                                      kw.get("peer", {}),
                                      lines,
                                  ),
    "heuristic-analyzer":         lambda lines, kw:  skill_engine.heuristic_analyzer(
                                      kw.get("profile", {}),
                                      kw.get("revenue", 0.0),
                                  ),
    "model-contextualizer":       lambda lines, kw:  interpret_structure_heuristic(
                                      kw.get("structural_summary", {})
                                  ),
}


def _invoke(skill: str, lines: List[NormalizedSpendLine], extra_kwargs: dict) -> Dict[str, Any]:
    fn = _SKILL_DISPATCH.get(skill)
    if fn is None:
        raise ValueError(f"No golden runner registered for skill '{skill}'")
    return fn(lines, extra_kwargs) or {}


# ---------------------------------------------------------------------------
# Assertion checker
# ---------------------------------------------------------------------------

def _check_assertions(output: Dict[str, Any], assertions: Dict[str, Any]) -> List[str]:
    """Return list of failure messages (empty = all pass)."""
    failures: List[str] = []

    for key in assertions.get("required_keys", []):
        if key not in output:
            failures.append(f"required key '{key}' missing from output")

    for key in assertions.get("forbidden_keys", []):
        if key in output:
            failures.append(f"forbidden key '{key}' present in output")

    for k, expected in assertions.items():
        if k in ("required_keys", "forbidden_keys"):
            continue

        if k.startswith("min_"):
            real_key = k[4:]
            val = output.get(real_key)
            if val is None:
                failures.append(f"min_{real_key}: key '{real_key}' missing")
            elif isinstance(val, (int, float)):
                # Scalar comparison — assert value >= expected
                if val < expected:
                    failures.append(f"min_{real_key}: value={val} < {expected}")
            else:
                if len(val) < expected:
                    failures.append(f"min_{real_key}: len={len(val)} < {expected}")

        elif k.startswith("contains_"):
            real_key = k[9:]
            val = str(output.get(real_key, ""))
            if expected not in val:
                failures.append(f"contains_{real_key}: '{expected}' not found in '{val[:120]}'")

        else:
            actual = output.get(k)
            if actual != expected:
                failures.append(f"assertion[{k}]: expected={expected!r}, actual={actual!r}")

    return failures


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_golden_suite(fixture_path: Path) -> GoldenResult:
    """Load a fixture file, invoke the skill, and check all assertions."""
    data = json.loads(fixture_path.read_text())
    skill = data["skill"]
    raw_lines = data.get("input_lines", [])
    extra_kwargs = data.get("extra_kwargs", {})
    assertions = data.get("assertions", {})

    lines = [NormalizedSpendLine(**row) for row in raw_lines]

    try:
        output = _invoke(skill, lines, extra_kwargs)
    except Exception as exc:
        return GoldenResult(
            fixture=fixture_path.name,
            skill=skill,
            passed=False,
            failures=[f"skill raised exception: {exc}"],
        )

    failures = _check_assertions(output, assertions)
    return GoldenResult(
        fixture=fixture_path.name,
        skill=skill,
        passed=len(failures) == 0,
        failures=failures,
        output=output,
    )
