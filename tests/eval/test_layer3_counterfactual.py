"""Layer 3: Counterfactual signal injection and prioritization tests.

All deterministic tests require no LLM.
The llm_judge-marked test calls the analysis-synthesizer and checks
whether the injected signal surfaces in the final response_text.
"""
from __future__ import annotations

from typing import List

import pytest

from app.eval.counterfactual import (
    PrioritizationResult,
    SignalSpec,
    build_noise_lines,
    inject_signal,
    score_prioritization,
)
from app.models import NormalizedSpendLine
from app.skills import engine as skill_engine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_baseline() -> List[NormalizedSpendLine]:
    """Return a minimal baseline spend dataset (3 categories, actuals only)."""
    rows = [
        (1, "Cloud Co",  "cloud",     "Cloud",     100_000.0, "actual"),
        (2, "Agency X",  "marketing", "Marketing",  75_000.0, "actual"),
        (3, "HR Vendor", "hr_systems","HR Systems",  35_000.0, "actual"),
    ]
    return [
        NormalizedSpendLine(
            row_id=r, supplier=s, description=s,
            category_id=c, category_name=cn, amount=a, spend_date="2025-01-15",
            amount_type=t, currency="USD",
            fx_rate_to_reporting=1.0, amount_reporting=a,
        )
        for r, s, c, cn, a, t in rows
    ]


def _overrun_signal(multiplier: float = 5.0) -> SignalSpec:
    return SignalSpec(
        supplier="OverrunCorp",
        category_id="cloud",
        signal_amount=100_000.0 * multiplier,  # 5x overrun
        baseline_amount=100_000.0,
        signal_type="overrun",
    )


# ---------------------------------------------------------------------------
# inject_signal — unit tests
# ---------------------------------------------------------------------------

class TestInjectSignal:
    def test_line_count_increases_by_two(self):
        base = _make_baseline()
        injected = inject_signal(base, _overrun_signal())
        assert len(injected) == len(base) + 2  # actual + budget

    def test_line_count_increases_by_one_without_budget(self):
        base = _make_baseline()
        injected = inject_signal(base, _overrun_signal(), include_budget_line=False)
        assert len(injected) == len(base) + 1

    def test_actual_line_amount_correct(self):
        base = _make_baseline()
        signal = _overrun_signal(multiplier=4.0)
        injected = inject_signal(base, signal)
        actual_lines = [l for l in injected if l.supplier == "OverrunCorp" and l.amount_type == "actual"]
        assert len(actual_lines) == 1
        assert actual_lines[0].amount == pytest.approx(400_000.0)

    def test_budget_line_amount_correct(self):
        base = _make_baseline()
        signal = _overrun_signal()
        injected = inject_signal(base, signal)
        budget_lines = [l for l in injected if l.supplier == "OverrunCorp" and l.amount_type == "budget"]
        assert len(budget_lines) == 1
        assert budget_lines[0].amount == pytest.approx(100_000.0)

    def test_injected_line_has_correct_category(self):
        base = _make_baseline()
        signal = _overrun_signal()
        injected = inject_signal(base, signal)
        signal_lines = [l for l in injected if l.supplier == "OverrunCorp"]
        for line in signal_lines:
            assert line.category_id == "cloud"

    def test_base_lines_unchanged(self):
        base = _make_baseline()
        original_count = len(base)
        inject_signal(base, _overrun_signal())
        # base must not be mutated
        assert len(base) == original_count


# ---------------------------------------------------------------------------
# inject_signal inflates spend totals
# ---------------------------------------------------------------------------

