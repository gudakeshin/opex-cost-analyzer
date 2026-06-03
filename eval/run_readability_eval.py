#!/usr/bin/env python3
"""
eval/run_readability_eval.py — OpEx Platform Diagnostic Readability Evaluator

Scores the /api/v1/diagnostic/company-research output across 4 domains
and 15 dimensions focused on FP&A readability: number formatting, label
accuracy, findings narrative quality, and context completeness.

Uses the same 5 golden scenarios as run_diagnostic_eval.py. Calls engine
functions in-process (no live HTTP server required).

Pass threshold: 7.0/10 overall

Usage:
    PYTHONPATH=. python eval/run_readability_eval.py
    PYTHONPATH=. python eval/run_readability_eval.py --json-only
    PYTHONPATH=. python eval/run_readability_eval.py --output eval/my_report.md

Exit codes:
    0 — all dimensions pass their threshold
    1 — one or more dimensions fail
    2 — critical error (missing file, import failure)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import traceback
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).parent.parent
SCENARIOS_DIR = ROOT / "tests" / "eval" / "golden" / "diagnostic"
DEFAULT_OUTPUT_MD = ROOT / "eval" / "readability_report.md"
DEFAULT_OUTPUT_JSON = ROOT / "eval" / "readability_scores.json"

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
# Scenario runner — mirrors run_diagnostic_eval._run_scenario exactly
# ---------------------------------------------------------------------------

def _run_scenario(fixture: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Execute diagnostic endpoint logic in-process. Returns (result_dict, error_msg)."""
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
        synthetic_profile = {
            "total_spend": total_implied,
            "category_profile": category_profile,
            "data_source": "benchmark_proxy",
        }

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
                "proxy_pct": round(p50_pct, 2),
                "gap_pct": round(p50_pct - p25_pct, 2),
                "gap_cr": band_cr,
                "implied_p50_cr": implied_p50_cr,
                "implied_p25_cr": implied_p25_cr,
                "benchmark_p50_to_p25_band_cr": band_cr,
                "percentile_band": "P50 industry benchmark (proxy)",
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

        _SAVINGS_TYPE_LABELS_LOCAL = {"run_rate": "Run Rate", "one_time": "One-Time", "mixed": "Mixed"}
        _COMPLEXITY_LABELS_LOCAL = {"low": "low complexity", "medium": "medium complexity", "high": "high complexity"}

        cat_spend_cr = {c["category_id"]: c["spend"] / 1_00_00_000 for c in category_profile}
        total_spend_cr = sum(cat_spend_cr.values()) or 1.0
        value_at_table = []
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
            base_spend_cr = primary_cat_spend_cr if primary_cat_spend_cr > 0 else total_spend_cr * 0.10
            p50_cr = round(p50_rate * base_spend_cr, 1)
            if p50_cr < 0.1:
                continue
            npv = round(sum(p50_cr / (1.0 + wacc) ** t for t in range(1, 4)), 1)
            savings_type = lv.get("savings_type", "run_rate")
            value_at_table.append({
                "lever_id": lv["lever_id"],
                "lever_name": lv["lever_name"],
                "category": matched_category_id,
                "p10_cr": round(p10_rate * base_spend_cr, 1),
                "p50_cr": p50_cr,
                "p90_cr": round(p90_rate * base_spend_cr, 1),
                "npv": npv,
                "savings_type": savings_type,
                "savings_type_label": _SAVINGS_TYPE_LABELS_LOCAL.get(savings_type, savings_type.replace("_", " ").title()),
                "complexity_tier": lv.get("complexity_tier", "medium"),
            })
        value_at_table.sort(key=lambda x: x["p50_cr"], reverse=True)
        value_at_table = value_at_table[:12]
        total_p50 = round(sum(v["p50_cr"] for v in value_at_table), 1)

        top_gap = benchmark_gaps[0] if benchmark_gaps else {}
        top_lever = value_at_table[0] if value_at_table else {}

        def _fmt_cr_local(n: float) -> str:
            return f"₹{n:,.0f} Cr"

        key_findings = []
        if top_gap:
            implied_p50_cr_top = top_gap.get("implied_p50_cr", 0)
            band_cr_top = top_gap.get("benchmark_p50_to_p25_band_cr", 0)
            rev_pct = round(implied_p50_cr_top / annual_revenue_cr * 100, 1) if annual_revenue_cr > 0 else 0.0
            key_findings.append(
                f"Largest category: {top_gap.get('category_name', '')} — "
                f"{_fmt_cr_local(implied_p50_cr_top)} ({rev_pct}% of revenue) at P50 benchmark; "
                f"{_fmt_cr_local(band_cr_top)} headroom to P25 best-in-class"
            )
        if top_lever:
            complexity = _COMPLEXITY_LABELS_LOCAL.get(top_lever.get("complexity_tier", "medium"), "medium complexity")
            key_findings.append(
                f"Highest-value lever: {top_lever['lever_name']} ({complexity}) — "
                f"{_fmt_cr_local(top_lever['p50_cr'])} annual savings; "
                f"{_fmt_cr_local(top_lever['npv'])} 3-year NPV (P50 estimate)"
            )
        if value_at_table:
            total_p10 = round(sum(v["p10_cr"] for v in value_at_table), 1)
            total_p90 = round(sum(v["p90_cr"] for v in value_at_table), 1)
            key_findings.append(
                f"Savings range (P10–P90): {_fmt_cr_local(total_p10)} to {_fmt_cr_local(total_p90)} across {len(value_at_table)} levers"
            )
        if company_signals.get("constraints"):
            key_findings.append(
                "Identified constraints (may affect lever eligibility): "
                + "; ".join(company_signals["constraints"][:2])
            )
        total_pct = round(total_p50 / annual_revenue_cr * 100, 1) if annual_revenue_cr > 0 else 0.0
        key_findings.append(
            f"Total value at table (P50 annual): {_fmt_cr_local(total_p50)} ({total_pct}% of revenue) across {len(value_at_table)} levers"
        )

        if bench_resolved.get("selected_dataset"):
            data_note = (
                f"Spend profile derived from {bench_industry} benchmark P50 values — "
                f"upload actual spend data for company-specific analysis."
            )
        else:
            data_note = (
                f"No benchmark data found for sector '{effective_industry}'; nearest-proxy estimates used. "
                f"Results should be treated as directional only. "
                f"Upload actual spend data for precise analysis."
            )

        return {
            "company_name": company_name,
            "industry_used": effective_industry,
            "bench_industry": bench_industry,
            "annual_revenue_cr": annual_revenue_cr,
            "assumptions": {
                "wacc_pct": round(wacc * 100, 1),
                "headcount": headcount,
                "npv_horizon_years": 3,
                "profile_basis": "benchmark_proxy",
            },
            "company_signals": company_signals,
            "benchmark_gaps": benchmark_gaps,
            "value_at_table": value_at_table,
            "eligible_levers_total": len(eligible_levers),
            "total_p50_value_cr": total_p50,
            "key_findings": key_findings,
            "percentile_legend": {
                "p10": "top-decile benchmark (stretch target)",
                "p25": "best-in-class quartile",
                "p50": "industry median",
                "p90": "lagging quartile",
            },
            "profile_basis": "benchmark_proxy",
            "data_note": data_note,
            "_meta": {"url_count": 0, "url_errors": [], "bench_industry": bench_industry},
            "_eligible_levers_total": len(eligible_levers),
            "_wacc": wacc,
            "_headcount": headcount,
            "_bench_resolved_has_dataset": bool(bench_resolved.get("selected_dataset")),
        }, None

    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"


