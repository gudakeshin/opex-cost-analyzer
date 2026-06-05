"""Tests for app/skills/engine/sme_critique.py — deterministic rules engine."""
import pytest

from app.skills.engine.sme_critique import (
    _build_probe_questions,
    _check_double_count,
    _score_evidence_maturity,
    sme_critique_analyzer,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_initiative(**kwargs):
    base = {
        "category_id": "it_software",
        "category_name": "IT Software",
        "lever": "supplier_consolidation",
        "lever_name": "Supplier Consolidation",
        "confidence": "medium",
        "annualized_run_rate_savings": 100,
        "net_savings": {"total_3yr": 300},
    }
    base.update(kwargs)
    return base


def _empty_inputs():
    return (
        {"initiatives": []},  # savings_model
        {"category_profile": []},  # spend_profile
        {"comparisons": []},  # benchmarks
        {"root_cause_findings": []},  # root_causes
        {"contracts": []},  # contract_lifecycle
    )


# ---------------------------------------------------------------------------
# _score_evidence_maturity
# ---------------------------------------------------------------------------

class TestScoreEvidenceMaturity:
    def _call(self, initiative, contracts=None, suppliers=None, signals=None):
        return _score_evidence_maturity(
            initiative,
            contracts_by_category=contracts or {},
            supplier_counts=suppliers or {},
            root_cause_signals_by_category=signals or {},
        )

    def test_hypothesis_zero_signals(self):
        init = _make_initiative()
        label, score = self._call(init)
        assert label == "hypothesis"
        assert score == 0

    def test_indicative_two_signals(self):
        init = _make_initiative(confidence="high")
        label, score = self._call(
            init,
            contracts={"it_software": [{"expiry": "2026-01"}]},
        )
        assert label == "indicative"
        assert score == 2

    def test_supported_three_signals(self):
        init = _make_initiative(confidence="high")
        label, score = self._call(
            init,
            contracts={"it_software": [{}]},
            suppliers={"it_software": 5},
        )
        assert label == "supported"
        assert score == 3

    def test_validated_all_four_signals(self):
        init = _make_initiative(confidence="high")
        label, score = self._call(
            init,
            contracts={"it_software": [{}]},
            suppliers={"it_software": 3},
            signals={"it_software": 2},
        )
        assert label == "validated"
        assert score == 4

    def test_supplier_threshold_exactly_one_not_counted(self):
        init = _make_initiative()
        label, score = self._call(init, suppliers={"it_software": 1})
        # supplier_counts > 1 required; exactly 1 doesn't add signal
        assert score == 0

    def test_supplier_threshold_two_counted(self):
        init = _make_initiative()
        label, score = self._call(init, suppliers={"it_software": 2})
        assert score == 1

    def test_root_cause_threshold_one_signal_not_counted(self):
        init = _make_initiative()
        label, score = self._call(init, signals={"it_software": 1})
        # ≥2 required
        assert score == 0

    def test_root_cause_threshold_two_signals_counted(self):
        init = _make_initiative()
        label, score = self._call(init, signals={"it_software": 2})
        assert score == 1

    def test_category_id_is_lowercased_lookup(self):
        init = _make_initiative(category_id="IT_Software")
        # The function uses category_id as-is; contracts keyed lowercase won't match
        label, score = self._call(
            init, contracts={"it_software": [{}]}
        )
        # category_id from initiative is "IT_Software", contracts key is "it_software" → no match
        assert score == 0


# ---------------------------------------------------------------------------
# _build_probe_questions
# ---------------------------------------------------------------------------

class TestBuildProbeQuestions:
    def _call(self, initiative, **kwargs):
        defaults = {
            "has_contract_data": False,
            "has_supplier_data": False,
            "benchmark_specificity": 0.5,
            "has_cost_center_split": False,
            "has_prior_year_data": False,
            "has_po_coverage": False,
            "has_transaction_volume": False,
            "has_spec_data": False,
        }
        defaults.update(kwargs)
        return _build_probe_questions(initiative, **defaults)

    def test_supplier_consolidation_no_contract_data_fires(self):
        init = _make_initiative(lever="supplier_consolidation")
        probes = self._call(init)
        assert any("contract" in p["question"].lower() or "contract" in p["data_to_request"].lower()
                   for p in probes)

    def test_supplier_consolidation_no_supplier_data_fires(self):
        init = _make_initiative(lever="supplier_consolidation")
        probes = self._call(init, has_contract_data=True)
        assert any("vendor" in p["question"].lower() or "supplier" in p["question"].lower()
                   for p in probes)

    def test_strategic_sourcing_low_specificity_fires(self):
        init = _make_initiative(lever="strategic_sourcing")
        probes = self._call(init, has_contract_data=True, benchmark_specificity=0.4)
        assert any("benchmark" in p["question"].lower() for p in probes)

    def test_strategic_sourcing_high_specificity_no_probe(self):
        init = _make_initiative(lever="strategic_sourcing")
        probes = self._call(init, has_contract_data=True, benchmark_specificity=0.75)
        # No benchmark probe when specificity >= 0.60
        assert not any("benchmark" in p["question"].lower() for p in probes)

    def test_demand_management_no_cost_center_fires(self):
        init = _make_initiative(lever="demand_management")
        probes = self._call(init)
        assert any("discretionary" in p["question"].lower() or "cost-centre" in p["data_to_request"].lower()
                   for p in probes)

    def test_demand_management_no_prior_year_fires(self):
        init = _make_initiative(lever="demand_management")
        probes = self._call(init, has_cost_center_split=True)
        assert any("2 year" in p["question"].lower() or "revenue" in p["question"].lower()
                   for p in probes)

    def test_maverick_buying_no_po_coverage_fires(self):
        init = _make_initiative(lever="maverick_buying_reduction")
        probes = self._call(init)
        assert any("po" in p["question"].lower() or "PO" in p["question"] for p in probes)

    def test_process_automation_no_volume_fires(self):
        init = _make_initiative(lever="process_automation")
        probes = self._call(init)
        assert any("invoice" in p["question"].lower() for p in probes)

    def test_specification_optimization_no_spec_data_fires(self):
        init = _make_initiative(lever="specification_optimization")
        probes = self._call(init)
        assert any("spec" in p["question"].lower() for p in probes)

    def test_max_three_probes_returned(self):
        init = _make_initiative(lever="supplier_consolidation")
        probes = self._call(init)
        assert len(probes) <= 3

    def test_generic_fallback_fires_when_no_lever_specific(self):
        init = _make_initiative(lever="unknown_lever_xyz")
        probes = self._call(init, has_supplier_data=False)
        # Generic fallback fires when no probes and no supplier data
        assert len(probes) == 1
        assert "vendor master" in probes[0]["question"].lower()

    def test_no_probes_when_all_data_present(self):
        init = _make_initiative(lever="supplier_consolidation")
        probes = self._call(
            init,
            has_contract_data=True,
            has_supplier_data=True,
        )
        assert probes == []

    def test_saving_at_stake_is_numeric(self):
        init = _make_initiative(lever="supplier_consolidation")
        probes = self._call(init)
        for p in probes:
            assert isinstance(p["saving_at_stake"], (int, float))

    def test_probe_structure_has_required_keys(self):
        init = _make_initiative(lever="supplier_consolidation")
        probes = self._call(init)
        for p in probes:
            assert "question" in p
            assert "why_critical" in p
            assert "saving_at_stake" in p
            assert "data_to_request" in p


# ---------------------------------------------------------------------------
# _check_double_count
# ---------------------------------------------------------------------------

class TestCheckDoubleCount:
    def test_no_overlap_returns_none(self):
        init = _make_initiative(category_id="hr", lever="demand_management")
        others = [_make_initiative(category_id="it", lever="supplier_consolidation")]
        assert _check_double_count(init, others) is None

    def test_same_category_different_lever_returns_warning(self):
        init = _make_initiative(category_id="hr", lever="demand_management", category_name="HR")
        others = [
            init,
            _make_initiative(category_id="hr", lever="supplier_consolidation", category_name="HR"),
        ]
        result = _check_double_count(init, others)
        assert result is not None
        # Message references the shared category name and both levers
        assert "HR" in result or "claim savings" in result

    def test_same_category_same_lever_no_overlap(self):
        init = _make_initiative(category_id="hr", lever="demand_management")
        others = [
            _make_initiative(category_id="hr", lever="demand_management"),
        ]
        # Same lever, same category → no conflict (not "different" lever)
        result = _check_double_count(init, others)
        assert result is None

    def test_empty_initiatives_list_returns_none(self):
        init = _make_initiative()
        assert _check_double_count(init, []) is None


# ---------------------------------------------------------------------------
# sme_critique_analyzer (integration)
# ---------------------------------------------------------------------------

class TestSmeCritiqueAnalyzer:
    def test_empty_initiatives_returns_zero_summary(self):
        result = sme_critique_analyzer(*_empty_inputs())
        s = result["critique_summary"]
        assert s["total_initiatives"] == 0
        assert s["ready_count"] == 0
        assert result["initiative_critiques"] == []
        assert result["top_probes"] == []

    def test_single_hypothesis_initiative(self):
        savings_model = {"initiatives": [_make_initiative()]}
        result = sme_critique_analyzer(
            savings_model, {"category_profile": []}, {"comparisons": []},
            {"root_cause_findings": []}, {"contracts": []},
        )
        assert result["critique_summary"]["total_initiatives"] == 1
        critiques = result["initiative_critiques"]
        assert len(critiques) == 1
        # No contract, no supplier → insufficient_data or probe_first
        assert critiques[0]["sme_verdict"] in ("insufficient_data", "probe_first")

    def test_validated_initiative_with_all_signals_proceeds(self):
        init = _make_initiative(confidence="high", lever="supplier_consolidation")
        savings_model = {"initiatives": [init]}
        spend_profile = {
            "category_profile": [
                {"category_id": "it_software", "supplier_count": 10}
            ]
        }
        benchmarks = {
            "comparisons": [{"category_id": "it_software", "specificity_score": 0.9}]
        }
        root_causes = {
            "root_cause_findings": [
                {"category_id": "it_software", "root_causes": ["price_gap", "fragmented_supply"]}
            ]
        }
        contracts = {
            "contracts": [{"category_id": "it_software", "expiry": "2026-06"}]
        }
        result = sme_critique_analyzer(savings_model, spend_profile, benchmarks, root_causes, contracts)
        c = result["initiative_critiques"][0]
        assert c["evidence_maturity"] in ("supported", "validated")
        # With contract + supplier data and all signals, should proceed
        assert c["sme_verdict"] == "proceed"
        assert result["critique_summary"]["ready_count"] == 1

    def test_double_count_flagged_across_categories(self):
        init_a = _make_initiative(category_id="hr", lever="demand_management")
        init_b = _make_initiative(category_id="hr", lever="supplier_consolidation")
        savings_model = {"initiatives": [init_a, init_b]}
        result = sme_critique_analyzer(
            savings_model, {"category_profile": []}, {"comparisons": []},
            {"root_cause_findings": []}, {"contracts": []},
        )
        critiques = result["initiative_critiques"]
        # At least one critique should flag double-count
        flagged = [c for c in critiques if c["double_count_risk"]]
        assert len(flagged) > 0

    def test_top_probes_sorted_by_saving_at_stake(self):
        big = _make_initiative(
            category_id="it_software", lever="supplier_consolidation",
            net_savings={"total_3yr": 1000},
        )
        small = _make_initiative(
            category_id="hr", lever="strategic_sourcing",
            net_savings={"total_3yr": 10},
        )
        savings_model = {"initiatives": [small, big]}
        result = sme_critique_analyzer(
            savings_model, {"category_profile": []}, {"comparisons": []},
            {"root_cause_findings": []}, {"contracts": []},
        )
        probes = result["top_probes"]
        if len(probes) >= 2:
            assert probes[0]["saving_at_stake"] >= probes[1]["saving_at_stake"]

    def test_top_probes_capped_at_three(self):
        many = [
            _make_initiative(category_id=f"cat_{i}", lever="supplier_consolidation")
            for i in range(10)
        ]
        savings_model = {"initiatives": many}
        result = sme_critique_analyzer(
            savings_model, {"category_profile": []}, {"comparisons": []},
            {"root_cause_findings": []}, {"contracts": []},
        )
        assert len(result["top_probes"]) <= 3

    def test_non_dict_initiative_skipped(self):
        # Non-dict items in the initiatives list must not crash _check_double_count
        savings_model = {"initiatives": ["not_a_dict", None, _make_initiative()]}
        result = sme_critique_analyzer(
            savings_model, {"category_profile": []}, {"comparisons": []},
            {"root_cause_findings": []}, {"contracts": []},
        )
        # Only the valid dict initiative is counted
        assert result["critique_summary"]["total_initiatives"] == 1

    def test_output_summary_savings_buckets_add_up(self):
        init = _make_initiative(net_savings={"total_3yr": 300})
        savings_model = {"initiatives": [init]}
        result = sme_critique_analyzer(
            savings_model, {"category_profile": []}, {"comparisons": []},
            {"root_cause_findings": []}, {"contracts": []},
        )
        s = result["critique_summary"]
        total = s["savings_ready"] + s["savings_probe"] + s["savings_insufficient"]
        assert total == 300
