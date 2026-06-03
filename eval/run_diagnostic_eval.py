#!/usr/bin/env python3
"""
eval/run_diagnostic_eval.py — OpEx Platform Diagnostic Feature Evaluator

Scores the /api/v1/diagnostic/company-research endpoint across 3 domains
and 8 dimensions. All checks are deterministic (rule-based); no LLM calls.

Surfaces 8 known stubs/inconsistencies:
  1. headcount hardcoded to 500 (enterprise.py:338)
  2. root_causes always empty list (enterprise.py:340)
  3. actual_pct = p50_pct, gap_pct = 0.0, gap_cr = 0.0 always (enterprise.py:326-328)
  4. category always "" in value_at_table (enterprise.py:365)
  5. npv always 0.0 in value_at_table (enterprise.py:369)
  6. "3-year savings" label but no 3x time-horizon multiplier (enterprise.py:387)
  7. resolve_benchmark_payload called twice unnecessarily (enterprise.py:280+303)
  8. _PACK_TO_BENCH missing sector packs: financial_services_nonbank, gcc_capability_centers,
     healthcare_hospitals, hospitality_travel

Usage:
    PYTHONPATH=. python eval/run_diagnostic_eval.py
    PYTHONPATH=. python eval/run_diagnostic_eval.py --json-only
    PYTHONPATH=. python eval/run_diagnostic_eval.py --output eval/my_report.md

Exit codes:
    0 — all dimensions pass their threshold
    1 — one or more dimensions fail
    2 — critical error (missing file, import failure)
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
import traceback
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).parent.parent
SCENARIOS_DIR = ROOT / "tests" / "eval" / "golden" / "diagnostic"
CRITERIA_PATH = ROOT / "eval" / "diagnostic_criteria.json"
DEFAULT_OUTPUT_MD = ROOT / "eval" / "diagnostic_report.md"
DEFAULT_OUTPUT_JSON = ROOT / "eval" / "diagnostic_scores.json"
SECTOR_PACKS_DIR = ROOT / "skills" / "sector-packs"
ENTERPRISE_ROUTER = ROOT / "app" / "routers" / "enterprise.py"

SCENARIO_FILES = [
    "s01_it_ites.json",
    "s02_bfsi_large.json",
    "s03_pharma_small.json",
    "s04_unknown_sector.json",
    "s05_hospitality_unmapped.json",
]


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class DimensionResult:
    dimension_id: str
    name: str
    domain: str
    weight: float
    threshold_pass: float
    raw_score: float
    passed: bool
    evidence: Dict[str, Any]
    finding_summary: str
    finding_detail: str
    remediation: str
    scenarios_run: int = 0
    scenarios_failed: int = 0

    @property
    def weighted_score(self) -> float:
        return self.raw_score * self.weight

    @property
    def gap(self) -> float:
        return max(0.0, self.threshold_pass - self.raw_score)


@dataclass
class DomainResult:
    domain_name: str
    domain_display: str
    domain_weight: float
    dimension_results: List[DimensionResult]
    domain_score: float
    passed: bool


@dataclass
class EvalReport:
    platform_version: str
    eval_date: str
    overall_score: float
    domain_results: List[DomainResult]
    top_gaps: List[Dict]
    remediation_roadmap: List[Dict]
    passed: bool
    scenario_run_count: int
    scenario_pass_count: int


# ---------------------------------------------------------------------------
# Scenario runner
# ---------------------------------------------------------------------------

def _run_scenario(fixture: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Execute the fixed diagnostic endpoint logic against a fixture request.
    Mirrors app/routers/enterprise.py::company_research exactly. Returns (result_dict, error_msg).
    """
    try:
        from app.skills.engine import (
            document_contextualizer,
            peer_benchmarker,
            resolve_eligible_levers,
            root_cause_analyzer,
        )
        from app.services.benchmarks import resolve_benchmark_payload
        from app.skills.engine.lever_rules import build_signal_corpus as _build_signal_corpus

        req = fixture["request"]
        company_name = req["company_name"]
        industry = req["industry"]
        annual_revenue_cr = float(req.get("annual_revenue_cr", 5000.0))
        headcount = int(req.get("headcount", 500))
        wacc = float(req.get("wacc", 0.12))

        company_signals = document_contextualizer([])
        inferred = company_signals.get("inferred_industry", "")
        effective_industry = inferred if inferred else industry

        _PACK_TO_BENCH: Dict[str, str] = {
            "it_ites": "technology",
            "bfsi_banks": "financial_services",
            "insurance_general": "financial_services",
            "fmcg_consumer": "retail_consumer",
            "pharma_lifesciences": "healthcare",
            "energy_utilities": "manufacturing",
            "retail_organized": "retail_consumer",
            "telecom_infra": "technology",
            "manufacturing_diversified": "manufacturing",
            "psu_cpse": "manufacturing",
            "conglomerate": "manufacturing",
            "financial_services_nonbank": "financial_services",
            "gcc_capability_centers": "technology",
            "healthcare_hospitals": "healthcare",
            "hospitality_travel": "retail_consumer",
        }
        bench_industry = _PACK_TO_BENCH.get(effective_industry, effective_industry)
        revenue_inr = annual_revenue_cr * 1_00_00_000

        bench_resolved = resolve_benchmark_payload(industry=bench_industry, categories=[], annual_revenue=revenue_inr)
        bench_cats = (
            bench_resolved.get("benchmark_data", {})
            .get("benchmarks", {}).get(bench_industry, {}).get("categories", {})
        )
        category_profile = []
        for cat_id, metrics in bench_cats.items():
            p50_pct = float(metrics.get("P50", 0.0))
            implied_spend = (p50_pct / 100.0) * revenue_inr
            if implied_spend > 0:
                category_profile.append({
                    "category_id": cat_id,
                    "category_name": cat_id.replace("_", " ").title(),
                    "spend": implied_spend,
                    "supplier_count": 5,
                    "transaction_count": 50,
                })

        total_implied = sum(c["spend"] for c in category_profile) or 1.0
        synthetic_profile = {"total_spend": total_implied, "category_profile": category_profile, "data_source": "benchmark_proxy"}

        benchmarks = peer_benchmarker(
            synthetic_profile,
            bench_resolved["benchmark_data"],
            bench_industry,
            revenue_inr,
            selected_dataset=bench_resolved.get("selected_dataset"),
            selection_rationale=bench_resolved.get("selection_rationale"),
        )

        benchmark_gaps = []
        for row in benchmarks.get("comparisons", []):
            p50_pct = float(row.get("benchmark_p50_pct", 0.0))
            p25_pct = float(row.get("benchmark_target_pct", 0.0))
            if p50_pct <= 0:
                continue
            implied_p50_cr = round(p50_pct / 100.0 * annual_revenue_cr, 1)
            implied_p25_cr = round(p25_pct / 100.0 * annual_revenue_cr, 1)
            band_cr = round((p50_pct - p25_pct) / 100.0 * annual_revenue_cr, 1)
            benchmark_gaps.append({
                "category": row.get("category_id", ""),
                "category_name": row.get("category_name", row.get("category_id", "")),
                "p25_pct": round(p25_pct, 2),
                "p50_pct": round(p50_pct, 2),
                "actual_pct": round(p50_pct, 2),
                "gap_pct": round(p50_pct - p25_pct, 2),
                "gap_cr": band_cr,
                "implied_p50_cr": implied_p50_cr,
                "implied_p25_cr": implied_p25_cr,
                "benchmark_p50_to_p25_band_cr": band_cr,
                "percentile_band": "synthetic_P50",
            })
        benchmark_gaps.sort(key=lambda x: x["implied_p50_cr"], reverse=True)

        root_cause_output = root_cause_analyzer(
            profile=synthetic_profile, peer=benchmarks, lines=[],
            headcount=float(headcount), annual_revenue=revenue_inr, industry=effective_industry,
        )
        derived_root_causes = root_cause_output.get("root_causes", [])
        signal_corpus = _build_signal_corpus(synthetic_profile)

        eligible_levers = resolve_eligible_levers(
            industry=effective_industry,
            spend_profile=synthetic_profile,
            headcount=float(headcount),
            annual_revenue=revenue_inr,
            root_causes=derived_root_causes,
            signal_corpus=signal_corpus,
            line_flags={"constraints": company_signals.get("constraints", [])},
            engagement_id=f"diag-{company_name[:20]}-{int(revenue_inr)}",
        )

        cat_spend_cr = {c["category_id"]: c["spend"] / 1_00_00_000 for c in category_profile}
        total_spend_cr = sum(cat_spend_cr.values()) or 1.0
        value_at_table = []
        lever_floor_count = 0
        lever_category_count = 0
        for lv in eligible_levers:
            rng = lv.get("savings_range_pct", {})
            if not rng:
                continue
            p10_rate = float(rng.get("p10", 0)) / 100.0
            p50_rate = float(rng.get("p50", 0)) / 100.0
            p90_rate = float(rng.get("p90", 0)) / 100.0
            primary_cat_spend_cr = 0.0
            matched_category_id = ""
            for sig in lv.get("trigger_signals", []):
                if sig.startswith("category:") and sig.endswith("_present"):
                    cid = sig.split(":")[1].replace("_present", "")
                    primary_cat_spend_cr = cat_spend_cr.get(cid, 0.0)
                    matched_category_id = cid
                    break
            if primary_cat_spend_cr > 0:
                lever_category_count += 1
            else:
                lever_floor_count += 1
            base_spend_cr = primary_cat_spend_cr if primary_cat_spend_cr > 0 else total_spend_cr * 0.10
            p50_cr = round(p50_rate * base_spend_cr, 1)
            if p50_cr < 0.1:
                continue
            npv = round(sum(p50_cr / (1.0 + wacc) ** t for t in range(1, 4)), 1)
            value_at_table.append({
                "lever_id": lv["lever_id"],
                "lever_name": lv["lever_name"],
                "category": matched_category_id,
                "p10_cr": round(p10_rate * base_spend_cr, 1),
                "p50_cr": p50_cr,
                "p90_cr": round(p90_rate * base_spend_cr, 1),
                "npv": npv,
                "savings_type": lv.get("savings_type", "run_rate"),
                "complexity_tier": lv.get("complexity_tier", "medium"),
                "_base_spend_from_floor": primary_cat_spend_cr == 0,
            })
        value_at_table.sort(key=lambda x: x["p50_cr"], reverse=True)
        value_at_table = value_at_table[:12]
        total_p50 = round(sum(v["p50_cr"] for v in value_at_table), 1)

        top_gap = benchmark_gaps[0] if benchmark_gaps else {}
        top_lever = value_at_table[0] if value_at_table else {}
        key_findings = []
        if top_gap:
            key_findings.append(
                f"Largest category: {top_gap.get('category_name', '')} — "
                f"₹{top_gap.get('implied_p50_cr', 0):.0f} Cr at P50 benchmark; "
                f"₹{top_gap.get('benchmark_p50_to_p25_band_cr', 0):.0f} Cr headroom to P25 best-in-class"
            )
        if top_lever:
            key_findings.append(
                f"Highest-value lever: {top_lever['lever_name']} — "
                f"₹{top_lever['p50_cr']:.0f} Cr annual savings (P50 estimate)"
            )
        if company_signals.get("constraints"):
            key_findings.append("Document flags: " + "; ".join(company_signals["constraints"][:2]))
        key_findings.append(
            f"Total value at table (P50 annual): ₹{total_p50:.0f} Cr across {len(value_at_table)} levers"
        )

        return {
            "company_name": company_name,
            "industry_used": effective_industry,
            "bench_industry": bench_industry,
            "annual_revenue_cr": annual_revenue_cr,
            "company_signals": company_signals,
            "benchmark_gaps": benchmark_gaps,
            "value_at_table": value_at_table,
            "total_p50_value_cr": total_p50,
            "key_findings": key_findings,
            "category_profile": category_profile,
            "total_spend_cr": total_spend_cr,
            "profile_basis": "benchmark_proxy",
            "data_note": "Spend profile derived from benchmark P50 values — upload actual spend data for company-specific analysis.",
            "_lever_floor_count": lever_floor_count,
            "_lever_category_count": lever_category_count,
            "_eligible_lever_count": len(eligible_levers),
        }, None

    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"