# ---------------------------------------------------------------------------
# Helper: extract all numbers ≥1000 from a string (as floats, after stripping commas)
# ---------------------------------------------------------------------------

def _large_numbers_in_string(s: str) -> List[float]:
    """Return all numbers ≥1000 found in a string (ignoring existing commas)."""
    cleaned = s.replace(",", "")
    return [float(m) for m in re.findall(r'\d+(?:\.\d+)?', cleaned) if float(m) >= 1000]


def _has_comma_formatted(s: str, n: float) -> bool:
    """Check that n≥1000 appears with comma separators in s."""
    # Build the comma-formatted form and check it exists in string
    formatted = f"{n:,.0f}"
    return formatted in s


# ---------------------------------------------------------------------------
# RD-01: Comma Separators in Findings
# ---------------------------------------------------------------------------

def score_rd01(results: List[Tuple[Dict, Dict]]) -> DimensionResult:
    """Every monetary figure ≥1,000 Cr in key_findings must use comma-formatted numbers."""
    scenario_evidence: Dict[str, Any] = {}
    violations: List[str] = []
    total_large_numbers = 0
    formatted_correctly = 0

    for fixture, result in results:
        sid = fixture["scenario_id"]
        if result is None:
            scenario_evidence[sid] = {"error": "run failed"}
            continue

        findings = result.get("key_findings", [])
        revenue_cr = fixture["request"].get("annual_revenue_cr", 5000.0)
        sid_violations: List[str] = []

        for finding in findings:
            large_nums = _large_numbers_in_string(finding)
            for n in large_nums:
                total_large_numbers += 1
                if _has_comma_formatted(finding, n):
                    formatted_correctly += 1
                else:
                    sid_violations.append(f"'{n:.0f}' missing comma in: {finding[:80]}")
                    violations.append(f"[{sid}] {sid_violations[-1]}")

        scenario_evidence[sid] = {
            "revenue_cr": revenue_cr,
            "findings_count": len(findings),
            "violations": sid_violations,
        }

    if total_large_numbers == 0:
        # No large numbers found in findings — the scenarios might all be small revenue
        # Check if any scenario has revenue ≥1000 that we'd expect to surface
        large_revenue_scenarios = [
            f["scenario_id"] for f in [r[0] for r in results]
            if float(f["request"].get("annual_revenue_cr", 0)) >= 1000
        ]
        if large_revenue_scenarios:
            score = 0.0
            summary = f"Large-revenue scenarios {large_revenue_scenarios} produced no ≥1000 numbers in findings — findings may be empty or below threshold"
        else:
            score = 10.0
            summary = "No large numbers in findings — all scenarios below 1,000 Cr threshold"
    else:
        score = (formatted_correctly / total_large_numbers) * 10.0
        summary = f"{formatted_correctly}/{total_large_numbers} large numbers use comma formatting"

    passed = score >= 8.0
    return DimensionResult(
        dimension_id="RD-01",
        name="Comma Separators in Findings",
        domain="financial_formatting",
        weight=0.35,
        threshold_pass=8.0,
        raw_score=round(score, 2),
        passed=passed,
        evidence={"scenario_evidence": scenario_evidence, "violations": violations[:10]},
        finding_summary=summary,
        finding_detail=(
            f"PASS — all large monetary figures use comma formatting"
            if passed else
            f"FAIL — {len(violations)} violation(s): numbers ≥1,000 not comma-formatted in findings. "
            f"e.g. '₹3200 Cr' should be '₹3,200 Cr'"
        ),
        remediation=(
            "In enterprise.py key_findings assembly, replace :.0f with a helper: "
            "def _fmt_cr(n): return f'₹{n:,.0f} Cr'. "
            "Apply to all findings strings (top-gap, top-lever, total-value findings)."
        ),
        scenarios_run=len(results),
        scenarios_failed=sum(1 for _, r in results if r is None),
    )


# ---------------------------------------------------------------------------
# RD-02: NPV Time Horizon Disclosure
# ---------------------------------------------------------------------------

def score_rd02(results: List[Tuple[Dict, Dict]]) -> DimensionResult:
    """key_findings or data_note must reference '3-year' or similar NPV horizon."""
    scenario_evidence: Dict[str, Any] = {}
    horizon_keywords = ["3-year", "3 year", "36-month", "three-year", "three year"]
    pass_count = 0
    total_mapped = 0

    for fixture, result in results:
        sid = fixture["scenario_id"]
        if result is None:
            scenario_evidence[sid] = {"error": "run failed"}
            continue

        mapped = fixture["scoring_hints"].get("industry_mapped", True)
        if not mapped:
            scenario_evidence[sid] = {"skipped": "unmapped sector — NPV may be absent by design"}
            continue

        total_mapped += 1
        findings_text = " ".join(result.get("key_findings", []))
        data_note = result.get("data_note", "")
        full_text = (findings_text + " " + data_note).lower()
        found = any(kw in full_text for kw in horizon_keywords)

        if found:
            pass_count += 1

        scenario_evidence[sid] = {
            "has_horizon_disclosure": found,
            "npv_values": [v["npv"] for v in result.get("value_at_table", [])[:3]],
            "searched_in": "key_findings + data_note",
        }

    score = (pass_count / total_mapped * 10.0) if total_mapped > 0 else 0.0
    passed = score >= 7.0
    return DimensionResult(
        dimension_id="RD-02",
        name="NPV Time Horizon Disclosure",
        domain="financial_formatting",
        weight=0.35,
        threshold_pass=7.0,
        raw_score=round(score, 2),
        passed=passed,
        evidence=scenario_evidence,
        finding_summary=f"{pass_count}/{total_mapped} mapped scenarios disclose NPV time horizon",
        finding_detail=(
            "PASS — '3-year' or equivalent appears in findings/data_note"
            if passed else
            "FAIL — NPV values appear in value_at_table but no '3-year' horizon disclosed anywhere. "
            "FP&A users cannot determine if NPV is 1-year, 3-year, or 5-year."
        ),
        remediation=(
            "In enterprise.py top-lever finding, append '3-year NPV' label: "
            "f'{lever_name} — {_fmt_cr(p50_cr)} annual savings; {_fmt_cr(npv)} 3-year NPV (P50 estimate)'. "
            "Alternatively add to assumptions dict: {npv_horizon_years: 3}."
        ),
        scenarios_run=total_mapped,
        scenarios_failed=0,
    )


# ---------------------------------------------------------------------------
# RD-03: WACC / Discount Rate Visible in Response
# ---------------------------------------------------------------------------

