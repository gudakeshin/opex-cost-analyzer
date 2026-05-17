"""Phase 3 enforcement test suite.

Tests:
  - AssumptionQualityScore: scoring, Gate-2 gate, CFO override
  - Narrative provenance: tag, save, replay, reproducibility check
  - Regulatory event watcher: baseline events, forced decision, category filter
  - DAG replanner: objective function, branch decisions (WC pivot, internal-only, add-core)
  - Group 0 injection: pii-stripper/data-classifier/llm-context-builder prepended to plan
  - Observe engagement context: week + gate inference
  - New skills: assumption_register, value_to_shareholder_bridge, scenario_modeler, brsr_cobenefit_calculator
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

import pytest

from app.models import NormalizedSpendLine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_line(**kwargs) -> NormalizedSpendLine:
    defaults = dict(
        row_id=1, supplier="Test Supplier", description="Test",
        amount=100_000.0, category="it_software",
        category_id="it_software", category_name="IT Software",
        spend_date="2025-01-01", currency="INR",
    )
    defaults.update(kwargs)
    return NormalizedSpendLine(**defaults)


def _make_initiative(**kwargs) -> Dict[str, Any]:
    defaults = dict(
        category_id="logistics",
        category_name="Logistics",
        mid_case_savings=5_000_000.0,
        deduped_mid_savings=5_000_000.0,
    )
    defaults.update(kwargs)
    return defaults


# ===========================================================================
# 1. AssumptionQualityScore
# ===========================================================================

class TestAssumptionQualityScore:
    def test_source_class_peer_validated_scores_high(self):
        from app.opar.quality import AssumptionRecord, score_assumption
        a = AssumptionRecord(
            assumption_id="a1", initiative_id="i1", description="test",
            source_class="peer_validated", owner_sign_off=True,
            validation_date=datetime.now(timezone.utc).isoformat(),
            peer_p50=1_000_000.0, peer_std=100_000.0, p50=1_000_000.0,
        )
        result = score_assumption(a)
        assert result.source_score == 1.0
        assert result.composite_score >= 0.90

    def test_source_class_unknown_scores_low(self):
        from app.opar.quality import AssumptionRecord, score_assumption
        a = AssumptionRecord(
            assumption_id="a2", initiative_id="i1", description="test",
            source_class="unknown",
        )
        result = score_assumption(a)
        assert result.source_score == 0.25
        assert result.composite_score < 0.65

    def test_old_validation_date_penalised(self):
        from app.opar.quality import AssumptionRecord, score_assumption
        a = AssumptionRecord(
            assumption_id="a3", initiative_id="i1", description="test",
            source_class="internal_validated",
            validation_date="2023-01-01",  # very old
            owner_sign_off=True,
        )
        result = score_assumption(a)
        assert result.age_score <= 0.25

    def test_recent_validation_scores_high(self):
        from app.opar.quality import AssumptionRecord, score_assumption
        a = AssumptionRecord(
            assumption_id="a4", initiative_id="i1", description="test",
            source_class="peer_validated",
            validation_date=datetime.now(timezone.utc).isoformat(),
            owner_sign_off=True,
        )
        result = score_assumption(a)
        assert result.age_score >= 0.95

    def test_owner_sign_off_true_adds_full_credit(self):
        from app.opar.quality import AssumptionRecord, score_assumption
        a_on = AssumptionRecord(assumption_id="a5", initiative_id="i1", description="", source_class="expert_estimate", owner_sign_off=True)
        a_off = AssumptionRecord(assumption_id="a6", initiative_id="i1", description="", source_class="expert_estimate", owner_sign_off=False)
        assert score_assumption(a_on).sign_off_score == 1.0
        assert score_assumption(a_off).sign_off_score == 0.50

    def test_p50_within_1sd_peer_is_plausible(self):
        from app.opar.quality import AssumptionRecord, score_assumption
        a = AssumptionRecord(
            assumption_id="a7", initiative_id="i1", description="",
            source_class="peer_validated", p50=1_000_000.0,
            peer_p50=1_000_000.0, peer_std=200_000.0,
        )
        result = score_assumption(a)
        assert result.plausibility_score == 1.00

    def test_p50_outside_3sd_peer_is_implausible(self):
        from app.opar.quality import AssumptionRecord, score_assumption
        a = AssumptionRecord(
            assumption_id="a8", initiative_id="i1", description="",
            source_class="expert_estimate", p50=5_000_000.0,
            peer_p50=1_000_000.0, peer_std=200_000.0,
        )
        result = score_assumption(a)
        assert result.plausibility_score <= 0.20

    def test_gate2_blocked_when_mean_below_threshold(self):
        from app.opar.quality import AssumptionRecord, check_gate2
        poor = [
            AssumptionRecord(
                assumption_id=f"a{i}", initiative_id="i1",
                description="poor assumption", source_class="unknown",
            )
            for i in range(3)
        ]
        result = check_gate2("i1", poor)
        assert result.gate2_blocked is True
        assert result.mean_composite < 0.65

    def test_gate2_passes_with_high_quality(self):
        from app.opar.quality import AssumptionRecord, check_gate2
        good = [
            AssumptionRecord(
                assumption_id=f"a{i}", initiative_id="i1",
                description="good assumption",
                source_class="peer_validated",
                owner_sign_off=True,
                validation_date=datetime.now(timezone.utc).isoformat(),
                peer_p50=1_000_000.0, peer_std=100_000.0, p50=1_000_000.0,
            )
            for i in range(3)
        ]
        result = check_gate2("i1", good)
        assert result.gate2_blocked is False
        assert result.mean_composite >= 0.65

    def test_cfo_override_clears_block(self):
        from app.opar.quality import AssumptionRecord, check_gate2
        poor = [
            AssumptionRecord(assumption_id="a1", initiative_id="i1", description="", source_class="unknown")
        ]
        result = check_gate2("i1", poor, override_by="CFO Pallav")
        assert result.gate2_blocked is False
        assert result.override_recorded is True
        assert result.override_by == "CFO Pallav"

    def test_no_assumptions_blocks_gate2(self):
        from app.opar.quality import check_gate2
        result = check_gate2("i1", [])
        assert result.gate2_blocked is True

    def test_assumptions_from_initiative_string_list(self):
        from app.opar.quality import assumptions_from_initiative
        init = {"category_id": "logistics", "assumptions": ["assumption A", "assumption B"]}
        records = assumptions_from_initiative(init)
        assert len(records) == 2
        assert all(r.source_class == "rule_of_thumb" for r in records)

    def test_assumptions_from_initiative_dict_list(self):
        from app.opar.quality import assumptions_from_initiative
        init = {
            "category_id": "logistics",
            "assumptions": [
                {"assumption_id": "a1", "description": "peer data", "source_class": "peer_validated",
                 "p10": 800, "p50": 1000, "p90": 1300, "owner_sign_off": True}
            ]
        }
        records = assumptions_from_initiative(init)
        assert len(records) == 1
        assert records[0].source_class == "peer_validated"
        assert records[0].owner_sign_off is True

    def test_empty_initiative_gets_synthetic_fallback(self):
        from app.opar.quality import assumptions_from_initiative
        records = assumptions_from_initiative({})
        assert len(records) == 1
        assert records[0].source_class == "rule_of_thumb"


# ===========================================================================
# 2. Narrative Provenance
# ===========================================================================

class TestNarrativeProvenance:
    def setup_method(self):
        self._tmpdir = tempfile.mkdtemp()
        import app.opar.provenance as prov_mod
        self._orig_dir = prov_mod._PROVENANCE_DIR
        prov_mod._PROVENANCE_DIR = Path(self._tmpdir) / "provenance"

    def teardown_method(self):
        import app.opar.provenance as prov_mod
        prov_mod._PROVENANCE_DIR = self._orig_dir
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_build_provenance_tag_is_deterministic(self):
        from app.opar.provenance import build_provenance_tag
        tag1 = build_provenance_tag(["a", "b"], "hello", "claude-sonnet-4-6", seed=0)
        tag2 = build_provenance_tag(["b", "a"], "hello", "claude-sonnet-4-6", seed=0)
        # data_slice is sorted
        assert tag1["data_slice"] == tag2["data_slice"]
        assert tag1["prompt_hash"] == tag2["prompt_hash"]

    def test_prompt_hash_changes_with_prompt(self):
        from app.opar.provenance import build_provenance_tag
        t1 = build_provenance_tag([], "prompt A", "model-x")
        t2 = build_provenance_tag([], "prompt B", "model-x")
        assert t1["prompt_hash"] != t2["prompt_hash"]

    def test_tag_narrative_splits_sentences(self):
        from app.opar.provenance import tag_narrative, build_provenance_tag
        tag = build_provenance_tag(["skill-a"], "q", "model-x")
        text = "First sentence. Second sentence. Third one."
        tagged = tag_narrative(text, tag)
        assert len(tagged) == 3
        assert tagged[0]["sentence"] == "First sentence."

    def test_save_and_replay_snapshot(self):
        from app.opar.provenance import save_snapshot, replay_snapshot, tag_narrative, build_provenance_tag
        tag = build_provenance_tag(["sp"], "q", "model-x")
        tagged = tag_narrative("Hello world. This is a test.", tag)
        save_snapshot("eng001", "turn001", tagged)
        replayed = replay_snapshot("eng001", "turn001")
        assert "Hello world." in replayed
        assert "This is a test." in replayed

    def test_load_snapshot_returns_records(self):
        from app.opar.provenance import save_snapshot, load_snapshot, tag_narrative, build_provenance_tag
        tag = build_provenance_tag(["sp"], "q", "model-x")
        tagged = tag_narrative("Sentence one. Sentence two.", tag)
        save_snapshot("eng002", "turn002", tagged)
        records = load_snapshot("eng002", "turn002")
        assert len(records) == 2
        assert records[0]["engagement_id"] == "eng002"

    def test_verify_reproducibility_match(self):
        from app.opar.provenance import save_snapshot, verify_reproducibility, tag_narrative, build_provenance_tag
        narrative = "The savings are real. The plan is solid."
        tag = build_provenance_tag(["sp"], "q", "model-x")
        tagged = tag_narrative(narrative, tag)
        save_snapshot("eng003", "turn003", tagged)
        result = verify_reproducibility("eng003", "turn003", narrative)
        assert result["match"] is True
        assert result["diff_count"] == 0

    def test_verify_reproducibility_mismatch(self):
        from app.opar.provenance import save_snapshot, verify_reproducibility, tag_narrative, build_provenance_tag
        original = "The savings are real. The plan is solid."
        tag = build_provenance_tag(["sp"], "q", "model-x")
        tagged = tag_narrative(original, tag)
        save_snapshot("eng004", "turn004", tagged)
        regenerated = "The savings are different. The plan changed."
        result = verify_reproducibility("eng004", "turn004", regenerated)
        assert result["match"] is False
        assert result["diff_count"] > 0

    def test_record_llm_narrative_convenience(self):
        from app.opar.provenance import record_llm_narrative, load_snapshot
        tag = record_llm_narrative(
            "Initiative A saves 10 Cr. Initiative B saves 5 Cr.",
            engagement_id="eng005",
            turn_id="turn005",
            skill_outputs_used=["spend-profiler", "savings-modeler"],
            prompt_text="Generate a narrative",
            model_version="claude-sonnet-4-6",
        )
        assert tag["model_version"] == "claude-sonnet-4-6"
        records = load_snapshot("eng005", "turn005")
        assert len(records) == 2


# ===========================================================================
# 3. Regulatory Event Watcher
# ===========================================================================

class TestRegWatcher:
    def test_baseline_events_exist(self):
        from app.services.reg_watcher import get_active_events
        events = get_active_events()
        assert len(events) >= 3  # at least the built-in baseline

    def test_high_severity_filter(self):
        from app.services.reg_watcher import get_active_events, SEVERITY_HIGH
        events = get_active_events(severity_filter=SEVERITY_HIGH)
        assert all(e["severity"] == SEVERITY_HIGH for e in events)

    def test_category_filter_returns_relevant(self):
        from app.services.reg_watcher import get_active_events
        events = get_active_events(categories=["finance"])
        # RBI event should match finance
        assert any("RBI" in e.get("source", "") for e in events)

    def test_category_filter_excludes_irrelevant(self):
        from app.services.reg_watcher import get_active_events
        events = get_active_events(categories=["nonexistent_category_xyz"])
        assert len(events) == 0

    def test_surface_at_reflect_gate_forced_decision(self):
        from app.services.reg_watcher import surface_at_reflect_gate
        # "professional_services" matches GST event
        result = surface_at_reflect_gate(["professional_services"], engagement_week=3)
        assert result["forced_decision"] is True
        assert result["gate_week"] == 3
        assert "decision_prompt" in result

    def test_surface_at_reflect_gate_no_match(self):
        from app.services.reg_watcher import surface_at_reflect_gate
        result = surface_at_reflect_gate(["nonexistent_cat_xyz"], engagement_week=2)
        assert result["forced_decision"] is False

    def test_add_event_persisted(self):
        import tempfile, shutil
        from app.services import reg_watcher as rw
        orig = rw._EVENTS_PATH
        tmpdir = Path(tempfile.mkdtemp())
        rw._EVENTS_PATH = tmpdir / "reg_events.jsonl"
        try:
            ev = rw.add_event(
                "TEST_001", "GST", "Test event", "Test summary",
                "2026-06-01", rw.SEVERITY_HIGH, ["it_software"],
            )
            assert ev["event_id"] == "TEST_001"
            stored = rw._load_stored_events()
            assert any(e["event_id"] == "TEST_001" for e in stored)
        finally:
            rw._EVENTS_PATH = orig
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_since_date_filter(self):
        from app.services.reg_watcher import get_active_events
        events_future = get_active_events(since_date="2099-01-01")
        assert len(events_future) == 0


# ===========================================================================
# 4. DAG Replanner
# ===========================================================================

class TestDagReplanner:
    def _make_ctx(self, engagement_week: int = 4) -> Any:
        from app.opar.models import ObserveContext
        return ObserveContext(
            user_message="test",
            intent_class="value_bridge",
            has_tabular_spend=True,
            has_annual_revenue=True,
            session_id="sess1",
            user_id="usr1",
            engagement_week=engagement_week,
        )

    def _make_plan(self, skills=None) -> Any:
        from app.opar.models import ExecutionPlan, SkillTask
        skills = skills or ["spend-profiler"]
        tasks = [SkillTask(skill_name=s, inputs={}, depends_on=[], parallel_group=0) for s in skills]
        return ExecutionPlan(tasks=tasks, total_skills=len(tasks), parallel_groups=1, user_summary="test", estimated_duration="")

    def test_replanner_returns_empty_log_when_no_branch(self):
        from app.opar.plan import replan
        ctx = self._make_ctx()
        plan = self._make_plan()
        validated = {
            "spend-profiler": {"total_spend": 1_000_000.0, "category_profile": []},
            "peer-benchmarker": {"comparisons": [{"category_id": "a"}] * 5,
                                  "benchmark_dataset": {"specificity_score": 0.85}},
            "internal-benchmarker": {},
            "value-bridge-calculator": {},
            "savings-modeler": {},
            "root-cause-analyzer": {},
        }
        _, log = replan(ctx, validated, plan)
        assert log == []

    def test_replanner_wc_branch_triggers(self):
        from app.opar.plan import replan
        ctx = self._make_ctx()
        plan = self._make_plan()
        # WC ratio > 2× opex requires total_spend for opex
        validated = {
            "spend-profiler": {"total_spend": 100_000.0, "category_profile": []},
            "payment-terms-optimizer": {
                "opportunities": [{"working_capital_release": 300_000.0}]  # 3× opex
            },
        }
        new_plan, log = replan(ctx, validated, plan)
        assert any(d["decision"] == "wc_deep_dive" for d in log)
        skill_names = {t.skill_name for t in new_plan.tasks}
        assert "payment-terms-optimizer" in skill_names

    def test_replanner_low_peer_evidence_branch(self):
        from app.opar.plan import replan
        ctx = self._make_ctx()
        plan = self._make_plan(["spend-profiler", "peer-benchmarker"])
        validated = {
            "peer-benchmarker": {
                "comparisons": [{"category_id": "a"}],
                "benchmark_dataset": {"specificity_score": 0.10},  # very low
            }
        }
        new_plan, log = replan(ctx, validated, plan)
        assert any(d["decision"] == "internal_only" for d in log)
        skill_names = {t.skill_name for t in new_plan.tasks}
        assert "peer-benchmarker" not in skill_names

    def test_replanner_add_core_skill_branch(self):
        from app.opar.plan import replan
        ctx = self._make_ctx()
        # Plan missing most core skills → low opportunity coverage
        plan = self._make_plan(["spend-profiler"])
        validated = {"spend-profiler": {"total_spend": 1_000_000.0}}  # only 1/6 filled
        new_plan, log = replan(ctx, validated, plan)
        assert any(d["decision"] == "add_core_skill" for d in log)

    def test_replanner_log_records_engagement_week(self):
        from app.opar.plan import replan
        ctx = self._make_ctx(engagement_week=7)
        plan = self._make_plan()
        validated = {
            "spend-profiler": {"total_spend": 100_000.0},
            "payment-terms-optimizer": {"opportunities": [{"working_capital_release": 300_000.0}]},
        }
        _, log = replan(ctx, validated, plan)
        for entry in log:
            assert entry["engagement_week"] == 7


# ===========================================================================
# 5. Group 0 Injection
# ===========================================================================

class TestGroup0Injection:
    def _make_ctx(self, has_tabular_spend=True) -> Any:
        from app.opar.models import ObserveContext
        return ObserveContext(
            user_message="analyze spend",
            intent_class="benchmark",
            has_tabular_spend=has_tabular_spend,
            session_id="s1", user_id="u1",
        )

    def test_group0_injected_when_tabular_spend(self):
        from app.opar.plan import plan
        ctx = self._make_ctx(has_tabular_spend=True)
        # Need spend profile ready for benchmark to produce tasks
        ctx = ctx.model_copy(update={"spend_profile_ready": True, "data_quality_score": 0.8})
        exec_plan = plan(ctx)
        skill_names = [t.skill_name for t in exec_plan.tasks]
        assert "pii-stripper" in skill_names
        assert "data-classifier" in skill_names
        assert "llm-context-builder" in skill_names

    def test_group0_not_injected_without_tabular_spend(self):
        from app.opar.plan import plan
        ctx = self._make_ctx(has_tabular_spend=False)
        ctx = ctx.model_copy(update={"spend_profile_ready": False, "uploaded_file_ids": []})
        exec_plan = plan(ctx)
        skill_names = [t.skill_name for t in exec_plan.tasks]
        assert "pii-stripper" not in skill_names

    def test_group0_parallel_groups_correct(self):
        from app.opar.plan import _inject_group0
        from app.opar.models import ObserveContext, SkillTask
        ctx = ObserveContext(user_message="test", has_tabular_spend=True, session_id="s1", user_id="u1")
        existing = [SkillTask(skill_name="spend-profiler", inputs={}, depends_on=[], parallel_group=0)]
        result = _inject_group0(existing, ctx)
        # pii-stripper should be group 0, data-classifier group 1, llm-context-builder group 2
        group0_skills = {t.skill_name: t.parallel_group for t in result}
        assert group0_skills["pii-stripper"] == 0
        assert group0_skills["data-classifier"] == 1
        assert group0_skills["llm-context-builder"] == 2

    def test_group0_not_injected_twice(self):
        from app.opar.plan import _inject_group0
        from app.opar.models import ObserveContext, SkillTask
        ctx = ObserveContext(user_message="test", has_tabular_spend=True, session_id="s1", user_id="u1")
        existing = [
            SkillTask(skill_name="pii-stripper", inputs={}, depends_on=[], parallel_group=0),
            SkillTask(skill_name="data-classifier", inputs={}, depends_on=[], parallel_group=1),
            SkillTask(skill_name="llm-context-builder", inputs={}, depends_on=[], parallel_group=2),
            SkillTask(skill_name="spend-profiler", inputs={}, depends_on=[], parallel_group=3),
        ]
        result = _inject_group0(existing, ctx)
        pii_count = sum(1 for t in result if t.skill_name == "pii-stripper")
        assert pii_count == 1


# ===========================================================================
# 6. Observe — engagement context
# ===========================================================================

class TestObserveEngagementContext:
    def test_infer_engagement_week_explicit(self):
        from app.opar.observe import _infer_engagement_week
        manifest = {"engagement_week": 7}
        week = _infer_engagement_week(manifest, [])
        assert week == 7

    def test_infer_engagement_week_clamp(self):
        from app.opar.observe import _infer_engagement_week
        manifest = {"engagement_week": 99}
        week = _infer_engagement_week(manifest, [])
        assert week == 12

    def test_infer_engagement_week_from_turn_count(self):
        from app.opar.observe import _infer_engagement_week
        # 6 non-empty turns → (6 // 3) + 1 = 3
        turns = [{"turn": i} for i in range(6)]
        week = _infer_engagement_week({}, turns)
        assert week == 3

    def test_infer_engagement_week_default(self):
        from app.opar.observe import _infer_engagement_week
        week = _infer_engagement_week({}, [])
        assert week == 1

    def test_decision_gate_mapping(self):
        from app.opar.observe import _infer_decision_gate
        assert _infer_decision_gate(1, "benchmark") == "pre-Gate-1"
        assert _infer_decision_gate(2, "benchmark") == "Gate-1"
        assert _infer_decision_gate(5, "value_bridge") == "Gate-2"
        assert _infer_decision_gate(9, "business_case") == "Gate-3"
        assert _infer_decision_gate(11, "business_case") == "Gate-4"


# ===========================================================================
# 7. New Skills
# ===========================================================================

class TestAssumptionRegisterSkill:
    def _lines(self, n=5):
        return [_make_line(row_id=i, amount=float(i * 100_000)) for i in range(1, n + 1)]

    def test_three_point_method_produces_p10_p50_p90(self):
        from app.skills.engine import assumption_register
        init = [_make_initiative()]
        result = assumption_register(self._lines(), init, method="three_point")
        assert result["initiative_count"] == 1
        r = result["register"][0]
        assert r["p10"] < r["p50"] < r["p90"]
        assert r["method"] == "three_point"

    def test_mc_method_produces_ranges(self):
        from app.skills.engine import assumption_register
        init = [_make_initiative()]
        result = assumption_register(self._lines(), init, method="mc")
        r = result["register"][0]
        assert r["p10"] < r["p90"]

    def test_empty_initiatives_returns_empty_register(self):
        from app.skills.engine import assumption_register
        result = assumption_register(self._lines(), [])
        assert result["initiative_count"] == 0
        assert result["p50_total"] == 0.0

    def test_portfolio_totals_computed(self):
        from app.skills.engine import assumption_register
        init = [_make_initiative(mid_case_savings=2_000_000.0), _make_initiative(category_id="energy", mid_case_savings=1_000_000.0)]
        result = assumption_register(self._lines(), init)
        assert result["p50_total"] > 0
        assert result["p10_total"] < result["p50_total"] < result["p90_total"]

    def test_summary_string_present(self):
        from app.skills.engine import assumption_register
        result = assumption_register(self._lines(), [_make_initiative()])
        assert "initiative(s)" in result["summary"]


class TestValueToShareholderBridge:
    def _lines(self, n=10):
        return [_make_line(row_id=i, amount=500_000.0) for i in range(1, n + 1)]

    def test_basic_output_structure(self):
        from app.skills.engine import value_to_shareholder_bridge
        init = [_make_initiative()]
        result = value_to_shareholder_bridge(self._lines(), init, annual_revenue=1_000_000_000.0)
        assert "delta_ebitda" in result
        assert "delta_roce_pp" in result
        assert "delta_eps" in result
        assert "delta_fcf" in result
        assert "delta_equity_value" in result

    def test_delta_ebitda_equals_savings(self):
        from app.skills.engine import value_to_shareholder_bridge
        savings = 10_000_000.0
        init = [_make_initiative(mid_case_savings=savings)]
        result = value_to_shareholder_bridge(self._lines(), init, annual_revenue=500_000_000.0)
        assert result["delta_ebitda"] == pytest.approx(savings, rel=0.01)

    def test_delta_ebitda_bps_computed(self):
        from app.skills.engine import value_to_shareholder_bridge
        result = value_to_shareholder_bridge(
            self._lines(), [_make_initiative(mid_case_savings=10_000_000.0)],
            annual_revenue=1_000_000_000.0,
        )
        # 10M / 1000M = 100 bps
        assert result["delta_ebitda_bps"] == pytest.approx(100.0, rel=0.05)

    def test_per_initiative_breakdown(self):
        from app.skills.engine import value_to_shareholder_bridge
        init = [_make_initiative(), _make_initiative(category_id="energy")]
        result = value_to_shareholder_bridge(self._lines(), init, annual_revenue=500_000_000.0)
        assert len(result["per_initiative"]) == 2

    def test_no_initiatives_returns_zero_deltas(self):
        from app.skills.engine import value_to_shareholder_bridge
        result = value_to_shareholder_bridge(self._lines(), [], annual_revenue=500_000_000.0)
        assert result["total_mid_savings"] == 0.0


class TestScenarioModeler:
    def _lines(self, n=5):
        return [_make_line(row_id=i, amount=200_000.0) for i in range(1, n + 1)]

    def test_returns_six_scenarios(self):
        from app.skills.engine import scenario_modeler
        result = scenario_modeler(self._lines(), [], base_savings=10_000_000.0)
        assert len(result["scenarios"]) == 6

    def test_scenario_ids_present(self):
        from app.skills.engine import scenario_modeler
        result = scenario_modeler(self._lines(), [], base_savings=5_000_000.0)
        ids = {s["scenario_id"] for s in result["scenarios"]}
        assert ids == {"base", "fx_stress", "wage_inflation", "commodity_spike", "execution_slip", "upside"}

    def test_execution_slip_is_lowest_downside(self):
        from app.skills.engine import scenario_modeler
        result = scenario_modeler(self._lines(), [], base_savings=10_000_000.0)
        slip = next(s for s in result["scenarios"] if s["scenario_id"] == "execution_slip")
        assert slip["savings_impact"] == result["downside_floor"]

    def test_upside_exceeds_base(self):
        from app.skills.engine import scenario_modeler
        init = [_make_initiative(p90=15_000_000.0, p50=10_000_000.0)]
        result = scenario_modeler(self._lines(), init)
        base = next(s for s in result["scenarios"] if s["scenario_id"] == "base")
        upside = next(s for s in result["scenarios"] if s["scenario_id"] == "upside")
        assert upside["savings_impact"] >= base["savings_impact"]

    def test_npv_all_positive_for_positive_savings(self):
        from app.skills.engine import scenario_modeler
        result = scenario_modeler(self._lines(), [], base_savings=5_000_000.0)
        assert all(s["npv"] > 0 for s in result["scenarios"])

    def test_macro_sensitivity_rating_present(self):
        from app.skills.engine import scenario_modeler
        result = scenario_modeler(self._lines(), [], base_savings=5_000_000.0)
        assert result["macro_sensitivity_rating"] in ("high", "medium", "low")


class TestBrsrCobenefitCalculator:
    def _lines(self, n=5):
        return [_make_line(row_id=i, amount=100_000.0) for i in range(1, n + 1)]

    def test_basic_output_structure(self):
        from app.skills.engine import brsr_cobenefit_calculator
        init = [_make_initiative(category_id="logistics", p50=10_000_000.0)]
        result = brsr_cobenefit_calculator(self._lines(), init)
        assert "cobenefit_items" in result
        assert "portfolio_totals" in result
        assert "brsr_principles_addressed" in result

    def test_logistics_maps_to_p6_scope3(self):
        from app.skills.engine import brsr_cobenefit_calculator
        init = [_make_initiative(category_id="logistics", p50=10_000_000.0)]
        result = brsr_cobenefit_calculator(self._lines(), init)
        item = result["cobenefit_items"][0]
        assert item["brsr_principle"] == "P6"
        assert item["delta_scope3_tco2e"] > 0

    def test_energy_maps_to_scope2(self):
        from app.skills.engine import brsr_cobenefit_calculator
        init = [_make_initiative(category_id="energy", p50=10_000_000.0)]
        result = brsr_cobenefit_calculator(self._lines(), init)
        item = result["cobenefit_items"][0]
        assert item["delta_scope2_tco2e"] > 0

    def test_portfolio_totals_sum_items(self):
        from app.skills.engine import brsr_cobenefit_calculator
        init = [
            _make_initiative(category_id="logistics", p50=10_000_000.0),
            _make_initiative(category_id="energy", p50=5_000_000.0),
        ]
        result = brsr_cobenefit_calculator(self._lines(), init)
        scope3_sum = sum(i["delta_scope3_tco2e"] for i in result["cobenefit_items"])
        assert result["portfolio_totals"]["delta_scope3_tco2e"] == pytest.approx(scope3_sum, rel=0.01)

    def test_empty_initiatives_returns_zeros(self):
        from app.skills.engine import brsr_cobenefit_calculator
        result = brsr_cobenefit_calculator(self._lines(), [])
        assert result["portfolio_totals"]["delta_scope2_tco2e"] == 0.0

    def test_principles_addressed_list_unique(self):
        from app.skills.engine import brsr_cobenefit_calculator
        init = [
            _make_initiative(category_id="logistics", p50=5_000_000.0),
            _make_initiative(category_id="energy", p50=5_000_000.0),
        ]
        result = brsr_cobenefit_calculator(self._lines(), init)
        principles = result["brsr_principles_addressed"]
        assert len(principles) == len(set(principles))

    def test_emission_factors_documented(self):
        from app.skills.engine import brsr_cobenefit_calculator
        result = brsr_cobenefit_calculator(self._lines(), [])
        assert "scope2_tco2e_per_cr" in result["emission_factors"]
        assert "note" in result["emission_factors"]
