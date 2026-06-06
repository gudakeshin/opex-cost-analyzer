"""Tests for SME critique LLM enrichment."""
from __future__ import annotations

from app.opar.sme_intelligence import _merge_adjustments


def test_merge_adjustments_updates_verdict() -> None:
    critique = {
        "initiative_critiques": [
            {
                "category_id": "it",
                "lever": "supplier_consolidation",
                "sme_verdict": "proceed",
            }
        ]
    }
    parsed = {
        "initiative_adjustments": [
            {
                "category_id": "it",
                "lever": "supplier_consolidation",
                "adjusted_verdict": "probe_first",
                "qualification_note": "No contract register uploaded.",
                "maturity_rationale": "Benchmark gap only.",
            }
        ]
    }
    merged = _merge_adjustments(critique, parsed)
    row = merged["initiative_critiques"][0]
    assert row["sme_verdict"] == "probe_first"
    assert "contract register" in row["llm_qualification_note"]