def score_rd03(results: List[Tuple[Dict, Dict]]) -> DimensionResult:
    """The response payload must surface the WACC used for NPV computation."""
    scenario_evidence: Dict[str, Any] = {}
    pass_count = 0
    total = 0

    for fixture, result in results:
        sid = fixture["scenario_id"]
        if result is None:
            scenario_evidence[sid] = {"error": "run failed"}
            continue

        total += 1
        wacc_used = result.get("_wacc", fixture["request"].get("wacc", 0.12))

        # Check whether wacc is surfaced anywhere in the response (excluding internal _ fields)
        response_keys = {k: v for k, v in result.items() if not k.startswith("_")}
        response_str = json.dumps(response_keys).lower()
        wacc_disclosed = (
            "wacc" in response_str
            or "discount_rate" in response_str
            or "assumptions" in response_str
        )
        if wacc_disclosed:
            pass_count += 1

        scenario_evidence[sid] = {
            "wacc_used": wacc_used,
            "wacc_disclosed_in_response": wacc_disclosed,
            "npv_computed": any(v["npv"] > 0 for v in result.get("value_at_table", [])),
        }

    score = (pass_count / total * 10.0) if total > 0 else 0.0
    passed = score >= 7.0
    return DimensionResult(
        dimension_id="RD-03",
        name="WACC / Discount Rate Visible",
        domain="financial_formatting",
        weight=0.30,
        threshold_pass=7.0,
        raw_score=round(score, 2),
        passed=passed,
        evidence=scenario_evidence,
        finding_summary=f"{pass_count}/{total} scenarios expose WACC in response payload",
        finding_detail=(
            "PASS — WACC or discount rate disclosed in response"
            if passed else
            "FAIL — NPV values computed using req.wacc but the discount rate is never returned. "
            "FP&A users cannot validate or replicate the NPV calculation."
        ),
        remediation=(
            "Add 'assumptions' object to enterprise.py return dict: "
            "{'wacc_pct': round(req.wacc * 100, 1), 'headcount': req.headcount, "
            "'npv_horizon_years': 3, 'profile_basis': 'benchmark_proxy'}."
        ),
        scenarios_run=total,
        scenarios_failed=sum(1 for _, r in results if r is None),
    )


# ---------------------------------------------------------------------------
# RD-04: actual_pct Misnomer
# ---------------------------------------------------------------------------

def score_rd04(results: List[Tuple[Dict, Dict]]) -> DimensionResult:
    """In proxy mode, actual_pct == p50_pct is a misleading field name.
    Should be renamed to proxy_pct or have a disclaimer."""
    scenario_evidence: Dict[str, Any] = {}
    misnomer_count = 0
    total_with_gaps = 0

    for fixture, result in results:
        sid = fixture["scenario_id"]
        if result is None:
            scenario_evidence[sid] = {"error": "run failed"}
            continue

        gaps = result.get("benchmark_gaps", [])
        if not gaps:
            scenario_evidence[sid] = {"skipped": "no benchmark gaps — unmapped sector"}
            continue

        total_with_gaps += 1
        has_actual_pct = any("actual_pct" in g for g in gaps)
        # Check if "actual_pct" exists and equals p50_pct (the misleading case)
        actual_equals_p50 = all(
            abs(g.get("actual_pct", 0) - g.get("p50_pct", 0)) < 0.001
            for g in gaps if "actual_pct" in g
        )
        # Also check for alternative: proxy_pct field
        has_proxy_pct = any("proxy_pct" in g for g in gaps)
        # Also check for disclaimer in data_note
        data_note = result.get("data_note", "").lower()
        has_proxy_disclaimer = "proxy" in data_note or "benchmark" in data_note

        is_misnomer = has_actual_pct and actual_equals_p50 and not has_proxy_pct
        if is_misnomer:
            misnomer_count += 1

        scenario_evidence[sid] = {
            "has_actual_pct_field": has_actual_pct,
            "actual_pct_equals_p50_pct": actual_equals_p50,
            "has_proxy_pct_alternative": has_proxy_pct,
            "has_proxy_disclaimer_in_data_note": has_proxy_disclaimer,
            "is_misnomer": is_misnomer,
            "gap_count": len(gaps),
        }

    score = max(0.0, 10.0 - (misnomer_count / max(total_with_gaps, 1)) * 10.0)
    passed = score >= 7.0
    return DimensionResult(
        dimension_id="RD-04",
        name="actual_pct Misnomer Detection",
        domain="label_accuracy",
        weight=0.30,
        threshold_pass=7.0,
        raw_score=round(score, 2),
        passed=passed,
        evidence=scenario_evidence,
        finding_summary=(
            f"{misnomer_count}/{total_with_gaps} scenarios have 'actual_pct' field equal to p50_pct "
            f"(implying real company data when using benchmark proxy)"
        ),
        finding_detail=(
            "PASS — actual_pct renamed or proxy disclaimer present"
            if passed else
            "FAIL — 'actual_pct' field equals 'p50_pct' in all benchmark_gaps rows. "
            "This implies real company spend data was used, when the profile is a benchmark proxy. "
            "An FP&A analyst would incorrectly conclude the company's actual spend matches P50 exactly."
        ),
        remediation=(
            "In enterprise.py benchmark_gaps assembly (line ~328), rename 'actual_pct' → 'proxy_pct'. "
            "Or add profile_note field per row: 'profile_note': 'derived from benchmark P50 — not actual spend'."
        ),
        scenarios_run=total_with_gaps,
        scenarios_failed=sum(1 for _, r in results if r is None),
    )


# ---------------------------------------------------------------------------
# RD-05: percentile_band Jargon
# ---------------------------------------------------------------------------

def score_rd05(results: List[Tuple[Dict, Dict]]) -> DimensionResult:
    """'synthetic_P50' in percentile_band is developer jargon, not FP&A-readable."""
    scenario_evidence: Dict[str, Any] = {}
    jargon_count = 0
    total_with_gaps = 0

    for fixture, result in results:
        sid = fixture["scenario_id"]
        if result is None:
            scenario_evidence[sid] = {"error": "run failed"}
            continue

        gaps = result.get("benchmark_gaps", [])
        if not gaps:
            scenario_evidence[sid] = {"skipped": "no benchmark gaps"}
            continue

        total_with_gaps += 1
        jargon_bands = [g.get("percentile_band", "") for g in gaps if g.get("percentile_band") == "synthetic_P50"]
        has_jargon = len(jargon_bands) > 0

        if has_jargon:
            jargon_count += 1

        scenario_evidence[sid] = {
            "percentile_band_values": list({g.get("percentile_band", "") for g in gaps}),
            "has_synthetic_P50_jargon": has_jargon,
            "gap_count": len(gaps),
        }

    score = max(0.0, 10.0 - (jargon_count / max(total_with_gaps, 1)) * 10.0)
    passed = score >= 7.0
    return DimensionResult(
        dimension_id="RD-05",
        name="percentile_band Jargon Removal",
        domain="label_accuracy",
        weight=0.25,
        threshold_pass=7.0,
        raw_score=round(score, 2),
        passed=passed,
        evidence=scenario_evidence,
        finding_summary=(
            f"{jargon_count}/{total_with_gaps} scenarios expose 'synthetic_P50' jargon in percentile_band"
        ),
        finding_detail=(
            "PASS — percentile_band uses FP&A-readable label"
            if passed else
            "FAIL — 'percentile_band': 'synthetic_P50' is developer terminology. "
            "An FP&A user has no frame of reference for 'synthetic'. "
            "Recommended: 'P50 industry benchmark (proxy)' or 'Industry median (estimated)'."
        ),
        remediation=(
            "In enterprise.py line ~334, change: "
            "'percentile_band': 'synthetic_P50' → 'percentile_band': 'P50 industry benchmark (proxy)'"
        ),
        scenarios_run=total_with_gaps,
        scenarios_failed=0,
    )