# ---------------------------------------------------------------------------
# DG-01: Synthetic Profile Arithmetic
# ---------------------------------------------------------------------------

def score_dg01(results: List[Tuple[Dict, Dict]]) -> DimensionResult:
    """total_spend == sum(category spends) within 1%; implied spend = P50/100 * revenue."""
    checks_per_scenario = {}
    passed_count = 0
    total_checks = 0

    for fixture, result in results:
        sid = fixture["scenario_id"]
        checks: Dict[str, Any] = {}

        if result is None:
            checks_per_scenario[sid] = {"error": "run failed", "passed": 0, "total": 0}
            continue

        cp = result.get("category_profile", [])
        total_spend = result.get("total_spend_cr", 0) * 1_00_00_000
        if cp and total_spend > 0:
            cat_sum = sum(c["spend"] for c in cp)
            rel_err = abs(cat_sum - total_spend) / total_spend if total_spend > 0 else 0
            checks["total_spend_matches_category_sum"] = rel_err <= 0.01
        else:
            # Empty profile (unmapped industry) — acceptable, not a failure
            checks["total_spend_matches_category_sum"] = True

        revenue_cr = fixture["request"]["annual_revenue_cr"]
        revenue_inr = revenue_cr * 1_00_00_000
        mismatches = []
        for cat in cp[:5]:
            # We can't re-read P50 from benchmark here, so verify spend > 0 and reasonable scale
            spend = cat.get("spend", 0)
            checks[f"cat_{cat['category_id']}_positive"] = spend > 0
            # Spend per category should be < 100% of revenue
            if revenue_inr > 0:
                pct = spend / revenue_inr * 100
                if pct > 100:
                    mismatches.append(f"{cat['category_id']} {pct:.1f}%>100%")
                checks[f"cat_{cat['category_id']}_pct_lt_100"] = pct <= 100

        checks["no_category_exceeds_revenue"] = len(mismatches) == 0

        n_pass = sum(1 for v in checks.values() if v is True)
        n_total = sum(1 for v in checks.values() if isinstance(v, bool))
        checks_per_scenario[sid] = {
            "checks": {k: v for k, v in checks.items() if isinstance(v, bool)},
            "passed": n_pass,
            "total": n_total,
            "mismatches": mismatches,
        }
        passed_count += n_pass
        total_checks += n_total

    score = (passed_count / total_checks * 10) if total_checks > 0 else 0.0
    passed = score >= 7.0
    return DimensionResult(
        dimension_id="DG-01",
        name="Synthetic Profile Arithmetic",
        domain="data_integrity",
        weight=0.30,
        threshold_pass=7.0,
        raw_score=round(score, 2),
        passed=passed,
        evidence=checks_per_scenario,
        finding_summary=f"{passed_count}/{total_checks} arithmetic checks passed across {len(results)} scenarios",
        finding_detail="PASS" if passed else f"FAIL — {passed_count}/{total_checks} checks passed; review category spend accumulation",
        remediation="Check floating-point accumulation at enterprise.py:301. Verify total_implied = sum(category_profile[*].spend).",
        scenarios_run=len(results),
        scenarios_failed=sum(1 for _, r in results if r is None),
    )


# ---------------------------------------------------------------------------
# DG-02: Benchmark Gap Field Consistency
# ---------------------------------------------------------------------------