class TestInjectedSpendInflation:
    def test_spend_profiler_total_increases(self):
        base = _make_baseline()
        baseline_profile = skill_engine.spend_profiler(base)
        baseline_total = baseline_profile["total_spend"]

        signal = _overrun_signal(multiplier=10.0)
        injected = inject_signal(base, signal, include_budget_line=False)
        injected_profile = skill_engine.spend_profiler(injected)
        injected_total = injected_profile["total_spend"]

        assert injected_total > baseline_total

    def test_injected_category_spend_increases(self):
        base = _make_baseline()
        signal = SignalSpec(
            supplier="NewVendor",
            category_id="professional_services",  # new category
            signal_amount=500_000.0,
            baseline_amount=0.0,
            signal_type="spike",
        )
        injected = inject_signal(base, signal, include_budget_line=False)
        profile = skill_engine.spend_profiler(injected)
        cat_ids = [c["category_id"] for c in profile["category_profile"]]
        assert "professional_services" in cat_ids


# ---------------------------------------------------------------------------
# BvA surfaces the overrun
# ---------------------------------------------------------------------------

class TestBvASurfacesOverrun:
    def test_overrun_appears_in_bva_variances(self):
        base = _make_baseline()
        # Add budget lines for base categories too so BvA has contrast
        cat_names = {"cloud": "Cloud", "marketing": "Marketing"}
        budget_lines = [
            NormalizedSpendLine(
                row_id=5000 + i, supplier=f"vendor_{i}", description="budget",
                category_id=cat, category_name=cat_names[cat],
                amount=amt * 0.9, spend_date="2025-01-15",
                amount_type="budget", currency="USD",
                fx_rate_to_reporting=1.0, amount_reporting=amt * 0.9,
            )
            for i, (cat, amt) in enumerate([("cloud", 100_000.0), ("marketing", 75_000.0)])
        ]
        base_with_budgets = base + budget_lines

        signal = _overrun_signal(multiplier=5.0)
        injected = inject_signal(base_with_budgets, signal)

        bva = skill_engine.bva_analyzer(injected)
        assert bva.get("bva_available") is True

        variances = {v["category_id"]: v for v in bva.get("variances", [])}
        assert "cloud" in variances, "Cloud category missing from BvA variances"

        cloud_delta = variances["cloud"]["total_variance"]
        # signal actual=500k vs budget (baseline 90k + signal budget 100k = 190k total budget)
        assert cloud_delta > 0, f"Cloud should be over-budget, got delta={cloud_delta}"

    def test_injected_signal_ranks_first_in_bva(self):
        """With a 10x overrun, signal category should be top-1 variance."""
        base = _make_baseline()
        cat_names2 = {"cloud": "Cloud", "marketing": "Marketing", "hr_systems": "HR Systems"}
        budget_lines = [
            NormalizedSpendLine(
                row_id=6000 + i, supplier=f"v{i}", description="bud",
                category_id=cat, category_name=cat_names2[cat],
                amount=amt, spend_date="2025-01-15",
                amount_type="budget", currency="USD",
                fx_rate_to_reporting=1.0, amount_reporting=amt,
            )
            for i, (cat, amt) in enumerate([("cloud", 100_000.0), ("marketing", 75_000.0), ("hr_systems", 35_000.0)])
        ]
        signal = _overrun_signal(multiplier=10.0)
        injected = inject_signal(base + budget_lines, signal)

        bva = skill_engine.bva_analyzer(injected)
        variances = sorted(
            bva.get("variances", []),
            key=lambda v: abs(v.get("total_variance", 0.0)),
            reverse=True,
        )
        assert variances, "No variances returned"
        assert variances[0]["category_id"] == "cloud", (
            f"Expected 'cloud' as top variance, got '{variances[0]['category_id']}'"
        )


# ---------------------------------------------------------------------------
# score_prioritization — deterministic keyword/BvA checks
# ---------------------------------------------------------------------------