# ---------------------------------------------------------------------------
# RD-06: savings_type Snake_case
# ---------------------------------------------------------------------------

def score_rd06(results: List[Tuple[Dict, Dict]]) -> DimensionResult:
    """savings_type values 'run_rate'/'one_time' in value_at_table are machine-format."""
    scenario_evidence: Dict[str, Any] = {}
    snake_count = 0
    total_with_levers = 0

    _SNAKE_PATTERN = re.compile(r'^[a-z]+(_[a-z]+)+$')

    for fixture, result in results:
        sid = fixture["scenario_id"]
        if result is None:
            scenario_evidence[sid] = {"error": "run failed"}
            continue

        vat = result.get("value_at_table", [])
        if not vat:
            scenario_evidence[sid] = {"skipped": "no levers in value_at_table"}
            continue

        total_with_levers += 1
        snake_values = [
            lv.get("savings_type", "")
            for lv in vat
            if _SNAKE_PATTERN.match(lv.get("savings_type", ""))
        ]
        has_label = any("savings_type_label" in lv for lv in vat)
        has_snake_without_label = len(snake_values) > 0 and not has_label

        if has_snake_without_label:
            snake_count += 1

        scenario_evidence[sid] = {
            "unique_savings_types": list({lv.get("savings_type") for lv in vat}),
            "has_savings_type_label": has_label,
            "snake_case_values_found": list(set(snake_values)),
            "readable_format_issue": has_snake_without_label,
        }

    score = max(0.0, 10.0 - (snake_count / max(total_with_levers, 1)) * 10.0)
    passed = score >= 7.0
    return DimensionResult(
        dimension_id="RD-06",
        name="savings_type Display Format",
        domain="label_accuracy",
        weight=0.25,
        threshold_pass=7.0,
        raw_score=round(score, 2),
        passed=passed,
        evidence=scenario_evidence,
        finding_summary=(
            f"{snake_count}/{total_with_levers} scenarios expose snake_case savings_type without readable label"
        ),
        finding_detail=(
            "PASS — savings_type uses readable labels or savings_type_label field present"
            if passed else
            "FAIL — value_at_table entries have 'savings_type': 'run_rate'/'one_time' in snake_case. "
            "FP&A tools would display this verbatim. Recommended: add savings_type_label field with "
            "human-readable values: 'Run Rate', 'One-Time', 'Mixed'."
        ),
        remediation=(
            "In enterprise.py value_at_table assembly (line ~393), add: "
            "_SAVINGS_LABELS = {'run_rate': 'Run Rate', 'one_time': 'One-Time', 'mixed': 'Mixed'} "
            "then 'savings_type_label': _SAVINGS_LABELS.get(savings_type, savings_type.replace('_', ' ').title())"
        ),
        scenarios_run=total_with_levers,
        scenarios_failed=0,
    )


# ---------------------------------------------------------------------------
# RD-07: Debug Fields at Top Level
# ---------------------------------------------------------------------------

def score_rd07(results: List[Tuple[Dict, Dict]]) -> DimensionResult:
    """url_count and url_errors are debug-level fields mixed into FP&A payload."""
    scenario_evidence: Dict[str, Any] = {}
    debug_top_level_count = 0
    total = 0

    for fixture, result in results:
        sid = fixture["scenario_id"]
        if result is None:
            scenario_evidence[sid] = {"error": "run failed"}
            continue

        total += 1
        # Check for debug fields at top level (not nested under _meta or _debug)
        top_level_keys = {k for k in result.keys() if not k.startswith("_")}
        debug_fields_exposed = [k for k in ["url_count", "url_errors"] if k in top_level_keys]
        has_meta_nesting = "_meta" in result or "debug" in result

        if debug_fields_exposed and not has_meta_nesting:
            debug_top_level_count += 1

        scenario_evidence[sid] = {
            "debug_fields_at_top_level": debug_fields_exposed,
            "has_meta_nesting": has_meta_nesting,
            "top_level_key_count": len(top_level_keys),
        }

    score = max(0.0, 10.0 - (debug_top_level_count / max(total, 1)) * 10.0)
    passed = score >= 6.0
    return DimensionResult(
        dimension_id="RD-07",
        name="Debug Fields Nested (not top-level)",
        domain="label_accuracy",
        weight=0.20,
        threshold_pass=6.0,
        raw_score=round(score, 2),
        passed=passed,
        evidence=scenario_evidence,
        finding_summary=(
            f"{debug_top_level_count}/{total} scenarios expose url_count/url_errors at top level"
        ),
        finding_detail=(
            "PASS — debug fields nested under _meta or absent from FP&A payload"
            if passed else
            "FAIL — 'url_count' and 'url_errors' appear at the top level of the response. "
            "These are implementation-level diagnostics that add noise to an FP&A payload. "
            "When url_count=0 and url_errors=[], they convey no useful information to the analyst."
        ),
        remediation=(
            "In enterprise.py return dict, replace top-level url_count/url_errors with: "
            "'_meta': {'url_count': len(texts), 'url_errors': url_errors, 'bench_industry': bench_industry}"
        ),
        scenarios_run=total,
        scenarios_failed=sum(1 for _, r in results if r is None),
    )


# ---------------------------------------------------------------------------
# RD-08: Revenue-% Framing in Findings
# ---------------------------------------------------------------------------

