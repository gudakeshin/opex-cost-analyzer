"""Synthesis payload slimming + token-budget degradation.

Covers the fix for "LLM synthesis skipped — context too large": initiative
enrichment and the 34-lever eligibility table inflated the reflect-advisory
payload to ~93% of _LLM_TOKEN_LIMIT before any document context, so real
turns intermittently tripped the hard skip at token_budget_exceeded.
"""
from __future__ import annotations

from unittest.mock import patch

from app.opar.claude_client import (
    _slim_eligible_levers,
    _slim_skill_outputs,
    _slim_sme_critique,
)
from app.opar.models import ObserveContext
from app.opar.reflect_advisory import (
    _drop_largest_to_budget,
    generate_llm_advisory_sections,
)


def _initiative(**overrides):
    base = {
        # synthesis-relevant — must survive slimming
        "category_id": "IT",
        "category_name": "IT & Telecom",
        "lever": "vendor_consolidation",
        "lever_name": "Vendor Consolidation",
        "lever_family": "commercial",
        "gross_savings": {"low": 1.0, "mid": 2.0, "high": 3.0},
        "net_savings": {"low": 0.8, "mid": 1.6, "high": 2.4},
        "confidence": "mid",
        "business_rationale": "Fragmented supplier base across 14 vendors.",
        "risks": [{"risk": "supplier pushback", "mitigation": "phased award"}],
        # UI-only enrichment — must be stripped from the LLM payload
        "execution_playbook": [{"step": "x" * 200, "owner_role": "CPO"}],
        "change_management": {"plan": "y" * 200},
        "kpis": [{"kpi": "supplier count", "target": "z" * 100}],
        "owner": {"name": "Owner", "raci": "w" * 150},
        "provenance": {"figures": ["p" * 400]},
        "affected_vendors": ["Vendor A", "Vendor B"],
        "contract_levers": ["q" * 200],
        "condition_precedents": ["r" * 80],
        "required_data_fields": ["s" * 60],
        "business_detail_enriched": True,
    }
    base.update(overrides)
    return base


def _lever(score: float, idx: int):
    return {
        "lever_id": f"lever_{idx}",
        "lever_name": f"Lever {idx}",
        "lever_family": "technology",
        "eligibility_score": score,
        "root_cause_match": False,
        "trigger_signals": ["signal"],
        "sustainability_score": 0.8,
        "bounce_back_risk": "low",
        # bulk fields — must be stripped
        "execution_playbook": [{"step": "x" * 400}],
        "condition_precedents": ["y" * 300],
    }


def test_slim_initiatives_strip_ui_enrichment() -> None:
    out = _slim_skill_outputs({
        "savings-modeler": {
            "summary": {"total": 10.0},
            "initiatives": [_initiative() for _ in range(15)],
        },
    })
    inits = out["savings-modeler"]["initiatives"]
    assert len(inits) == 12  # count cap retained
    for init in inits:
        assert init["category_name"] == "IT & Telecom"
        assert init["net_savings"]["mid"] == 1.6
        assert init["business_rationale"]
        assert init["risks"]
        for stripped in (
            "execution_playbook", "change_management", "kpis", "owner",
            "provenance", "affected_vendors", "contract_levers",
            "condition_precedents", "required_data_fields",
        ):
            assert stripped not in init
    assert out["savings-modeler"]["summary"] == {"total": 10.0}


def test_slim_eligible_levers_top8_by_score_compact_keys() -> None:
    levers = [_lever(score=i / 100, idx=i) for i in range(34)]
    slim = _slim_eligible_levers(levers)
    assert len(slim) == 8
    # highest scores kept, descending
    assert [lv["lever_id"] for lv in slim] == [f"lever_{i}" for i in range(33, 25, -1)]
    for lv in slim:
        assert "execution_playbook" not in lv
        assert "condition_precedents" not in lv
        assert lv["eligibility_score"] >= 0.26


def test_slim_compacts_lever_table_in_both_skills() -> None:
    levers = [_lever(score=0.5, idx=i) for i in range(34)]
    out = _slim_skill_outputs({
        "savings-modeler": {"initiatives": [], "eligible_levers": levers},
        "root-cause-analyzer": {
            "root_cause_findings": [{"finding": "f"}],
            "eligible_levers_summary": levers,
        },
    })
    assert len(out["savings-modeler"]["eligible_levers"]) == 8
    assert len(out["root-cause-analyzer"]["eligible_levers_summary"]) == 8
    assert "execution_playbook" not in out["root-cause-analyzer"]["eligible_levers_summary"][0]


def test_slim_sme_critique_survives_double_slim() -> None:
    full = {
        "critique_summary": {"verdicts": {"proceed": 1}},
        "initiative_critiques": [{
            "category_name": "IT",
            "lever": "consolidation",
            "sme_verdict": "probe_first",
            "evidence_maturity": "low",
            "critical_risk": "no contract register",
            "probe_questions": [
                {"question": "Is the contract up for renewal?", "why_critical": "locks timing", "extra": "bulk"},
                {"question": "second", "why_critical": "less"},
            ],
            "bulk_field": "x" * 500,
        }],
    }
    slimmed = _slim_skill_outputs({"sme-critique": full})["sme-critique"]
    assert "bulk_field" not in slimmed["initiative_critiques"][0]
    # the dedicated sme_critique_data view must be identical from either form
    assert _slim_sme_critique(full) == _slim_sme_critique(slimmed)
    assert _slim_sme_critique(slimmed)["initiative_critiques"][0]["top_probe_question"] == (
        "Is the contract up for renewal?"
    )