class TestScorePrioritization:
    def test_signal_found_by_keyword(self):
        signal = _overrun_signal()
        result = score_prioritization(
            response_text="OverrunCorp shows a significant cost overrun in cloud.",
            signal=signal,
        )
        assert result.signal_surfaced is True
        assert result.mention_count >= 1

    def test_signal_found_by_category(self):
        signal = _overrun_signal()
        result = score_prioritization(
            response_text="The cloud category is the primary driver of variance.",
            signal=signal,
        )
        assert result.signal_surfaced is True

    def test_signal_not_found_in_irrelevant_text(self):
        signal = _overrun_signal()
        result = score_prioritization(
            response_text="Marketing and HR spend remain within budget.",
            signal=signal,
        )
        assert result.signal_surfaced is False

    def test_bva_top3_check(self):
        """BvA rank #1 should trigger signal_surfaced even without keyword."""
        signal = _overrun_signal()
        bva_output = {
            "bva_available": True,
            "category_variances": [
                {"category_id": "cloud", "variance_amount": 500_000.0},
                {"category_id": "marketing", "variance_amount": 10_000.0},
            ],
        }
        result = score_prioritization(
            response_text="No mention here.",
            signal=signal,
            bva_output=bva_output,
        )
        assert result.signal_surfaced is True

    def test_prominence_higher_when_mentioned_early(self):
        signal = _overrun_signal()
        early = score_prioritization(
            "OverrunCorp is the top issue. Everything else is fine.", signal
        )
        late = score_prioritization(
            "Everything is fine. " * 20 + "OverrunCorp was flagged.", signal
        )
        assert early.prominence_score > late.prominence_score

    def test_signal_surfaced_from_evidence_anchor_section(self):
        signal = _overrun_signal()
        response = (
            "Executive summary.\n\n"
            "**Evidence anchors**\n"
            "- cloud: $500,000 modeled via supplier consolidation.\n"
            "- OverrunCorp remains the dominant variance source.\n"
        )
        result = score_prioritization(response, signal)
        assert isinstance(result, PrioritizationResult)
        assert result.signal_surfaced is True


# ---------------------------------------------------------------------------
# Noise does not suppress signal
# ---------------------------------------------------------------------------

class TestNoiseSuppression:
    def test_signal_ranks_above_noise_in_bva(self):
        """10x overrun signal should rank above 5 small noise categories."""
        noise = build_noise_lines(n=5, base_amount=5_000.0)
        # Add budget versions for noise
        noise_budgets = [
            NormalizedSpendLine(
                row_id=8000 + i, supplier=f"noise_vendor_{i}", description="noise bud",
                category_id=f"noise_cat_{i}", category_name=f"Noise Category {i}",
                amount=5_000.0, spend_date="2025-01-15",
                amount_type="budget", currency="USD",
                fx_rate_to_reporting=1.0, amount_reporting=5_000.0,
            )
            for i in range(5)
        ]
        signal = SignalSpec(
            supplier="OverrunCorp",
            category_id="cloud",
            signal_amount=1_000_000.0,
            baseline_amount=100_000.0,
        )
        all_lines = inject_signal(noise + noise_budgets, signal)

        bva = skill_engine.bva_analyzer(all_lines)
        assert bva.get("bva_available") is True, "BvA should be available"

        variances = sorted(
            bva.get("variances", []),
            key=lambda v: abs(v.get("total_variance", 0.0)),
            reverse=True,
        )
        top_cat = variances[0]["category_id"] if variances else None
        assert top_cat == "cloud", f"Signal category not top-ranked; got '{top_cat}'"


# ---------------------------------------------------------------------------
# build_noise_lines helper
# ---------------------------------------------------------------------------

class TestBuildNoiseLines:
    def test_returns_correct_count(self):
        noise = build_noise_lines(n=7)
        assert len(noise) == 7

    def test_all_noise_are_actual_type(self):
        noise = build_noise_lines(n=3)
        for line in noise:
            assert line.amount_type == "actual"

    def test_distinct_categories(self):
        noise = build_noise_lines(n=5)
        cats = {l.category_id for l in noise}
        assert len(cats) == 5, "Each noise line should have a distinct category"