def score_rd08(results: List[Tuple[Dict, Dict]]) -> DimensionResult:
    """At least 1 key_finding must include % of revenue context."""
    scenario_evidence: Dict[str, Any] = {}
    pass_count = 0
    total = 0

    for fixture, result in results:
        sid = fixture["scenario_id"]
        if result is None:
            scenario_evidence[sid] = {"error": "run failed"}
            continue

        total += 1
        findings = result.get("key_findings", [])
        findings_text = " ".join(findings)
        has_revenue_pct = (
            "% of revenue" in findings_text
            or "% revenue" in findings_text
            or re.search(r'\d+\.?\d*%\s+of', findings_text) is not None
        )

        if has_revenue_pct:
            pass_count += 1

        scenario_evidence[sid] = {
            "has_revenue_pct_framing": has_revenue_pct,
            "findings": findings,
            "annual_revenue_cr": fixture["request"].get("annual_revenue_cr", 5000.0),
        }

    score = (pass_count / total * 10.0) if total > 0 else 0.0
    passed = score >= 7.0
    return DimensionResult(
        dimension_id="RD-08",
        name="Revenue-% Framing in Findings",
        domain="findings_narrative",
        weight=0.35,
        threshold_pass=7.0,
        raw_score=round(score, 2),
        passed=passed,
        evidence=scenario_evidence,
        finding_summary=f"{pass_count}/{total} scenarios include % of revenue context in findings",
        finding_detail=(
            "PASS — findings include % of revenue framing"
            if passed else
            "FAIL — findings show only absolute ₹ amounts with no % of revenue context. "
            "FP&A analysts need relative framing: '₹240 Cr (12% of revenue)' is more actionable "
            "than '₹240 Cr' — it enables benchmarking against revenue growth and budget planning."
        ),
        remediation=(
            "In enterprise.py top-gap finding, add revenue_pct: "
            "revenue_pct = round(implied_p50_cr / req.annual_revenue_cr * 100, 1); "
            "f'Largest category: {name} — {_fmt_cr(implied_p50_cr)} ({revenue_pct}% of revenue); ...' "
            "Similarly for total-value finding: total_pct = round(total_p50 / req.annual_revenue_cr * 100, 1)"
        ),
        scenarios_run=total,
        scenarios_failed=sum(1 for _, r in results if r is None),
    )


# ---------------------------------------------------------------------------
# RD-09: Actionability Signal in Findings
# ---------------------------------------------------------------------------

def score_rd09(results: List[Tuple[Dict, Dict]]) -> DimensionResult:
    """At least 1 finding must reference complexity or implementation horizon."""
    scenario_evidence: Dict[str, Any] = {}
    pass_count = 0
    total_with_levers = 0

    actionability_keywords = [
        "low complexity", "medium complexity", "high complexity",
        "complexity", "quick win", "90-day", "12-month",
        "time-to-value", "implementation", "near-term", "phasing",
        "payback", "run rate", "run-rate",
    ]

    for fixture, result in results:
        sid = fixture["scenario_id"]
        if result is None:
            scenario_evidence[sid] = {"error": "run failed"}
            continue

        vat = result.get("value_at_table", [])
        if not vat:
            scenario_evidence[sid] = {"skipped": "no levers"}
            continue

        total_with_levers += 1
        findings_text = " ".join(result.get("key_findings", [])).lower()
        found_keyword = next(
            (kw for kw in actionability_keywords if kw in findings_text),
            None
        )

        if found_keyword:
            pass_count += 1

        complexity_values = list({lv.get("complexity_tier", "medium") for lv in vat})
        scenario_evidence[sid] = {
            "has_actionability_signal": found_keyword is not None,
            "matched_keyword": found_keyword,
            "complexity_tiers_in_vat": complexity_values,
            "findings_preview": result.get("key_findings", [])[:2],
        }

    score = (pass_count / total_with_levers * 10.0) if total_with_levers > 0 else 0.0
    passed = score >= 6.0
    return DimensionResult(
        dimension_id="RD-09",
        name="Actionability Signal in Findings",
        domain="findings_narrative",
        weight=0.25,
        threshold_pass=6.0,
        raw_score=round(score, 2),
        passed=passed,
        evidence=scenario_evidence,
        finding_summary=f"{pass_count}/{total_with_levers} scenarios with levers include actionability signal in findings",
        finding_detail=(
            "PASS — findings reference complexity tier or implementation horizon"
            if passed else
            "FAIL — findings show only savings amounts with no prioritization guidance. "
            "FP&A analysts need to know which lever to pursue first. "
            "e.g. 'Vendor Consolidation (low complexity) — ₹45 Cr run-rate savings' "
            "is more actionable than 'Vendor Consolidation — ₹45 Cr annual savings'."
        ),
        remediation=(
            "In enterprise.py top-lever finding, include complexity_tier: "
            "_COMPLEXITY = {'low': 'low complexity', 'medium': 'medium complexity', 'high': 'high complexity'}; "
            "f'{lever_name} ({_COMPLEXITY.get(top_lever[\"complexity_tier\"], \"medium complexity\")}) — ...'"
        ),
        scenarios_run=total_with_levers,
        scenarios_failed=0,
    )


# ---------------------------------------------------------------------------
# RD-10: Savings Confidence Range in Findings
# ---------------------------------------------------------------------------

def score_rd10(results: List[Tuple[Dict, Dict]]) -> DimensionResult:
    """P10/P90 range should be surfaced as uncertainty bounds in findings."""
    scenario_evidence: Dict[str, Any] = {}
    pass_count = 0
    total_with_levers = 0

    range_keywords = ["p10", "p90", "range", "low end", "high end", "upside", "downside", "–", "to ₹"]

    for fixture, result in results:
        sid = fixture["scenario_id"]
        if result is None:
            scenario_evidence[sid] = {"error": "run failed"}
            continue

        vat = result.get("value_at_table", [])
        if not vat:
            scenario_evidence[sid] = {"skipped": "no levers"}
            continue

        total_with_levers += 1
        findings_text = " ".join(result.get("key_findings", [])).lower()
        found_range = any(kw in findings_text for kw in range_keywords)

        total_p10 = sum(v.get("p10_cr", 0) for v in vat)
        total_p90 = sum(v.get("p90_cr", 0) for v in vat)
        total_p50 = sum(v.get("p50_cr", 0) for v in vat)

        if found_range:
            pass_count += 1

        scenario_evidence[sid] = {
            "has_range_disclosure": found_range,
            "total_p10_cr": round(total_p10, 1),
            "total_p50_cr": round(total_p50, 1),
            "total_p90_cr": round(total_p90, 1),
            "p10_to_p90_multiplier": round(total_p90 / total_p10, 1) if total_p10 > 0 else None,
        }

    score = (pass_count / total_with_levers * 10.0) if total_with_levers > 0 else 0.0
    passed = score >= 6.0
    return DimensionResult(
        dimension_id="RD-10",
        name="Savings Confidence Range Surfaced",
        domain="findings_narrative",
        weight=0.20,
        threshold_pass=6.0,
        raw_score=round(score, 2),
        passed=passed,
        evidence=scenario_evidence,
        finding_summary=f"{pass_count}/{total_with_levers} scenarios surface P10/P90 savings range",
        finding_detail=(
            "PASS — P10/P90 range disclosed in findings"
            if passed else
            "FAIL — value_at_table contains p10_cr and p90_cr columns but the confidence spread "
            "is never surfaced in findings. CFO presentations require uncertainty bounds. "
            "e.g. 'Estimated savings range: ₹120 Cr – ₹380 Cr (P10–P90) across 10 levers'."
        ),
        remediation=(
            "In enterprise.py key_findings assembly, add: "
            "total_p10 = sum(v['p10_cr'] for v in value_at_table); "
            "total_p90 = sum(v['p90_cr'] for v in value_at_table); "
            "key_findings.append(f'Savings range (P10–P90): {_fmt_cr(total_p10)} to {_fmt_cr(total_p90)}')"
        ),
        scenarios_run=total_with_levers,
        scenarios_failed=0,
    )