def test_slim_skill_outputs_idempotent() -> None:
    payload = {
        "savings-modeler": {
            "initiatives": [_initiative()],
            "eligible_levers": [_lever(score=0.5, idx=1)],
        },
        "root-cause-analyzer": {
            "root_cause_findings": [{"finding": "f"}],
            "eligible_levers_summary": [_lever(score=0.5, idx=2)],
        },
        "sme-critique": {
            "critique_summary": {},
            "initiative_critiques": [{
                "category_name": "IT", "lever": "x", "sme_verdict": "proceed",
                "evidence_maturity": "high", "critical_risk": None,
                "probe_questions": [{"question": "q", "why_critical": "w"}],
            }],
        },
        "peer-benchmarker": {"comparisons": [1, 2, 3]},
    }
    once = _slim_skill_outputs(payload)
    twice = _slim_skill_outputs(once)
    assert once == twice


def test_drop_largest_to_budget_drops_biggest_first() -> None:
    outputs = {
        "big": {"blob": "x" * 40_000},     # ~10k tokens
        "medium": {"blob": "y" * 8_000},   # ~2k tokens
        "small": {"value": 1},
    }
    kept, dropped = _drop_largest_to_budget(outputs, overshoot_tokens=5_000)
    assert dropped == ["big"]
    assert set(kept) == {"medium", "small"}

    kept, dropped = _drop_largest_to_budget(outputs, overshoot_tokens=11_000)
    assert dropped == ["big", "medium"]
    assert set(kept) == {"small"}


def test_generate_degrades_instead_of_skipping_when_over_budget() -> None:
    """An over-budget payload drops its largest skills and still synthesizes."""
    captured: dict = {}

    def fake_synthesize(user_message, **kwargs):
        captured["skill_outputs"] = kwargs.get("skill_outputs")
        return None, None

    ctx = ObserveContext(user_message="calculate value at the table", intent_class="value_bridge")
    validated = {
        "spend-profiler": {"category_profile": [], "total_spend": 1_000_000},
        # ~100k estimated tokens — alone exceeds the 80k budget
        "internal-benchmarker": {"blob": "x" * 400_000},
    }
    with patch("app.opar.reflect_advisory.ANTHROPIC_ENABLED", True), patch(
        "app.opar.reflect_advisory._iter_analysis_synthesizers",
        return_value=[fake_synthesize],
    ):
        advisory, _thinking, skip = generate_llm_advisory_sections(ctx, {}, validated)
    assert skip != "token_budget_exceeded"
    assert skip == "provider_failed"  # fake returned no raw — budget gate passed
    assert "internal-benchmarker" not in captured["skill_outputs"]
    assert "spend-profiler" in captured["skill_outputs"]


def test_available_analyses_passed_to_synthesizer() -> None:
    """Excluded skills must appear in available_analyses in the synthesizer call.

    Uses intent_class="benchmark" (in _ANALYSIS_INTENTS) so needs_llm_advisory
    returns True and the synthesizer is actually called.  query_capabilities=
    ["benchmarking"] maps peer-benchmarker into context and leaves bva-analyzer
    (only in variance_analysis) as an excluded manifest entry.
    """
    captured: dict = {}

    def fake_synthesize(user_message, **kwargs):
        captured["available_analyses"] = kwargs.get("available_analyses")
        captured["skill_outputs"] = kwargs.get("skill_outputs")
        return None, None

    ctx = ObserveContext(
        user_message="benchmark my IT spend vs peers",
        intent_class="benchmark",
        query_capabilities=["benchmarking"],
    )
    validated = {
        "spend-profiler": {"category_profile": [{"cat": "IT"}], "total_spend": 1_000_000},
        "peer-benchmarker": {"comparisons": [{"cat": "IT"}]},
        # bva-analyzer: only in variance_analysis capability — excluded for benchmarking query
        "bva-analyzer": {"variances": [{"cat": "IT"}, {"cat": "HR"}]},
    }
    with patch("app.opar.reflect_advisory.ANTHROPIC_ENABLED", True), patch(
        "app.opar.reflect_advisory._iter_analysis_synthesizers",
        return_value=[fake_synthesize],
    ):
        generate_llm_advisory_sections(ctx, {}, validated)

    aa = captured.get("available_analyses") or []
    skill_outputs = captured.get("skill_outputs") or {}
    # peer-benchmarker in context (matched benchmarking capability)
    assert "peer-benchmarker" in skill_outputs, f"skill_outputs keys={list(skill_outputs)}"
    # bva-analyzer excluded from context (wrong capability)
    assert "bva-analyzer" not in skill_outputs
    # bva-analyzer surfaced as available_analyses manifest entry
    assert any(e.get("skill") == "bva-analyzer" for e in aa), f"available_analyses={aa}"


def test_generate_skips_when_budget_unreachable() -> None:
    """If even an empty skill set exceeds the budget, keep the hard skip."""
    calls = []

    def fake_synthesize(user_message, **kwargs):
        calls.append(user_message)
        return None, None

    ctx = ObserveContext(user_message="x" * 400_000, intent_class="value_bridge")
    validated = {"spend-profiler": {"category_profile": [], "total_spend": 1_000_000}}
    with patch("app.opar.reflect_advisory.ANTHROPIC_ENABLED", True), patch(
        "app.opar.reflect_advisory._iter_analysis_synthesizers",
        return_value=[fake_synthesize],
    ):
        advisory, _thinking, skip = generate_llm_advisory_sections(ctx, {}, validated)
    assert advisory is None
    assert skip == "token_budget_exceeded"
    assert calls == []