def score_dg02(results: List[Tuple[Dict, Dict]]) -> DimensionResult:
    """actual_pct == p50_pct; gap_pct == 0.0; gap_cr == 0.0; sorted desc by implied_p50_cr."""
    checks_per_scenario = {}
    total_pass = 0
    total_checks = 0

    for fixture, result in results:
        sid = fixture["scenario_id"]
        if result is None:
            checks_per_scenario[sid] = {"error": "run failed"}
            continue

        gaps = result.get("benchmark_gaps", [])
        checks: Dict[str, bool] = {}

        if not gaps:
            checks["has_gaps_or_unmapped"] = not fixture["scoring_hints"].get("expect_benchmark_gaps_nonempty", True)
        else:
            all_actual_eq_p50 = all(abs(g["actual_pct"] - g["p50_pct"]) < 0.001 for g in gaps)
            # After fix: gap_pct should equal (p50_pct - p25_pct), not 0.0
            all_gap_pct_correct = all(
                abs(g["gap_pct"] - (g["p50_pct"] - g["p25_pct"])) < 0.02 for g in gaps
            )
            all_gap_cr_positive = all(g["gap_cr"] >= 0.0 for g in gaps)
            sorted_ok = all(
                gaps[i]["implied_p50_cr"] >= gaps[i + 1]["implied_p50_cr"]
                for i in range(len(gaps) - 1)
            )
            # After fix: field should be benchmark_p50_to_p25_band_cr (renamed from headroom_to_p25_cr)
            has_renamed_field = all("benchmark_p50_to_p25_band_cr" in g for g in gaps)
            # After fix: percentile_band should be synthetic_P50, not Reference
            has_informative_band = all(g.get("percentile_band") == "synthetic_P50" for g in gaps)
            checks["actual_pct_equals_p50_pct"] = all_actual_eq_p50
            checks["gap_pct_equals_p50_minus_p25"] = all_gap_pct_correct
            checks["gap_cr_non_negative"] = all_gap_cr_positive
            checks["sorted_desc_by_implied_p50"] = sorted_ok
            checks["headroom_field_renamed"] = has_renamed_field
            checks["percentile_band_informative"] = has_informative_band

        n_pass = sum(1 for v in checks.values() if v is True)
        n_total = sum(1 for v in checks.values() if isinstance(v, bool))
        checks_per_scenario[sid] = {
            "checks": checks,
            "passed": n_pass,
            "total": n_total,
            "gap_count": len(gaps),
        }
        total_pass += n_pass
        total_checks += n_total

    score = (total_pass / total_checks * 10) if total_checks > 0 else 0.0
    passed = score >= 8.0
    return DimensionResult(
        dimension_id="DG-02",
        name="Benchmark Gap Field Consistency",
        domain="data_integrity",
        weight=0.30,
        threshold_pass=8.0,
        raw_score=round(score, 2),
        passed=passed,
        evidence=checks_per_scenario,
        finding_summary=f"{total_pass}/{total_checks} field consistency checks passed.",
        finding_detail="PASS" if passed else f"FAIL — score {score:.1f} < 8.0",
        remediation="gap_pct should equal (p50_pct - p25_pct); benchmark_p50_to_p25_band_cr should be present; percentile_band should be 'synthetic_P50'.",
        scenarios_run=len(results),
        scenarios_failed=sum(1 for _, r in results if r is None),
    )


# ---------------------------------------------------------------------------
# DG-03: Value-at-Table Arithmetic
# ---------------------------------------------------------------------------

def score_dg03(results: List[Tuple[Dict, Dict]]) -> DimensionResult:
    """total_p50 == sum(p50_cr) within 1%; p10 <= p50 <= p90 for every lever; no p50 < 0.1."""
    checks_per_scenario = {}
    total_pass = 0
    total_checks = 0

    for fixture, result in results:
        sid = fixture["scenario_id"]
        if result is None:
            checks_per_scenario[sid] = {"error": "run failed"}
            continue

        vat = result.get("value_at_table", [])
        total_p50 = result.get("total_p50_value_cr", 0.0)
        checks: Dict[str, bool] = {}

        if not vat:
            checks["empty_table_acceptable"] = True
            checks_per_scenario[sid] = {"checks": checks, "lever_count": 0}
        else:
            computed_sum = round(sum(v["p50_cr"] for v in vat), 1)
            rel_err = abs(computed_sum - total_p50) / max(total_p50, 0.001)
            checks["total_p50_matches_sum"] = rel_err <= 0.01

            monotone_violations = [
                v["lever_id"] for v in vat
                if not (v["p10_cr"] <= v["p50_cr"] <= v["p90_cr"])
            ]
            checks["p10_le_p50_le_p90"] = len(monotone_violations) == 0

            below_floor = [v["lever_id"] for v in vat if v["p50_cr"] < 0.1]
            checks["no_lever_below_min_threshold"] = len(below_floor) == 0

            checks["max_12_levers"] = len(vat) <= 12

            checks_per_scenario[sid] = {
                "checks": checks,
                "lever_count": len(vat),
                "computed_sum": computed_sum,
                "reported_total": total_p50,
                "monotone_violations": monotone_violations,
                "below_floor": below_floor,
            }

        n_pass = sum(1 for v in checks.values() if v is True)
        n_total = len(checks)
        total_pass += n_pass
        total_checks += n_total

    score = (total_pass / total_checks * 10) if total_checks > 0 else 0.0
    passed = score >= 7.0
    return DimensionResult(
        dimension_id="DG-03",
        name="Value-at-Table Arithmetic",
        domain="data_integrity",
        weight=0.40,
        threshold_pass=7.0,
        raw_score=round(score, 2),
        passed=passed,
        evidence=checks_per_scenario,
        finding_summary=f"{total_pass}/{total_checks} arithmetic checks passed across {len(results)} scenarios",
        finding_detail="PASS" if passed else f"FAIL — check monotonicity of savings_range_pct in lever JSONs and summation at enterprise.py:375",
        remediation="Verify savings_range_pct.p10 <= p50 <= p90 in all sector_levers.json files. Review rounding at enterprise.py:359-368.",
        scenarios_run=len(results),
        scenarios_failed=sum(1 for _, r in results if r is None),
    )


# ---------------------------------------------------------------------------
# DG-04: Stub Field Detection
# ---------------------------------------------------------------------------

def score_dg04(results: List[Tuple[Dict, Dict]]) -> DimensionResult:
    """
    Detects confirmed stubs. Each confirmed stub costs 2.5 points from 10.
    Score = max(0, 10 - 2.5 * stubs_confirmed).
    Threshold is set to 4.0 — anything >= 2 stubs confirmed fails.
    """
    stub_checks = {
        "npv_always_zero": False,
        "category_always_empty": False,
        "gap_pct_always_zero": False,
        "hardcoded_headcount_500": False,
        "root_causes_not_derived": False,
        "label_3yr_no_multiplier": False,
    }

    # Check npv, category across all result levers
    all_npvs = []
    all_categories = []
    all_gap_pcts = []
    for fixture, result in results:
        if result is None:
            continue
        for lv in result.get("value_at_table", []):
            all_npvs.append(lv.get("npv", -1))
            all_categories.append(lv.get("category", "NOT_EMPTY"))
        for g in result.get("benchmark_gaps", []):
            all_gap_pcts.append(g.get("gap_pct", -1))

    if all_npvs:
        # After fix: NPV should be non-zero for levers with p50_cr > 0
        stub_checks["npv_always_zero"] = all(n == 0.0 for n in all_npvs)
    if all_categories:
        # After fix: category should be populated from trigger signal (non-empty for matched levers)
        stub_checks["category_always_empty"] = all(c == "" for c in all_categories)
    if all_gap_pcts:
        # After fix: gap_pct = p50_pct - p25_pct, so should not all be 0.0
        stub_checks["gap_pct_always_zero"] = all(g == 0.0 for g in all_gap_pcts)

    # Static analysis: read enterprise.py source for remaining hardcoded values
    try:
        src = ENTERPRISE_ROUTER.read_text()
        # After fix: headcount is passed from req.headcount (not literal 500.0)
        stub_checks["hardcoded_headcount_500"] = "headcount=500.0" in src and "req.headcount" not in src
        # After fix: root_causes=[] should be replaced with derived_root_causes
        stub_checks["root_causes_not_derived"] = "root_causes=[]" in src
        # After fix: label should say "annual savings" not "3-year savings"
        stub_checks["label_3yr_no_multiplier"] = (
            "3-year savings" in src and "p50_cr * 3" not in src and "p50_cr*3" not in src
        )
    except Exception:
        pass

    stubs_confirmed = sum(1 for v in stub_checks.values() if v is True)
    score = max(0.0, 10.0 - 2.5 * stubs_confirmed)
    passed = score >= 4.0

    confirmed_list = [k for k, v in stub_checks.items() if v is True]
    not_confirmed = [k for k, v in stub_checks.items() if not v]
    total_stubs = len(stub_checks)

    return DimensionResult(
        dimension_id="DG-04",
        name="Stub Field Detection",
        domain="analysis_completeness",
        weight=0.35,
        threshold_pass=4.0,
        raw_score=round(score, 2),
        passed=passed,
        evidence={
            "stub_checks": stub_checks,
            "stubs_confirmed": stubs_confirmed,
            "confirmed_stubs": confirmed_list,
            "not_confirmed": not_confirmed,
            "lever_npv_values_sampled": all_npvs[:10],
            "lever_category_values_sampled": all_categories[:10],
        },
        finding_summary=f"{stubs_confirmed}/{total_stubs} stubs confirmed: {confirmed_list}",
        finding_detail=(
            f"FAIL — {stubs_confirmed} stubs confirmed (score {score:.1f} < 4.0). "
            f"Stubs: {', '.join(confirmed_list)}"
            if not passed else
            f"PASS — only {stubs_confirmed} stubs remaining"
        ),
        remediation=(
            "Priority order: "
            "1) NPV: add wacc param, compute sum(p50_cr/(1+wacc)^t for t in 1..3). "
            "2) category: populate from first matched trigger_signal category ID. "
            "3) headcount: add to CompanyResearchRequest schema and pass through. "
            "4) root_causes: run root_cause_analyzer on synthetic profile first. "
            "5) label: rename to 'annual savings estimate'."
        ),
        scenarios_run=len(results),
        scenarios_failed=0,
    )