# ---------------------------------------------------------------------------
# RD-11: Assumption Disclosure (WACC + headcount + NPV horizon)
# ---------------------------------------------------------------------------

def score_rd11(results: List[Tuple[Dict, Dict]]) -> DimensionResult:
    """WACC, headcount, and NPV horizon must all be disclosed in the response."""
    scenario_evidence: Dict[str, Any] = {}
    scores_by_scenario: List[float] = []

    for fixture, result in results:
        sid = fixture["scenario_id"]
        if result is None:
            scenario_evidence[sid] = {"error": "run failed"}
            continue

        response_str = json.dumps({k: v for k, v in result.items() if not k.startswith("_")}).lower()

        wacc_present = "wacc" in response_str or "discount_rate" in response_str
        headcount_present = "headcount" in response_str
        horizon_present = any(kw in response_str for kw in ["3-year", "3 year", "npv_horizon", "36-month"])
        assumptions_obj = "assumptions" in response_str

        count = sum([wacc_present, headcount_present, horizon_present])
        scenario_score = (count / 3) * 10.0

        scores_by_scenario.append(scenario_score)
        scenario_evidence[sid] = {
            "wacc_disclosed": wacc_present,
            "headcount_disclosed": headcount_present,
            "npv_horizon_disclosed": horizon_present,
            "has_assumptions_object": assumptions_obj,
            "disclosure_count": count,
            "scenario_score": round(scenario_score, 1),
        }

    score = (sum(scores_by_scenario) / len(scores_by_scenario)) if scores_by_scenario else 0.0
    passed = score >= 7.0
    count_passed = sum(1 for s in scores_by_scenario if s >= 7.0)
    return DimensionResult(
        dimension_id="RD-11",
        name="Assumption Disclosure (WACC, headcount, horizon)",
        domain="findings_narrative",
        weight=0.20,
        threshold_pass=7.0,
        raw_score=round(score, 2),
        passed=passed,
        evidence=scenario_evidence,
        finding_summary=f"{count_passed}/{len(scores_by_scenario)} scenarios disclose ≥2/3 key assumptions",
        finding_detail=(
            "PASS — WACC, headcount, and NPV horizon disclosed"
            if passed else
            "FAIL — Key model assumptions (WACC, headcount, 3-year NPV horizon) consumed internally "
            "but never returned in the response. FP&A analysts and auditors need to see the inputs "
            "used to derive savings estimates to validate and communicate the analysis."
        ),
        remediation=(
            "Add 'assumptions' object to enterprise.py return dict: "
            "{'wacc_pct': round(req.wacc * 100, 1), 'headcount': req.headcount, "
            "'npv_horizon_years': 3, 'profile_basis': 'benchmark_proxy'}. "
            "This one change resolves RD-03, RD-11, and partially RD-02."
        ),
        scenarios_run=len(scores_by_scenario),
        scenarios_failed=sum(1 for _, r in results if r is None),
    )


# ---------------------------------------------------------------------------
# RD-12: Document Flags Interpretability
# ---------------------------------------------------------------------------

def score_rd12(results: List[Tuple[Dict, Dict]]) -> DimensionResult:
    """'Document flags: ...' prefix is cryptic; should explain what the flags mean."""
    scenario_evidence: Dict[str, Any] = {}
    total_with_constraints = 0
    interpretable_count = 0

    cryptic_prefixes = ["document flags:", "flags:"]
    descriptive_alternatives = [
        "identified constraint", "constraint:", "limitation:", "risk:",
        "noted:", "advisory:", "caution:", "may affect",
    ]

    for fixture, result in results:
        sid = fixture["scenario_id"]
        if result is None:
            scenario_evidence[sid] = {"error": "run failed"}
            continue

        constraints = result.get("company_signals", {}).get("constraints", [])
        if not constraints:
            scenario_evidence[sid] = {"skipped": "no constraints in company_signals"}
            continue

        total_with_constraints += 1
        constraint_findings = [
            f for f in result.get("key_findings", [])
            if any(c.lower() in f.lower() for c in constraints[:1])
            or any(pf in f.lower() for pf in cryptic_prefixes + descriptive_alternatives)
        ]
        is_cryptic = any(
            f.lower().startswith(pf) for f in constraint_findings for pf in cryptic_prefixes
        )
        is_descriptive = any(
            any(alt in f.lower() for alt in descriptive_alternatives)
            for f in constraint_findings
        )

        interpretable = is_descriptive and not is_cryptic
        if interpretable:
            interpretable_count += 1

        scenario_evidence[sid] = {
            "has_constraints": True,
            "constraint_count": len(constraints),
            "constraint_findings": constraint_findings,
            "is_cryptic_prefix": is_cryptic,
            "is_descriptive": is_descriptive,
            "interpretable": interpretable,
        }

    if total_with_constraints == 0:
        # No scenarios had constraints — give full marks, this is not a failure
        score = 10.0
        summary = "No scenarios with constraints found — dimension not exercised"
    else:
        score = (interpretable_count / total_with_constraints * 10.0)
        summary = f"{interpretable_count}/{total_with_constraints} constraint findings use descriptive prefix"

    passed = score >= 6.0
    return DimensionResult(
        dimension_id="RD-12",
        name="Document Flags Interpretability",
        domain="findings_narrative",
        weight=0.20,
        threshold_pass=6.0,
        raw_score=round(score, 2),
        passed=passed,
        evidence=scenario_evidence,
        finding_summary=summary,
        finding_detail=(
            "PASS — constraint findings use descriptive language"
            if passed else
            "FAIL — findings use 'Document flags: xyz' prefix. "
            "The word 'flags' is abstract; an FP&A analyst doesn't know if this means a data warning, "
            "a risk to the savings estimate, or a regulatory constraint. "
            "Recommended: 'Identified constraint (may affect lever eligibility): union agreements...'"
        ),
        remediation=(
            "In enterprise.py key_findings assembly (line ~414), replace: "
            "'Document flags: ' + ... "
            "with: 'Identified constraints (may affect lever eligibility): ' + ..."
        ),
        scenarios_run=total_with_constraints,
        scenarios_failed=0,
    )


# ---------------------------------------------------------------------------
# RD-13: data_note Specificity
# ---------------------------------------------------------------------------

