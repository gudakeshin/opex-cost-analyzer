"""Locks the deterministic dimensions of the document-processing quality eval.

Runs the real ingestion pipeline (parse -> schema -> chunk -> retrieve) over the
synthetic golden fixtures and asserts every deterministic dimension clears its
threshold. The DP-07 LLM judge is not exercised here (disabled under pytest).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

# Load the eval runner by file path. The top-level eval/ package is shadowed by
# tests/eval/ under pytest (tests/ is prepended to sys.path), so a normal
# `from eval.run_document_processing_eval import ...` would import the wrong package.
_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "dp_eval_runner", _ROOT / "eval" / "run_document_processing_eval.py"
)
dpe = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
sys.modules["dp_eval_runner"] = dpe  # so @dataclass can resolve cls.__module__
_spec.loader.exec_module(dpe)


def _obs():
    specs = dpe.ensure_fixtures()
    return dpe.process_fixtures(specs, judge=False)


def test_deterministic_dimensions_clear_thresholds() -> None:
    obs = _obs()
    assert dpe.score_dp01_parse_success(obs)[0] >= 9.0
    assert dpe.score_dp02_schema_role_accuracy(obs)[0] >= 7.0
    assert dpe.score_dp03_sheet_selection(obs)[0] >= 7.0
    assert dpe.score_dp04_normalization_fidelity(obs)[0] >= 7.0
    assert dpe.score_dp05_chunk_structure(obs)[0] >= 7.0
    assert dpe.score_dp06_retrieval_precision(obs)[0] >= 6.0
    assert dpe.score_dp08_quality_flag_capture(obs)[0] >= 7.0


def test_malformed_fixture_raises_zero_spend_warning() -> None:
    obs = _obs()
    malformed = obs["malformed.csv"]
    assert malformed["quality"]["zero_spend_warning"] is True
    assert malformed["warnings"]


def test_clean_fixtures_have_no_false_warnings() -> None:
    obs = _obs()
    for name in ("clean_spend.csv", "multi_sheet.xlsx", "spend.json"):
        assert obs[name]["quality"]["zero_spend_warning"] is False
        assert not obs[name].get("warnings")