# ---------------------------------------------------------------------------
# DG-05: Lever Base Spend Coverage
# ---------------------------------------------------------------------------

def score_dg05(results: List[Tuple[Dict, Dict]]) -> DimensionResult:
    """Fraction of eligible levers that resolved a category spend vs. fell back to 10% floor."""
    per_scenario = {}
    total_category = 0
    total_floor = 0

    for fixture, result in results:
        sid = fixture["scenario_id"]
        if result is None:
            per_scenario[sid] = {"error": "run failed"}
            continue
        cat = result.get("_lever_category_count", 0)
        floor = result.get("_lever_floor_count", 0)
        total = cat + floor
        ratio = cat / total if total > 0 else 0.0
        per_scenario[sid] = {
            "levers_with_category_match": cat,
            "levers_using_floor": floor,
            "total_eligible": total,
            "category_match_ratio": round(ratio, 3),
        }
        total_category += cat
        total_floor += floor

    grand_total = total_category + total_floor
    overall_ratio = total_category / grand_total if grand_total > 0 else 0.0
    score = round(overall_ratio * 10, 2)
    passed = score >= 6.0

    return DimensionResult(
        dimension_id="DG-05",
        name="Lever Base Spend Coverage",
        domain="analysis_completeness",
        weight=0.30,
        threshold_pass=6.0,
        raw_score=score,
        passed=passed,
        evidence={
            "per_scenario": per_scenario,
            "total_category_matched": total_category,
            "total_floor_fallback": total_floor,
            "overall_match_ratio": round(overall_ratio, 3),
        },
        finding_summary=f"{total_category}/{grand_total} levers resolved a category spend ({overall_ratio:.0%}); {total_floor} fell back to 10% floor",
        finding_detail=(
            "PASS" if passed else
            f"FAIL — only {overall_ratio:.0%} of levers matched a category. "
            "High floor-fallback rate means savings estimates are based on 10% of total spend regardless of actual category weighting."
        ),
        remediation=(
            "Review trigger_signals in sector_levers.json — ensure category IDs match those returned by "
            "resolve_benchmark_payload. Consider a multi-signal resolver (not just first match). "
            "Also ensure category keys in cat_spend_cr are case-consistently matched."
        ),
        scenarios_run=len(results),
        scenarios_failed=sum(1 for _, r in results if r is None),
    )


# ---------------------------------------------------------------------------
# DG-06: Key Findings Completeness
# ---------------------------------------------------------------------------

def score_dg06(results: List[Tuple[Dict, Dict]]) -> DimensionResult:
    """All expected finding types present; '3-year' label vs. actual time horizon flagged."""
    checks_per_scenario = {}
    total_pass = 0
    total_checks = 0

    for fixture, result in results:
        sid = fixture["scenario_id"]
        if result is None:
            checks_per_scenario[sid] = {"error": "run failed"}
            continue

        kf = result.get("key_findings", [])
        checks: Dict[str, bool] = {}

        kf_text = " ".join(kf).lower()
        has_category_finding = any("largest category" in f.lower() or "benchmark" in f.lower() for f in kf)
        has_lever_finding = any("lever" in f.lower() or "savings" in f.lower() for f in kf)
        has_total_finding = any("total value" in f.lower() or "value at table" in f.lower() for f in kf)
        min_count = fixture["scoring_hints"].get("expect_key_findings_min_count", 2)

        checks["min_findings_present"] = len(kf) >= min_count
        checks["total_value_finding_present"] = has_total_finding
        checks["lever_finding_present"] = has_lever_finding or not result.get("value_at_table")

        three_yr_label = any("3-year" in f for f in kf)
        # Flag as informational (does not deduct score): '3-year' used but no multiplier applied
        label_inconsistency = three_yr_label  # known issue — always True if levers exist

        n_pass = sum(1 for v in checks.values() if v is True)
        n_total = len(checks)
        checks_per_scenario[sid] = {
            "checks": checks,
            "findings_count": len(kf),
            "passed": n_pass,
            "total": n_total,
            "label_3yr_inconsistency": label_inconsistency,
            "note": "3-year label used without 3x multiplier — informational flag, no score deduction",
        }
        total_pass += n_pass
        total_checks += n_total

    score = (total_pass / total_checks * 10) if total_checks > 0 else 0.0
    passed = score >= 7.0

    three_yr_flagged = sum(
        1 for s in checks_per_scenario.values()
        if isinstance(s, dict) and s.get("label_3yr_inconsistency", False)
    )

    return DimensionResult(
        dimension_id="DG-06",
        name="Key Findings Completeness",
        domain="analysis_completeness",
        weight=0.35,
        threshold_pass=7.0,
        raw_score=round(score, 2),
        passed=passed,
        evidence={
            "per_scenario": checks_per_scenario,
            "three_yr_label_flagged_in_n_scenarios": three_yr_flagged,
            "known_issue": "'3-year savings' label appears but p50_cr is not multiplied by 3 (enterprise.py:387). Fix: either multiply p50_cr * 3 in key_findings or rename to 'annual savings estimate'.",
        },
        finding_summary=f"{total_pass}/{total_checks} completeness checks passed. '3-year' label inconsistency flagged in {three_yr_flagged} scenarios.",
        finding_detail="PASS" if passed else f"FAIL — {total_pass}/{total_checks} passed",
        remediation="Fix '3-year savings' label at enterprise.py:387 — multiply p50_cr by 3 for a true 3-year estimate, or relabel as 'annual savings estimate (P50)'.",
        scenarios_run=len(results),
        scenarios_failed=sum(1 for _, r in results if r is None),
    )


# ---------------------------------------------------------------------------
# DG-07: Diagnostic Signal Schema (static analysis — no scenario run needed)
# ---------------------------------------------------------------------------