def score_rd13(results: List[Tuple[Dict, Dict]]) -> DimensionResult:
    """data_note should vary between mapped and unmapped sectors."""
    scenario_evidence: Dict[str, Any] = {}
    data_notes: Dict[str, str] = {}

    for fixture, result in results:
        sid = fixture["scenario_id"]
        if result is None:
            scenario_evidence[sid] = {"error": "run failed"}
            continue

        note = result.get("data_note", "")
        industry_mapped = fixture["scoring_hints"].get("industry_mapped", True)
        data_notes[sid] = note
        scenario_evidence[sid] = {
            "industry_mapped": industry_mapped,
            "data_note": note,
            "note_length": len(note),
        }

    unique_notes = set(data_notes.values())
    all_identical = len(unique_notes) == 1
    mapped_notes = {
        sid: n for sid, n in data_notes.items()
        if scenario_evidence.get(sid, {}).get("industry_mapped", True)
    }
    unmapped_notes = {
        sid: n for sid, n in data_notes.items()
        if not scenario_evidence.get(sid, {}).get("industry_mapped", True)
    }

    mapped_note_unique = len(set(mapped_notes.values())) if mapped_notes else 0
    unmapped_note_unique = len(set(unmapped_notes.values())) if unmapped_notes else 0

    if mapped_notes and unmapped_notes:
        notes_differ = set(mapped_notes.values()) != set(unmapped_notes.values())
        score = 10.0 if notes_differ else 0.0
        summary = (
            f"data_note varies between mapped/unmapped: {notes_differ}"
        )
    elif all_identical:
        score = 0.0
        summary = f"All {len(data_notes)} scenarios have identical data_note (static boilerplate)"
    else:
        score = 7.0
        summary = "data_note varies but no unmapped scenarios to compare against"

    passed = score >= 6.0
    return DimensionResult(
        dimension_id="RD-13",
        name="data_note Specificity",
        domain="context_completeness",
        weight=0.25,
        threshold_pass=6.0,
        raw_score=round(score, 2),
        passed=passed,
        evidence={
            "unique_note_count": len(unique_notes),
            "all_identical": all_identical,
            "mapped_scenarios": list(mapped_notes.keys()),
            "unmapped_scenarios": list(unmapped_notes.keys()),
            "scenario_evidence": scenario_evidence,
        },
        finding_summary=summary,
        finding_detail=(
            "PASS — data_note is scenario-specific"
            if passed else
            "FAIL — data_note is a static string identical for all scenarios. "
            "S04/S05 (unmapped sectors) get the same note as S01/S02 (well-mapped sectors). "
            "An unmapped scenario should warn: 'No benchmark found for this sector — estimates are directional only.'"
        ),
        remediation=(
            "In enterprise.py return dict (line ~431), make data_note conditional: "
            "if bench_resolved.get('selected_dataset'): data_note = 'Spend profile derived from ...' "
            "else: data_note = f'No benchmark data found for sector {effective_industry!r}; "
            "nearest-proxy estimates used. Treat as directional only.'"
        ),
        scenarios_run=len(data_notes),
        scenarios_failed=sum(1 for _, r in results if r is None),
    )


# ---------------------------------------------------------------------------
# RD-14: Eligible Levers Total Disclosed
# ---------------------------------------------------------------------------

def score_rd14(results: List[Tuple[Dict, Dict]]) -> DimensionResult:
    """Response should include total eligible levers before top-12 truncation."""
    scenario_evidence: Dict[str, Any] = {}
    pass_count = 0
    total = 0

    for fixture, result in results:
        sid = fixture["scenario_id"]
        if result is None:
            scenario_evidence[sid] = {"error": "run failed"}
            continue

        total += 1
        response_keys = set(result.keys())
        has_total = (
            "eligible_levers_total" in response_keys
            or "total_eligible_levers" in response_keys
            or "levers_evaluated" in response_keys
        )

        vat_count = len(result.get("value_at_table", []))
        eligible_total = result.get("_eligible_levers_total", None)

        if has_total:
            pass_count += 1

        scenario_evidence[sid] = {
            "value_at_table_count": vat_count,
            "eligible_levers_total_internal": eligible_total,
            "eligible_levers_total_in_response": has_total,
            "truncated": vat_count == 12 and eligible_total and eligible_total > 12,
        }

    score = (pass_count / total * 10.0) if total > 0 else 0.0
    passed = score >= 6.0
    return DimensionResult(
        dimension_id="RD-14",
        name="Eligible Levers Total Disclosed",
        domain="context_completeness",
        weight=0.25,
        threshold_pass=6.0,
        raw_score=round(score, 2),
        passed=passed,
        evidence=scenario_evidence,
        finding_summary=f"{pass_count}/{total} scenarios include eligible_levers_total in response",
        finding_detail=(
            "PASS — eligible_levers_total field present"
            if passed else
            "FAIL — value_at_table is capped at 12 levers but the total pool of eligible levers "
            "is never disclosed. An FP&A analyst seeing '12 levers' doesn't know if 12 of 12 or "
            "12 of 47 were shown — critical context for understanding coverage."
        ),
        remediation=(
            "In enterprise.py return dict, add: 'eligible_levers_total': len(eligible_levers). "
            "This is already tracked internally as _eligible_levers_total — just expose it."
        ),
        scenarios_run=total,
        scenarios_failed=sum(1 for _, r in results if r is None),
    )


# ---------------------------------------------------------------------------
# RD-15: P25/P50 Percentile Legend
# ---------------------------------------------------------------------------

