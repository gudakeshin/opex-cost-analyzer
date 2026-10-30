"""Wraps eval/run_llm_judge_eval.py (the LJ-01..05 analytical-quality judge) into
the llm_judge-marked suite.

The structural evals (run_feature_eval / run_analysis_quality_eval) only validate
schema and output integrity — they explicitly defer analytical correctness to this
judge. Until now the judge existed only as a standalone CLI that produced no
committed output, so content quality was never tracked in CI. This test plugs it
into the existing nightly job (`pytest tests/eval/ -m llm_judge` in ci.yml), which
already provides the ANTHROPIC_API_KEY secret and RUN_LLM_JUDGE=1.

Gating mirrors the other llm_judge tests exactly: without RUN_LLM_JUDGE=1 and an
API key the test skips, so the deterministic `-m "not llm_judge"` unit run is
unaffected. Running it also writes eval/llm_judge_report.md + llm_judge_scores.json,
which is the baseline the plan calls for committing.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_LJ_SCRIPT = _PROJECT_ROOT / "eval" / "run_llm_judge_eval.py"


@pytest.mark.llm_judge
def test_llm_judge_analytical_quality_above_threshold() -> None:
    """LJ-01..05 average must clear the judge's PASS_THRESHOLD (7.0) on the 5
    golden scenarios."""
    if os.environ.get("RUN_LLM_JUDGE") != "1":
        pytest.skip("Set RUN_LLM_JUDGE=1 to run live LLM judge tests")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY required for the analytical-quality LLM judge")
    assert _LJ_SCRIPT.exists(), f"LLM judge script missing: {_LJ_SCRIPT}"

    proc = subprocess.run(
        [sys.executable, str(_LJ_SCRIPT)],
        cwd=str(_PROJECT_ROOT),
        env={**os.environ, "PYTHONPATH": str(_PROJECT_ROOT)},
        capture_output=True,
        text=True,
        timeout=900,
    )
    # Exit-code contract documented in run_llm_judge_eval.py:
    #   0 = all dimensions >= 7.0
    #   1 = one or more dimensions below threshold
    #   2 = critical error (no API key / pipeline load failure)
    if proc.returncode == 2:
        pytest.skip(f"LLM judge could not run:\n{proc.stdout}\n{proc.stderr}")
    assert proc.returncode == 0, (
        "LJ-01..05 analytical quality below threshold (7.0):\n"
        f"{proc.stdout}\n{proc.stderr}"
    )