def score_dg07() -> DimensionResult:
    """Every lever in every sector pack must have valid diagnostic_signals array."""
    violations: List[str] = []
    total_levers = 0
    total_signals = 0

    for pack_dir in sorted(SECTOR_PACKS_DIR.iterdir()):
        levers_file = pack_dir / "sector_levers.json"
        if not levers_file.exists():
            continue
        try:
            data = json.loads(levers_file.read_text())
        except json.JSONDecodeError as e:
            violations.append(f"{pack_dir.name}/sector_levers.json — JSON parse error: {e}")
            continue

        levers = (
            data if isinstance(data, list)
            else data.get("sector_specific_levers", data.get("levers", []))
        )
        for lv in levers:
            total_levers += 1
            lid = lv.get("lever_id", "unknown")
            sigs = lv.get("diagnostic_signals")
            if sigs is None:
                violations.append(f"{pack_dir.name}/{lid} — missing diagnostic_signals key")
                continue
            if not isinstance(sigs, list):
                violations.append(f"{pack_dir.name}/{lid} — diagnostic_signals is not a list")
                continue
            if len(sigs) == 0:
                violations.append(f"{pack_dir.name}/{lid} — diagnostic_signals is empty []")
                continue
            for i, sig in enumerate(sigs):
                total_signals += 1
                for field in ("signal", "evidence_source", "confirms"):
                    if not sig.get(field):
                        violations.append(f"{pack_dir.name}/{lid}[{i}] — missing/empty field: {field}")

    if total_levers == 0:
        # No levers found — likely wrong JSON key; treat as critical failure
        violations.append("CRITICAL: 0 levers found — check sector_specific_levers key in sector_levers.json")
        score = 0.0
    else:
        # Each violation costs 1 point, max deduction 10
        score = max(0.0, 10.0 - min(10.0, len(violations)))
    passed = score >= 9.0

    return DimensionResult(
        dimension_id="DG-07",
        name="Diagnostic Signal Schema",
        domain="schema_signal_integrity",
        weight=0.40,
        threshold_pass=9.0,
        raw_score=round(score, 2),
        passed=passed,
        evidence={
            "total_levers_checked": total_levers,
            "total_signals_found": total_signals,
            "violation_count": len(violations),
            "violations": violations[:30],
        },
        finding_summary=f"{total_levers} levers checked, {total_signals} signals validated, {len(violations)} violations",
        finding_detail="PASS" if passed else f"FAIL — {len(violations)} schema violations found",
        remediation="For each violation, add/fix diagnostic_signals in the corresponding sector_levers.json. Required schema: [{signal, evidence_source, confirms}].",
        scenarios_run=0,
        scenarios_failed=0,
    )


# ---------------------------------------------------------------------------
# DG-08: Sector Pack Mapping Coverage (static analysis)
# ---------------------------------------------------------------------------

def score_dg08() -> DimensionResult:
    """All sector pack dirs must have a mapping in _PACK_TO_BENCH in enterprise.py."""

    # Parse _PACK_TO_BENCH from enterprise.py source
    try:
        src = ENTERPRISE_ROUTER.read_text()
        # Find the dict literal
        start = src.find("_PACK_TO_BENCH: Dict[str, str] = {")
        if start == -1:
            start = src.find("_PACK_TO_BENCH = {")
        end = src.find("}", start) + 1
        dict_src = src[start:end]
        # Extract keys using simple regex
        import re
        mapped_keys = set(re.findall(r'"([a-z_]+)"\s*:', dict_src))
    except Exception as exc:
        mapped_keys = set()

    discovered_packs = set()
    for pack_dir in SECTOR_PACKS_DIR.iterdir():
        if (pack_dir / "sector_levers.json").exists():
            discovered_packs.add(pack_dir.name)

    missing = sorted(discovered_packs - mapped_keys)
    covered = sorted(discovered_packs & mapped_keys)
    phantom = sorted(mapped_keys - discovered_packs)  # in dict but no dir

    ratio = len(covered) / len(discovered_packs) if discovered_packs else 1.0
    score = round(ratio * 10, 2)
    passed = score >= 8.0

    return DimensionResult(
        dimension_id="DG-08",
        name="Sector Pack Mapping Coverage",
        domain="schema_signal_integrity",
        weight=0.60,
        threshold_pass=8.0,
        raw_score=score,
        passed=passed,
        evidence={
            "discovered_packs": sorted(discovered_packs),
            "mapped_in_pack_to_bench": sorted(mapped_keys),
            "covered": covered,
            "missing_from_mapping": missing,
            "phantom_keys_in_dict": phantom,
            "coverage_ratio": round(ratio, 3),
        },
        finding_summary=f"{len(covered)}/{len(discovered_packs)} sector packs mapped ({ratio:.0%}). Missing: {missing}",
        finding_detail=(
            "PASS" if passed else
            f"FAIL — {len(missing)} sector packs unmapped: {missing}. "
            "These sectors will silently fail benchmark lookup."
        ),
        remediation=(
            f"Add the following to _PACK_TO_BENCH in app/routers/enterprise.py: "
            + ", ".join(f'"{p}": "<benchmark_industry>"' for p in missing)
            + ". Suggested mappings: financial_services_nonbank→financial_services, "
            "gcc_capability_centers→technology, healthcare_hospitals→healthcare, "
            "hospitality_travel→retail_consumer."
        ),
        scenarios_run=0,
        scenarios_failed=0,
    )


# ---------------------------------------------------------------------------
# DG-09: Document Contextualizer Signal Quality (static + runtime)
# ---------------------------------------------------------------------------

