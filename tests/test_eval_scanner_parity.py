"""Parity guard for the feature-eval structural scanners.

The feature eval (eval/run_feature_eval.py) inspects source layout with regexes.
When the code is refactored — reflect.py split into reflect*.py modules, the
global Limiter moved into app/ratelimit.py, dispatch handlers turned into thin
engine delegators — those scanners can silently start emitting FALSE NEGATIVES
while the functionality is fully present.

These tests assert the three previously-drifted dimensions PASS against the live
tree, so a future move of the same symbols fails loudly here instead of quietly
dragging down the readiness score.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

# Ensure project root is on sys.path so the eval module's own `app.*` imports
# resolve. We load the eval scanner by file path (below) rather than as
# `eval.run_feature_eval`, because under pytest the top-level `eval` name is
# already bound to a different package, which shadows the dotted import.
_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_FEATURE_EVAL_PATH = _PROJECT_ROOT / "eval" / "run_feature_eval.py"


def _load_feature_eval():
    try:
        spec = importlib.util.spec_from_file_location(
            "feature_eval_under_test", _FEATURE_EVAL_PATH
        )
        module = importlib.util.module_from_spec(spec)
        # Register before exec so @dataclass can resolve cls.__module__.
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    except Exception as exc:  # pragma: no cover - environment guard
        pytest.skip(f"Cannot load run_feature_eval.py: {exc}")


def test_sp_02_recognizes_engine_delegators() -> None:
    """Thin 2-line dispatch handlers that delegate to app.skills.engine count
    as implemented (not stubs)."""
    mod = _load_feature_eval()
    result = mod.score_sp_02(_PROJECT_ROOT)
    assert result.passed, (
        f"SP_02 regressed to {result.raw_score:.2f}: {result.finding_detail}"
    )


def test_opar_03_scans_reflect_package() -> None:
    """Quality-gate symbols live across the reflect*.py package, not reflect.py
    alone."""
    mod = _load_feature_eval()
    result = mod.score_opar_03(_PROJECT_ROOT)
    assert result.passed, (
        f"OPAR_03 regressed to {result.raw_score:.2f}: {result.finding_detail}"
    )


def test_infra_03_detects_dedicated_ratelimit_module() -> None:
    """A global Limiter() instantiated in app/ratelimit.py and attached via
    app.state.limiter counts as a global limiter."""
    mod = _load_feature_eval()
    result = mod.score_infra_03(_PROJECT_ROOT)
    assert result.passed, (
        f"INFRA_03 regressed to {result.raw_score:.2f}: {result.finding_detail}"
    )