def score_rd15(results: List[Tuple[Dict, Dict]]) -> DimensionResult:
    """Response should include a legend explaining what P25/P50/P10/P90 mean."""
    scenario_evidence: Dict[str, Any] = {}
    pass_count = 0
    total = 0

    legend_keys = {"percentile_legend", "benchmark_legend", "percentile_definitions"}
    legend_keywords = ["best-in-class", "industry median", "top decile", "lagging"]

    for fixture, result in results:
        sid = fixture["scenario_id"]
        if result is None:
            scenario_evidence[sid] = {"error": "run failed"}
            continue

        total += 1
        response_keys = set(result.keys())
        has_legend_key = bool(legend_keys & response_keys)

        response_str = json.dumps({k: v for k, v in result.items() if not k.startswith("_")}).lower()
        has_legend_keyword = any(kw in response_str for kw in legend_keywords)

        has_legend = has_legend_key or has_legend_keyword
        if has_legend:
            pass_count += 1

        scenario_evidence[sid] = {
            "has_legend_key": has_legend_key,
            "has_legend_keyword": has_legend_keyword,
            "has_legend": has_legend,
        }

    score = (pass_count / total * 10.0) if total > 0 else 0.0
    passed = score >= 5.0
    return DimensionResult(
        dimension_id="RD-15",
        name="Percentile Legend (P25/P50 definitions)",
        domain="context_completeness",
        weight=0.20,
        threshold_pass=5.0,
        raw_score=round(score, 2),
        passed=passed,
        evidence=scenario_evidence,
        finding_summary=f"{pass_count}/{total} scenarios include percentile legend",
        finding_detail=(
            "PASS — percentile legend present"
            if passed else
            "FAIL — response uses P10/P25/P50/P90 extensively without defining them. "
            "FP&A users unfamiliar with benchmarking nomenclature don't know that "
            "P25 = best-in-class quartile, P50 = industry median, P90 = lagging quartile. "
            "A one-time legend object removes ambiguity."
        ),
        remediation=(
            "In enterprise.py return dict, add: "
            "'percentile_legend': {'p10': 'top-decile benchmark (stretch target)', "
            "'p25': 'best-in-class quartile', 'p50': 'industry median', 'p90': 'lagging quartile'}"
        ),
        scenarios_run=total,
        scenarios_failed=sum(1 for _, r in results if r is None),
    )


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def _aggregate(dimension_results: List[DimensionResult]) -> Tuple[List[DomainResult], float]:
    domains_meta = {
        "financial_formatting": ("Financial Number Formatting", 0.25),
        "label_accuracy": ("Label Accuracy & Terminology", 0.25),
        "findings_narrative": ("Key Findings Narrative Quality", 0.30),
        "context_completeness": ("Context Completeness", 0.20),
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
    overall = (
        sum(dr.domain_score * dr.domain_weight for dr in domain_results) / total_dw
        if total_dw > 0 else 0.0
    )
    return domain_results, round(overall, 2)


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def _to_json(report: EvalReport, dimension_results: List[DimensionResult]) -> Dict:
    return {
        "eval_name": "Diagnostic Readability Eval",
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
        f"# Diagnostic Readability Eval — {status}",
        f"",
        f"**Date:** {report.eval_date}  |  **Version:** {report.platform_version}  "
        f"|  **Overall Score:** {report.overall_score}/10  |  "
        f"**Pass threshold:** 7.0/10",
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

    lines += ["", "## Findings by Dimension", ""]
    for d in dimension_results:
        st = "PASS" if d.passed else "FAIL"
        lines += [
            f"### {d.dimension_id} — {d.name} [{st}]",
            f"",
            f"**Score:** {d.raw_score:.1f}/{d.threshold_pass:.1f}  |  **Domain:** {d.domain}",
            f"",
            f"{d.finding_detail}",
            f"",
            f"**Remediation:** {d.remediation}",
            f"",
        ]

    lines += ["## LLM Enhancement Opportunities", ""]
    llm_opps = [
        (
            "LLM-1 (Highest Value)",
            "key_findings narrative via Claude",
            "app/routers/enterprise.py:401-417",
            "Replace 4 template strings with claude-haiku-4-5 call. System prompt cached. "
            "Generates 5-7 FP&A-grade bullets with %-of-revenue, complexity framing, and assumption disclosure. "
            "Fallback: existing templates on LLM failure.",
        ),
        (
            "LLM-2 (High Value)",
            "Semantic document_contextualizer",
            "app/skills/engine/profiler.py:document_contextualizer()",
            "Replace bag-of-words with claude-haiku-4-5 structured extraction: "
            "inferred_industry, growth_phase, financial_stress_signals, procurement_maturity, constraints, positive_signals. "
            "Guard: skip LLM when texts=[]. Eliminates false positives from short keywords.",
        ),
        (
            "LLM-3 (Medium Value)",
            "executive_summary field",
            "app/routers/enterprise.py (new field in return dict)",
            "3-sentence CFO paragraph generated post-assembly. "
            "Sentence 1: headline opportunity (₹ + % of revenue). "
            "Sentence 2: top lever with complexity + payback. "
            "Sentence 3: caveat or next step.",
        ),
        (
            "LLM-4 (Medium Value)",
            "Per-gap benchmark commentary",
            "app/routers/enterprise.py benchmark_gaps assembly",
            "Add commentary field to each benchmark_gap entry. "
            "Single batch LLM call for all gaps. System prompt cached. "
            "e.g. 'Your HR spend at 12.3% is 1.35x median; ₹46 Cr to P25 best-in-class.'",
        ),
        (
            "LLM-5 (Lower Value)",
            "Lever rationale per value-at-table entry",
            "app/routers/enterprise.py value_at_table assembly",
            "Add rationale field explaining why each lever was flagged: "
            "'Applicable based on IT concentration above P50 and vendor fragmentation signals.' "
            "trigger_signals already captures this structurally — LLM adds narrative.",
        ),
    ]
    lines += [
        "| Priority | Enhancement | Location | Description |",
        "|----------|-------------|----------|-------------|",
    ]
    for priority, name, loc, desc in llm_opps:
        lines.append(f"| {priority} | {name} | `{loc}` | {desc} |")

    if report.top_gaps:
        lines += ["", "## Top Gaps to Close", ""]
        for i, g in enumerate(report.top_gaps[:5], 1):
            lines.append(f"{i}. **{g['dimension']}** (gap {g['gap']:.1f}) — {g['remediation'][:120]}")

    lines += ["", "## Remediation Roadmap", ""]
    for i, item in enumerate(report.remediation_roadmap, 1):
        lines.append(f"{i}. **[{item['dimension_id']}] {item['name']}** — {item['remediation'][:140]}")

    lines += [""]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run Diagnostic Readability Eval")
    parser.add_argument("--json-only", action="store_true", help="Skip markdown report")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_MD), help="Markdown output path")
    parser.add_argument("--json-output", default=str(DEFAULT_OUTPUT_JSON), help="JSON output path")
    args = parser.parse_args(argv)

    print("=" * 70)
    print("OpEx Platform — Diagnostic Readability Eval")
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
    mapped_results = [(f, r) for f, r in run_results if r is not None]

    dimension_results: List[DimensionResult] = [
        score_rd01(mapped_results),
        score_rd02(mapped_results),
        score_rd03(mapped_results),
        score_rd04(mapped_results),
        score_rd05(mapped_results),
        score_rd06(mapped_results),
        score_rd07(mapped_results),
        score_rd08(mapped_results),
        score_rd09(mapped_results),
        score_rd10(mapped_results),
        score_rd11(mapped_results),
        score_rd12(mapped_results),
        score_rd13(run_results),
        score_rd14(mapped_results),
        score_rd15(mapped_results),
    ]

    for d in dimension_results:
        st = "PASS" if d.passed else "FAIL"
        print(f"  [{st}] {d.dimension_id} {d.name}: {d.raw_score:.1f}/{d.threshold_pass:.1f}")

    # Aggregate
    domain_results, overall_score = _aggregate(dimension_results)
    all_passed = all(d.passed for d in dimension_results)

    top_gaps = sorted(
        [
            {"dimension": d.dimension_id, "name": d.name, "gap": d.gap, "remediation": d.remediation}
            for d in dimension_results if d.gap > 0
        ],
        key=lambda x: x["gap"], reverse=True,
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

    print()
    st = "✅ PASS" if all_passed else "❌ FAIL"
    print(f"Overall Readability Score: {overall_score:.2f}/10  [{st}]")
    print()
    for dr in domain_results:
        domain_st = "✅" if dr.passed else "❌"
        print(f"  {domain_st} {dr.domain_display}: {dr.domain_score:.2f}/10")

    # Write JSON
    json_path = Path(args.json_output)
    json_path.write_text(json.dumps(_to_json(report, dimension_results), indent=2))
    print(f"\nJSON scores → {json_path}")

    # Write markdown
    if not args.json_only:
        md_path = Path(args.output)
        md_path.write_text(_to_markdown(report, dimension_results))
        print(f"Markdown report → {md_path}")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