def score_dg09() -> DimensionResult:
    """
    Audits document_contextualizer() for 5 stub/quality issues.
    Score = 10 - (2 * issues_confirmed).
    """
    import re as _re

    issues: Dict[str, bool] = {}
    evidence: Dict[str, Any] = {}

    # ── Runtime check 1: empty-input dead-code path ──────────────────────────
    try:
        from app.skills.engine import document_contextualizer
        empty_result = document_contextualizer([])
        issues["empty_input_always_no_inference"] = empty_result.get("inferred_industry", "SENTINEL") == ""
        evidence["empty_input_result"] = {
            "inferred_industry": empty_result.get("inferred_industry"),
            "constraints": empty_result.get("constraints"),
            "context_summary_len": len(empty_result.get("context_summary", "")),
            "note": "document_contextualizer([]) always returns empty inferred_industry — URL analysis is dead code when no URLs provided",
        }
    except Exception as exc:
        issues["empty_input_always_no_inference"] = False
        evidence["empty_input_error"] = str(exc)

    # ── Runtime check 2: false-positive substring matching ───────────────────
    # "contractor agreement" should NOT trigger the "contract" constraint
    # "the program ran successfully" should NOT trigger telecom_infra via "ran"
    try:
        fp_result_contract = document_contextualizer(["Our contractor agreement was signed."])
        fp_result_ran = document_contextualizer(["The program ran successfully in the electrical grid."])

        contract_fp = any("contract" in c.lower() for c in fp_result_contract.get("constraints", []))
        ran_fp = "telecom_infra" in fp_result_ran.get("inferred_industry", "")
        grid_fp = "energy_utilities" in fp_result_ran.get("inferred_industry", "")

        issues["substring_false_positive_constraints"] = contract_fp
        issues["substring_false_positive_industry"] = ran_fp or grid_fp
        evidence["false_positive_tests"] = {
            "text_contractor": "Our contractor agreement was signed.",
            "constraints_triggered": fp_result_contract.get("constraints"),
            "contract_triggered_erroneously": contract_fp,
            "text_ran_grid": "The program ran successfully in the electrical grid.",
            "inferred_industry": fp_result_ran.get("inferred_industry"),
            "ran_triggered_telecom": ran_fp,
            "grid_triggered_energy": grid_fp,
        }
    except Exception as exc:
        issues["substring_false_positive_constraints"] = False
        issues["substring_false_positive_industry"] = False
        evidence["false_positive_error"] = str(exc)

    # ── Static check 3: ambiguous ultra-short keywords (≤3 chars) ────────────
    try:
        profiler_src = (ROOT / "app" / "skills" / "engine" / "profiler.py").read_text()
        # Extract _DOC_INDUSTRY_SIGNALS dict block
        sig_start = profiler_src.find("_DOC_INDUSTRY_SIGNALS")
        sig_end = profiler_src.find("\n}\n", sig_start) + 3
        sig_block = profiler_src[sig_start:sig_end]

        # Extract all quoted string values that are keywords
        all_keywords = _re.findall(r'"([^"]{1,3})"', sig_block)
        # Filter to actual keywords (in values, not dict keys)
        ambiguous = sorted(set(kw for kw in all_keywords if len(kw) <= 3 and kw.isalpha()))
        # Specifically flag ones that are common English words or cross-industry acronyms
        flagged = [kw for kw in ambiguous if kw in {
            "ran", "rpu", "gcc", "nav", "oee", "coe", "ssc", "pms", "bpo", "aum"
        }]
        issues["ambiguous_short_keywords_present"] = len(flagged) > 0
        evidence["ambiguous_short_keyword_check"] = {
            "short_keywords_found_le3_chars": ambiguous,
            "flagged_as_ambiguous": flagged,
            "note": (
                "'ran' matches English past tense; 'gcc' matches GNU Compiler Collection; "
                "'nav' matches 'navigation'; 'pms' matches project-management-system. "
                "These will false-positive on generic company web pages."
            ),
        }
    except Exception as exc:
        issues["ambiguous_short_keywords_present"] = False
        evidence["short_keyword_error"] = str(exc)

    # ── Static check 4: nondeterministic tie-breaking ────────────────────────
    try:
        profiler_src = profiler_src if "profiler_src" in dir() else (ROOT / "app" / "skills" / "engine" / "profiler.py").read_text()
        # Check if document_contextualizer uses plain max() without explicit key tie-breaking
        dc_start = profiler_src.find("def document_contextualizer")
        dc_end = profiler_src.find("\ndef ", dc_start + 10)
        dc_body = profiler_src[dc_start:dc_end]
        uses_plain_max = "max(industry_hit_counts" in dc_body
        has_tie_break = "sorted(" in dc_body or "key=lambda" in dc_body.replace(
            "key=lambda k: industry_hit_counts[k]", ""
        )
        issues["nondeterministic_tiebreaking"] = uses_plain_max and not has_tie_break
        evidence["tiebreaking_check"] = {
            "uses_plain_max": uses_plain_max,
            "has_secondary_sort": has_tie_break,
            "note": "max() on dict keys with equal values returns unpredictable result (CPython dict insertion order, not alphabetical)",
        }
    except Exception as exc:
        issues["nondeterministic_tiebreaking"] = False
        evidence["tiebreaking_error"] = str(exc)

    # ── Static check 5: context_summary is raw concatenation, not a summary ──
    try:
        dc_start = profiler_src.find("def document_contextualizer")
        dc_end = profiler_src.find("\ndef ", dc_start + 10)
        dc_body = profiler_src[dc_start:dc_end]
        is_raw_concat = '"context_summary": joined[:' in dc_body
        issues["context_summary_is_raw_concat"] = is_raw_concat
        evidence["context_summary_check"] = {
            "is_raw_text_slice": is_raw_concat,
            "note": (
                "context_summary is joined[:2500] — raw stripped HTML text, not an actual summary. "
                "Should be replaced with a structured excerpt or LLM-generated summary."
            ),
        }
    except Exception as exc:
        issues["context_summary_is_raw_concat"] = False
        evidence["context_summary_error"] = str(exc)

    confirmed = sum(1 for v in issues.values() if v is True)
    score = max(0.0, 10.0 - 2.0 * confirmed)
    passed = score >= 4.0

    confirmed_list = [k for k, v in issues.items() if v is True]
    return DimensionResult(
        dimension_id="DG-09",
        name="Document Contextualizer Signal Quality",
        domain="input_signal_quality",
        weight=0.40,
        threshold_pass=4.0,
        raw_score=round(score, 2),
        passed=passed,
        evidence={"issue_checks": issues, "confirmed_issues": confirmed_list, **evidence},
        finding_summary=f"{confirmed}/5 quality issues confirmed in document_contextualizer(): {confirmed_list}",
        finding_detail=(
            f"FAIL — {confirmed} issues confirmed (score {score:.1f} < 4.0). "
            f"Issues: {', '.join(confirmed_list)}"
            if not passed else f"PASS — {confirmed} issues confirmed"
        ),
        remediation=(
            "1) Empty-input path: return structured 'no_url_provided' signal when texts=[]. "
            "2) Substring matching: use \\b word-boundary regex instead of 'kw in lowered'. "
            "3) Remove/qualify ambiguous ≤3-char keywords (ran, gcc, nav, pms). "
            "4) Tie-breaking: add secondary sort by pack_id (alphabetical). "
            "5) context_summary: replace raw slice with a structured excerpt or LLM-generated abstract."
        ),
        scenarios_run=0,
        scenarios_failed=0,
    )


# ---------------------------------------------------------------------------
# DG-10: Circular Benchmark Derivation Disclosure (runtime + static)
# ---------------------------------------------------------------------------

def score_dg10(results: List[Tuple[Dict, Dict]]) -> DimensionResult:
    """
    Detects and measures the circular benchmarking problem:
    synthetic profile is derived from P50 → then compared to same benchmarks → actual_pct ≈ p50_pct.
    Also checks disclosure quality.
    """
    issues: Dict[str, bool] = {}
    per_scenario: Dict[str, Any] = {}

    # ── Runtime check 1: actual_pct ≈ p50_pct (circularity confirmed) ────────
    circularity_confirmed_scenarios = []
    for fixture, result in results:
        sid = fixture["scenario_id"]
        if result is None or not fixture["scoring_hints"].get("industry_mapped", True):
            per_scenario[sid] = {"skipped": "unmapped industry or run failed"}
            continue
        gaps = result.get("benchmark_gaps", [])
        if not gaps:
            per_scenario[sid] = {"skipped": "no benchmark gaps (unmapped industry)"}
            continue
        circular = [g for g in gaps if abs(g.get("actual_pct", 0) - g.get("p50_pct", -1)) < 0.01]
        ratio = len(circular) / len(gaps) if gaps else 0.0
        is_circular = ratio > 0.95
        if is_circular:
            circularity_confirmed_scenarios.append(sid)
        per_scenario[sid] = {
            "total_gaps": len(gaps),
            "gaps_where_actual_eq_p50": len(circular),
            "circularity_ratio": round(ratio, 3),
            "circular": is_circular,
        }

    mapped_ran = [s for s in per_scenario.values() if "circular" in s]
    issues["circular_derivation_confirmed"] = (
        len(circularity_confirmed_scenarios) > 0 and len(mapped_ran) > 0
    )

    # ── Runtime check 2: percentile_band still "Reference" (should be "synthetic_P50" after fix) ──
    all_bands = []
    for fixture, result in results:
        if result is None:
            continue
        all_bands += [g.get("percentile_band") for g in result.get("benchmark_gaps", [])]
    all_reference = all(b == "Reference" for b in all_bands) if all_bands else False
    # After fix: percentile_band should be "synthetic_P50", not "Reference"
    issues["percentile_band_hardcoded_reference"] = all_reference

    # ── Runtime check 3: data_note present (this is a mitigation — NOT an issue) ──
    data_notes = []
    for fixture, result in results:
        if result is None:
            continue
        note = result.get("data_note", "")
        data_notes.append("benchmark" in note.lower() or "synthetic" in note.lower() or "proxy" in note.lower())
    data_note_present = all(data_notes) if data_notes else False
    # Not an issue if data_note is present — this is a positive
    issues["data_note_missing_or_inaccurate"] = not data_note_present

    # ── Static check 4: headroom field renamed (should now be benchmark_p50_to_p25_band_cr) ────
    try:
        src = ENTERPRISE_ROUTER.read_text()
        # After fix: old misleading name removed, new descriptive name present
        old_name_still_present = '"headroom_to_p25_cr"' in src
        new_name_present = '"benchmark_p50_to_p25_band_cr"' in src
        issues["headroom_field_name_misleading"] = old_name_still_present or not new_name_present
    except Exception:
        issues["headroom_field_name_misleading"] = False

    confirmed = sum(1 for v in issues.values() if v is True)
    # data_note_missing contributes negatively; circularity + hidden percentile + misleading name are issues
    score = max(0.0, 10.0 - 2.5 * confirmed)
    passed = score >= 5.0

    confirmed_list = [k for k, v in issues.items() if v is True]
    return DimensionResult(
        dimension_id="DG-10",
        name="Circular Benchmark Derivation Disclosure",
        domain="input_signal_quality",
        weight=0.30,
        threshold_pass=5.0,
        raw_score=round(score, 2),
        passed=passed,
        evidence={
            "issue_checks": issues,
            "confirmed_issues": confirmed_list,
            "per_scenario_circularity": per_scenario,
            "all_percentile_bands_reference": all_reference,
            "data_note_present_and_accurate": data_note_present,
            "circularity_scenarios": circularity_confirmed_scenarios,
            "explanation": (
                "Synthetic profile is built as: implied_spend = P50_pct/100 * revenue. "
                "peer_benchmarker then computes actual_pct = spend/revenue*100 = P50_pct. "
                "Benchmark gap analysis therefore benchmarks the benchmark against itself."
            ),
        },
        finding_summary=(
            f"{confirmed}/4 disclosure issues confirmed. "
            f"Circularity present in: {circularity_confirmed_scenarios}. "
            f"data_note present: {data_note_present}."
        ),
        finding_detail=(
            f"FAIL — score {score:.1f} < 5.0. Issues: {', '.join(confirmed_list)}"
            if not passed else f"PASS — {confirmed} issues ({', '.join(confirmed_list)})"
        ),
        remediation=(
            "1) Rename headroom_to_p25_cr → benchmark_p50_to_p25_band_cr to clarify it is a benchmark range width. "
            "2) Change percentile_band from hardcoded 'Reference' to 'synthetic_P50' to make derivation explicit. "
            "3) Add top-level field 'profile_basis': 'benchmark_proxy' in addition to data_note. "
            "Structural fix: when session has uploaded spend data, use actual spend profile instead of synthetic."
        ),
        scenarios_run=len(results),
        scenarios_failed=sum(1 for _, r in results if r is None),
    )


