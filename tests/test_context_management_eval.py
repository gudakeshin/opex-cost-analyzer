"""Locks the deterministic dimensions of the context-management quality eval.

Runs the real context-management machinery (slimming, budget gate, relevance
filtering, chat windowing, RAG packing) over synthetic golden fixtures and
asserts every deterministic dimension clears its threshold. CM-13 is not
exercised here (disabled under pytest).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

# Load the eval runner by file path. The top-level eval/ package is shadowed by
# tests/eval/ under pytest (tests/ is prepended to sys.path), so a normal
# `from eval.run_context_management_eval import ...` would import the wrong package.
_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "cm_eval_runner", _ROOT / "eval" / "run_context_management_eval.py"
)
cme = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
sys.modules["cm_eval_runner"] = cme  # so @dataclass can resolve cls.__module__
_spec.loader.exec_module(cme)

_PASSING_DIMS = {
    "CM-01": 7.0,
    "CM-02": 8.0,
    "CM-03": 6.0,
    "CM-04": 6.0,
    "CM-05": 8.0,
    "CM-06": 7.0,
    "CM-07": 7.0,
    "CM-08": 8.0,
    "CM-09": 7.0,
    "CM-10": 7.5,
    "CM-11": 7.0,
    "CM-12": 6.0,
}


def _raw_scores():
    fx = cme.ensure_fixtures()
    raw, skipped = cme.run_all_scorers(fx, judge_active=False)
    return raw, skipped


def test_deterministic_dimensions_clear_thresholds() -> None:
    raw, skipped = _raw_scores()
    assert "CM-13" in skipped
    for dim_id, threshold in _PASSING_DIMS.items():
        score, _ev = raw[dim_id]
        assert score >= threshold, f"{dim_id} scored {score:.1f}, expected >= {threshold}"


def test_cm05_no_hard_skip_on_oversized_chain() -> None:
    raw, _skipped = _raw_scores()
    score, ev = raw["CM-05"]
    assert score >= 8.0
    assert ev.get("skip_reason") != "token_budget_exceeded"
    assert ev.get("synthesizer_called") is True


def test_cm03_core_skills_protected_when_non_core_suffices() -> None:
    raw, _skipped = _raw_scores()
    score, ev = raw["CM-03"]
    assert score >= 6.0
    protected = sum(1 for row in ev.get("core_protection", []) if row.get("protected"))
    assert protected == len(ev.get("core_protection", []))