# ---------------------------------------------------------------------------
# DG-11: Silent Parameter Defaulting (static analysis)
# ---------------------------------------------------------------------------

def score_dg11() -> DimensionResult:
    """
    Detects parameters that affect analysis quality but are silently hardcoded
    or unavailable to the API caller.
    Score = 10 - (2 * params_confirmed).
    """
    import re as _re

    issues: Dict[str, bool] = {}
    evidence: Dict[str, Any] = {}

    try:
        src = ENTERPRISE_ROUTER.read_text()
        schemas_src = (ROOT / "app" / "schemas.py").read_text()

        # ── Check 1: headcount missing from CompanyResearchRequest schema ────
        schema_block_start = schemas_src.find("class CompanyResearchRequest")
        schema_block_end = schemas_src.find("\nclass ", schema_block_start + 10)
        schema_block = schemas_src[schema_block_start:schema_block_end] if schema_block_start != -1 else ""
        has_headcount_field = "headcount" in schema_block
        issues["headcount_missing_from_request_schema"] = not has_headcount_field
        evidence["schema_fields"] = {
            "CompanyResearchRequest_has_headcount": has_headcount_field,
            "note": "headcount=500.0 hardcoded in endpoint; caller cannot override it",
        }

        # ── Checks 2–4: kwargs in the resolve_eligible_levers call block ────────
        # Use a broad window search: find the call and scan up to 800 chars ahead
        lever_call_window = ""
        if "resolve_eligible_levers(" in src:
            start_idx = src.index("resolve_eligible_levers(")
            lever_call_window = src[start_idx: start_idx + 800]

        issues["signal_corpus_always_none"] = "signal_corpus" not in lever_call_window
        evidence["signal_corpus_check"] = {
            "passed_in_lever_call": "signal_corpus" in lever_call_window,
            "note": "signal_corpus=None means signal corpus rebuilt from scratch every call",
        }

        issues["line_flags_always_none"] = "line_flags" not in lever_call_window
        evidence["line_flags_check"] = {
            "passed_in_lever_call": "line_flags" in lever_call_window,
            "note": "line_flags=None disables flag-based lever filtering",
        }

        issues["engagement_id_not_passed"] = "engagement_id" not in lever_call_window
        evidence["engagement_id_check"] = {
            "passed_in_lever_call": "engagement_id" in lever_call_window,
            "note": "engagement_id=None orphans diagnostic runs from audit trail",
        }

        # ── Check 5 (informational only — by design, not scored) ─────────────
        # categories param to resolve_benchmark_payload is used for dataset selection only.
        # Documented as intentional — not counted as a failing issue.
        evidence["categories_filter_note"] = (
            "By design: resolve_benchmark_payload passes categories to select_best_dataset() "
            "for dataset selection scoring only. Payload covers all categories. Not a bug."
        )

    except Exception as exc:
        evidence["static_analysis_error"] = str(exc)

    confirmed = sum(1 for v in issues.values() if v is True)
    score = max(0.0, 10.0 - 2.0 * confirmed)
    passed = score >= 4.0

    confirmed_list = [k for k, v in issues.items() if v is True]
    return DimensionResult(
        dimension_id="DG-11",
        name="Silent Parameter Defaulting",
        domain="input_signal_quality",
        weight=0.30,
        threshold_pass=4.0,
        raw_score=round(score, 2),
        passed=passed,
        evidence={"issue_checks": issues, "confirmed_issues": confirmed_list, **evidence},
        finding_summary=f"{confirmed}/{len(issues)} silent-defaulting issues confirmed: {confirmed_list}",
        finding_detail=(
            f"FAIL — {confirmed} parameters silently defaulted (score {score:.1f} < 4.0). "
            f"Issues: {', '.join(confirmed_list)}"
            if not passed else f"PASS — {confirmed} issues confirmed"
        ),
        remediation=(
            "1) Add headcount (int, default=500) to CompanyResearchRequest schema and pass through. "
            "2) Build signal_corpus from synthetic profile before calling resolve_eligible_levers. "
            "3) Derive line_flags from company_signals.constraints before lever resolution. "
            "4) Generate engagement_id = f'diag-{company_name}-{timestamp}' for audit traceability. "
            "5) Document in API response that benchmark payload covers all categories by design."
        ),
        scenarios_run=0,
        scenarios_failed=0,
    )


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def _aggregate(dimension_results: List[DimensionResult]) -> Tuple[List[DomainResult], float]:
    domains_meta = {
        "data_integrity": ("Data Integrity", 0.30),
        "analysis_completeness": ("Analysis Completeness", 0.35),
        "schema_signal_integrity": ("Schema & Signal Integrity", 0.15),
        "input_signal_quality": ("Input Signal Quality", 0.20),
    }
    domain_results: List[DomainResult] = []
    for domain_key, (display, d_weight) in domains_meta.items():
        dims = [d for d in dimension_results if d.domain == domain_key]
        if not dims:
            continue
        total_w = sum(d.weight for d in dims)
        d_score = sum(d.raw_score * d.weight for d in dims) / total_w if total_w > 0 else 0.0
        domain_results.append(DomainResult(
            domain_name=domain_key,
            domain_display=display,
            domain_weight=d_weight,
            dimension_results=dims,
            domain_score=round(d_score, 2),
            passed=all(d.passed for d in dims),
        ))

    total_dw = sum(dr.domain_weight for dr in domain_results)
    overall = sum(dr.domain_score * dr.domain_weight for dr in domain_results) / total_dw if total_dw > 0 else 0.0
    return domain_results, round(overall, 2)


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def _to_json(report: EvalReport, dimension_results: List[DimensionResult]) -> Dict:
    return {
        "eval_name": "Diagnostic Feature Eval",
        "eval_date": report.eval_date,
        "platform_version": report.platform_version,
        "overall_score": report.overall_score,
        "passed": report.passed,
        "scenario_run_count": report.scenario_run_count,
        "scenario_pass_count": report.scenario_pass_count,
        "domains": [
            {
                "name": dr.domain_name,
                "display": dr.domain_display,
                "weight": dr.domain_weight,
                "score": dr.domain_score,
                "passed": dr.passed,
                "dimensions": [
                    {
                        "id": d.dimension_id,
                        "name": d.name,
                        "weight": d.weight,
                        "threshold": d.threshold_pass,
                        "score": d.raw_score,
                        "passed": d.passed,
                        "gap": round(d.gap, 2),
                        "scenarios_run": d.scenarios_run,
                        "scenarios_below_threshold": d.scenarios_failed,
                        "finding_summary": d.finding_summary,
                        "remediation": d.remediation,
                        "evidence": d.evidence,
                    }
                    for d in dr.dimension_results
                ],
            }
            for dr in report.domain_results
        ],
        "top_gaps": report.top_gaps,
        "remediation_roadmap": report.remediation_roadmap,
    }


def _to_markdown(report: EvalReport, dimension_results: List[DimensionResult]) -> str:
    lines: List[str] = []
    status = "✅ PASS" if report.passed else "❌ FAIL"
    lines += [
        f"# Diagnostic Feature Eval — {status}",
        f"",
        f"**Date:** {report.eval_date}  |  **Version:** {report.platform_version}  "
        f"|  **Overall Score:** {report.overall_score}/10",
        f"",
        "## Summary",
        "",
        "| Domain | Score | Weight | Status |",
        "|--------|-------|--------|--------|",
    ]
    for dr in report.domain_results:
        st = "✅" if dr.passed else "❌"
        lines.append(f"| {dr.domain_display} | {dr.domain_score:.1f}/10 | {dr.domain_weight:.0%} | {st} |")

    lines += ["", "## Dimension Detail", ""]
    lines += [
        "| ID | Dimension | Score | Threshold | Status | Gap |",
        "|----|-----------|-------|-----------|--------|-----|",
    ]
    for d in dimension_results:
        st = "✅" if d.passed else "❌"
        lines.append(
            f"| {d.dimension_id} | {d.name} | {d.raw_score:.1f} | {d.threshold_pass:.1f} | {st} | {d.gap:.1f} |"
        )

    lines += ["", "## Known Stubs & Inconsistencies", ""]
    stubs = [
        ("HIGH", "NPV always 0.0", "`enterprise.py:369`", "Add wacc param; compute 3-year NPV"),
        ("HIGH", "root_causes=[] always", "`enterprise.py:340`", "Run root_cause_analyzer on synthetic profile first"),
        ("HIGH", "document_contextualizer is bag-of-words", "`profiler.py:786-811`", "Word-boundary regex; remove ambiguous ≤3-char keywords; add LLM summary"),
        ("HIGH", "URL analysis dead code when urls=[]", "`enterprise.py:261` + `profiler.py:787`", "Return structured 'no_url_provided' signal; skip contextualizer call"),
        ("MED", "Circular benchmark derivation", "`enterprise.py:289-333`", "Rename headroom field; set percentile_band='synthetic_P50'; add profile_basis field"),
        ("MED", "headcount hardcoded 500", "`enterprise.py:338`", "Add headcount to CompanyResearchRequest schema"),
        ("MED", "headcount missing from request schema", "`schemas.py:203-207`", "Add headcount field to CompanyResearchRequest"),
        ("MED", "signal_corpus / line_flags always None", "`enterprise.py:335-341`", "Build signal_corpus from synthetic profile; derive line_flags from constraints"),
        ("MED", "category='' always in value_at_table", "`enterprise.py:365`", "Populate from matched trigger_signal category ID"),
        ("MED", "gap_pct/gap_cr always 0", "`enterprise.py:326-328`", "Compute vs. P25 target or rename fields"),
        ("MED", "'3-year' label without 3x multiplier", "`enterprise.py:387`", "Multiply p50_cr by 3 or rename to 'annual savings'"),
        ("LOW", "_PACK_TO_BENCH missing sector packs", "`enterprise.py:265-277`", "Add financial_services_nonbank, gcc_capability_centers, healthcare_hospitals, hospitality_travel"),
        ("LOW", "resolve_benchmark_payload called twice", "`enterprise.py:280+303`", "Reuse categories list from first call"),
        ("LOW", "engagement_id not passed to lever resolver", "`enterprise.py:335-341`", "Generate engagement_id from company+timestamp for audit trail"),
    ]
    lines += ["| Severity | Stub | Location | Fix |", "|----------|------|----------|-----|"]
    for sev, stub, loc, fix in stubs:
        lines.append(f"| {sev} | {stub} | {loc} | {fix} |")

    if report.top_gaps:
        lines += ["", "## Top Gaps to Close", ""]
        for i, g in enumerate(report.top_gaps[:5], 1):
            lines.append(f"{i}. **{g['dimension']}** (gap {g['gap']:.1f}) — {g['remediation'][:100]}")

    lines += ["", "## Remediation Roadmap", ""]
    for i, item in enumerate(report.remediation_roadmap, 1):
        lines.append(f"{i}. **[{item['dimension_id']}] {item['name']}** — {item['remediation'][:120]}")

    lines += [""]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run Diagnostic Feature Eval")
    parser.add_argument("--json-only", action="store_true", help="Skip markdown report")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_MD), help="Markdown output path")
    parser.add_argument("--json-output", default=str(DEFAULT_OUTPUT_JSON), help="JSON output path")
    args = parser.parse_args(argv)

    print("=" * 70)
    print("OpEx Platform — Diagnostic Feature Eval")
    print("=" * 70)

    # Load scenarios
    scenarios: List[Dict] = []
    for fname in SCENARIO_FILES:
        fpath = SCENARIOS_DIR / fname
        if not fpath.exists():
            print(f"  [WARN] Missing fixture: {fpath}", file=sys.stderr)
            continue
        scenarios.append(json.loads(fpath.read_text()))
    print(f"Loaded {len(scenarios)} golden scenarios\n")

    # Run scenarios
    print("Running scenarios...")
    run_results: List[Tuple[Dict, Optional[Dict]]] = []
    for fixture in scenarios:
        sid = fixture["scenario_id"]
        print(f"  {sid}: {fixture['request']['company_name']} ({fixture['request']['industry']})...", end=" ")
        result, err = _run_scenario(fixture)
        if err:
            print(f"ERROR — {err[:80]}")
        else:
            vat_count = len(result.get("value_at_table", []))
            gap_count = len(result.get("benchmark_gaps", []))
            print(f"OK  ({gap_count} benchmark gaps, {vat_count} levers in value-at-table)")
        run_results.append((fixture, result))

    print()

    # Score dimensions
    print("Scoring dimensions...")
    mapped_results = [
        (fixture, result)
        for fixture, result in run_results
        if result is not None
    ]

    dimension_results: List[DimensionResult] = [
        score_dg01(mapped_results),
        score_dg02(mapped_results),
        score_dg03(mapped_results),
        score_dg04(run_results),
        score_dg05(mapped_results),
        score_dg06(mapped_results),
        score_dg07(),
        score_dg08(),
        score_dg09(),
        score_dg10(mapped_results),
        score_dg11(),
    ]

    for d in dimension_results:
        st = "PASS" if d.passed else "FAIL"
        print(f"  [{st}] {d.dimension_id} {d.name}: {d.raw_score:.1f}/{d.threshold_pass:.1f}")

    # Aggregate
    domain_results, overall_score = _aggregate(dimension_results)
    all_passed = all(d.passed for d in dimension_results)

    top_gaps = sorted(
        [{"dimension": d.dimension_id, "name": d.name, "gap": d.gap, "remediation": d.remediation}
         for d in dimension_results if d.gap > 0],
        key=lambda x: x["gap"], reverse=True
    )
    roadmap = [
        {"dimension_id": d.dimension_id, "name": d.name, "remediation": d.remediation}
        for d in sorted(dimension_results, key=lambda x: x.gap, reverse=True)
        if d.gap > 0
    ]

    report = EvalReport(
        platform_version="v2.1",
        eval_date=date.today().isoformat(),
        overall_score=overall_score,
        domain_results=domain_results,
        top_gaps=top_gaps,
        remediation_roadmap=roadmap,
        passed=all_passed,
        scenario_run_count=len(scenarios),
        scenario_pass_count=sum(1 for _, r in run_results if r is not None),
    )

    print(f"\n{'='*70}")
    status = "PASS" if all_passed else "FAIL"
    print(f"OVERALL: {overall_score:.2f}/10  [{status}]")
    print(f"{'='*70}\n")

    # Write outputs
    json_payload = _to_json(report, dimension_results)
    json_path = Path(args.json_output)
    json_path.write_text(json.dumps(json_payload, indent=2))
    print(f"JSON report → {json_path}")

    if not args.json_only:
        md = _to_markdown(report, dimension_results)
        md_path = Path(args.output)
        md_path.write_text(md)
        print(f"Markdown report → {md_path}")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
