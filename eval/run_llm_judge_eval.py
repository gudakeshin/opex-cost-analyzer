#!/usr/bin/env python3
"""
eval/run_llm_judge_eval.py — LLM-Judged Analytical Quality Evaluator

Uses Claude as an independent judge to assess the analytical quality of platform
outputs against 5 golden scenarios. Unlike the structural evals, this eval measures
whether the CONTENT is plausible and client-ready, not just schema-compliant.

IMPORTANT — score interpretation:
  - run_analysis_quality_eval.py  (AQ-01..08) = STRUCTURAL score: schema compliance
  - THIS eval (LJ-01..05)          = ANALYTICAL score: content quality, as judged by an LLM

Neither score validates real-world savings accuracy. The LJ scores are subjective
by construction — an LLM judge can hallucinate or be inconsistent. They are a
directional signal, not ground truth.

Requires: ANTHROPIC_API_KEY in environment.
If the key is absent, the eval exits 2 with a clear message.

Usage:
    ANTHROPIC_API_KEY=sk-... PYTHONPATH=. python eval/run_llm_judge_eval.py
    PYTHONPATH=. python eval/run_llm_judge_eval.py --output eval/llm_judge_report.md

Exit codes:
    0 — all 5 dimensions average >= PASS_THRESHOLD (7.0)
    1 — one or more dimensions below threshold
    2 — critical error (no API key, pipeline load failure)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).parent.parent
SCENARIOS_DIR = ROOT / "tests" / "eval" / "golden" / "analysis_quality"
DEFAULT_OUTPUT_MD = ROOT / "eval" / "llm_judge_report.md"
DEFAULT_OUTPUT_JSON = ROOT / "eval" / "llm_judge_scores.json"
PASS_THRESHOLD = 7.0
JUDGE_MODEL = "claude-sonnet-4-6"

# Prompt version — bump when rubric changes materially.
# Persisted in JSON output so every score can be traced to the rubric that produced it.
JUDGE_PROMPT_VERSION = "1.0"

SCENARIO_FILES = [
    "s01_it_benchmark.json",
    "s02_bva_surfacing.json",
    "s03_category_focus.json",
    "s04_msme_contract.json",
    "s05_multi_category.json",
]

# ---------------------------------------------------------------------------
# Judge rubric — 5 analytical quality dimensions
# ---------------------------------------------------------------------------

_RUBRIC = """
You are an independent analytical quality reviewer for an FP&A OpEx intelligence platform.
Your role is to judge whether the platform's analysis outputs are analytically sound,
plausible, and client-ready. You are NOT checking schema or formatting — only content quality.

Score each of the 5 dimensions from 0 to 10, where:
  10 = exemplary — a Deloitte partner would send this to a CFO without editing
   8 = strong — minor gaps but fundamentally sound
   6 = adequate — passes a credibility check but has noticeable weaknesses
   4 = weak — significant plausibility or transparency issues
   2 = poor — would embarrass the firm if shown to a client
   0 = unusable — wrong, internally inconsistent, or completely missing

Dimensions:
  LJ-01 Recommendation Plausibility
    Are the recommended savings levers realistic for this company type, industry, and
    spend mix? Would a CFO in this sector accept these as actionable starting points?
    Penalise: generic advice that ignores the actual spend data, unrealistic savings
    percentages, levers that contradict sector norms.

  LJ-02 Assumption Transparency
    Are key assumptions (addressability %, capture rate, implementation timeline,
    benchmark source) visible in the output — even if only as metadata fields?
    Penalise: numbers presented without any indication of the underlying assumption,
    savings figures with no benchmark or methodology reference.

  LJ-03 Analytical Depth
    Does the analysis surface non-obvious insights (concentration risk, DPO gap,
    contract expiry cliff, maverick spend pattern) or does it just restate the
    input spend data in different words?
    Penalise: observations that any Excel pivot table would produce without context.

  LJ-04 Client Readiness
    Could a senior consultant hand this output to a CFO tomorrow? Consider: are
    initiative titles specific (not "Reduce IT spend"), are savings ranges plausible,
    is the prioritisation logic visible?
    Penalise: boilerplate initiative names, round-number estimates without justification,
    missing owner / timeline / confidence.

  LJ-05 Benchmark Integrity
    Are benchmark comparisons appropriately caveated (source disclosed, illustrative
    nature noted) or are they presented as authoritative external data?
    Penalise: peer percentile claims with no source, internally calibrated thresholds
    presented as industry-standard facts.

Return your response as a JSON object with this exact structure:
{
  "LJ-01": {"score": <0-10>, "justification": "<2-3 sentences>"},
  "LJ-02": {"score": <0-10>, "justification": "<2-3 sentences>"},
  "LJ-03": {"score": <0-10>, "justification": "<2-3 sentences>"},
  "LJ-04": {"score": <0-10>, "justification": "<2-3 sentences>"},
  "LJ-05": {"score": <0-10>, "justification": "<2-3 sentences>"}
}
Return only the JSON object, no markdown wrapping.
"""

_DIMENSION_META = {
    "LJ-01": ("Recommendation Plausibility", 0.25),
    "LJ-02": ("Assumption Transparency", 0.20),
    "LJ-03": ("Analytical Depth", 0.20),
    "LJ-04": ("Client Readiness", 0.20),
    "LJ-05": ("Benchmark Integrity", 0.15),
}


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class DimScore:
    dimension_id: str
    name: str
    weight: float
    scores: List[float] = field(default_factory=list)
    justifications: List[str] = field(default_factory=list)

    @property
    def average(self) -> float:
        return sum(self.scores) / len(self.scores) if self.scores else 0.0

    @property
    def passed(self) -> bool:
        return self.average >= PASS_THRESHOLD

    @property
    def weighted(self) -> float:
        return self.average * self.weight


@dataclass
class EvalReport:
    eval_date: str
    judge_model: str
    judge_prompt_version: str
    overall_score: float
    dimension_scores: Dict[str, DimScore]
    scenario_ids: List[str]
    passed: bool
    skipped_scenarios: int


# ---------------------------------------------------------------------------
# Pipeline runner (same as run_analysis_quality_eval.py)
# ---------------------------------------------------------------------------

def _run_pipeline(scenario: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    try:
        from app.models import NormalizedSpendLine
        from app.services.analysis import run_core_pipeline

        ctx = scenario.get("scenario_context", {})
        raw_lines = scenario.get("input_lines", [])
        lines: List[NormalizedSpendLine] = []
        for raw in raw_lines:
            if isinstance(raw.get("contract_expiry_date"), str):
                raw = dict(raw)
                try:
                    from datetime import date as _date
                    raw["contract_expiry_date"] = _date.fromisoformat(raw["contract_expiry_date"])
                except Exception:
                    raw.pop("contract_expiry_date", None)
            lines.append(NormalizedSpendLine(**raw))

        state = run_core_pipeline(
            session_id=str(uuid.uuid4()),
            lines=lines,
            docs_text=[],
            industry=ctx.get("industry", "technology"),
            annual_revenue=float(ctx.get("annual_revenue", 0.0)),
            company_name=ctx.get("company_name", "Eval Co"),
            headcount=float(ctx.get("headcount", 0) or 0),
            reporting_currency=ctx.get("reporting_currency", "USD"),
        )
        if hasattr(state, "skill_outputs"):
            return state.skill_outputs, None
        if isinstance(state, dict) and "skill_outputs" in state:
            return state["skill_outputs"], None
        return state, None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


# ---------------------------------------------------------------------------
# Output summarizer — compact representation for the judge
# ---------------------------------------------------------------------------

def _summarize_outputs(scenario: Dict[str, Any], skill_outputs: Dict[str, Any]) -> str:
    ctx = scenario.get("scenario_context", {})
    lines = [
        f"COMPANY: {ctx.get('company_name', 'Unknown')}",
        f"INDUSTRY: {ctx.get('industry', 'unknown')}",
        f"ANNUAL REVENUE: {ctx.get('annual_revenue', 0):,.0f} {ctx.get('reporting_currency', 'USD')}",
        f"SCENARIO: {scenario.get('description', 'N/A')}",
        "",
    ]

    # Spend profile summary
    profiler = skill_outputs.get("spend-profiler", {})
    total_spend = profiler.get("total_spend", 0)
    categories = profiler.get("category_profile", [])
    lines += [
        f"TOTAL OPEX SPEND: {total_spend:,.0f}",
        f"CATEGORY COUNT: {len(categories)}",
    ]
    if categories:
        top3 = sorted(categories, key=lambda c: c.get("spend", 0), reverse=True)[:3]
        for c in top3:
            pct = c.get("spend", 0) / total_spend * 100 if total_spend else 0
            lines.append(f"  TOP CATEGORY: {c.get('category_id','?')} — {pct:.1f}% of spend")
    lines.append("")

    # Value bridge / savings initiatives
    bridge = skill_outputs.get("value-bridge-calculator", {})
    matrix = bridge.get("value_matrix", [])
    bands = bridge.get("confidence_bands", {})
    lines += [
        f"SAVINGS MATRIX ROWS: {len(matrix)}",
        f"CONFIDENCE BANDS: low={bands.get('low',0):,.0f}  mid={bands.get('mid',0):,.0f}  high={bands.get('high',0):,.0f}",
    ]
    for row in matrix[:5]:
        lines.append(
            f"  LEVER: {row.get('lever','?')} | "
            f"deduped_mid={row.get('deduped_mid_savings',0):,.0f} | "
            f"npv={row.get('net_npv',0):,.0f} | "
            f"payback={row.get('payback_months','?')}mo | "
            f"confidence={row.get('confidence_band','?')}"
        )
    lines.append("")

    # Benchmark
    peer = skill_outputs.get("peer-benchmarker", {})
    peer_rows = peer.get("peer_comparisons", [])
    peer_src = peer.get("benchmark_dataset", {}).get("source", "unknown")
    lines += [
        f"BENCHMARK SOURCE: {peer_src}",
        f"PEER COMPARISON ROWS: {len(peer_rows)}",
    ]
    for pr in peer_rows[:3]:
        lines.append(
            f"  CATEGORY: {pr.get('category_id','?')} | "
            f"company_pct={pr.get('company_pct_revenue',0):.2f}% | "
            f"p50={pr.get('p50',0):.2f}% | position={pr.get('benchmark_position','?')}"
        )
    lines.append("")

    # Initiatives (top 3)
    modeler = skill_outputs.get("savings-modeler", {})
    initiatives = modeler.get("initiatives", [])
    lines += [f"INITIATIVE COUNT: {len(initiatives)}"]
    for ini in initiatives[:3]:
        lines.append(
            f"  INITIATIVE: {ini.get('title','?')} | "
            f"savings_3yr={ini.get('savings_3yr',0):,.0f} | "
            f"lever={ini.get('lever','?')} | "
            f"confidence={ini.get('confidence','?')} | "
            f"payback={ini.get('payback_months','?')}mo"
        )
    lines.append("")

    # Root cause highlights
    root = skill_outputs.get("root-cause-analyzer", {})
    diagnoses = root.get("diagnoses", [])
    if diagnoses:
        lines.append(f"ROOT CAUSE DIAGNOSES: {len(diagnoses)}")
        for d in diagnoses[:2]:
            lines.append(f"  {d.get('category_id','?')}: {d.get('primary_driver','?')} — {d.get('description','')[:80]}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Judge caller
# ---------------------------------------------------------------------------

def _call_judge(scenario_summary: str, api_key: str) -> Tuple[Optional[Dict], Optional[str]]:
    try:
        import anthropic
    except ImportError:
        return None, "anthropic package not installed"

    user_content = (
        "Please evaluate the following FP&A analysis output from an OpEx intelligence platform.\n\n"
        "=== ANALYSIS OUTPUT SUMMARY ===\n"
        f"{scenario_summary}\n"
        "=== END SUMMARY ===\n\n"
        "Apply the scoring rubric and return your JSON evaluation."
    )

    try:
        client = anthropic.Anthropic(api_key=api_key, timeout=60.0)
        response = client.messages.create(
            model=JUDGE_MODEL,
            max_tokens=1024,
            system=_RUBRIC,
            messages=[{"role": "user", "content": user_content}],
        )
        raw = response.content[0].text.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip()), None
    except json.JSONDecodeError as exc:
        return None, f"JSON parse error: {exc}"
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def _build_report(
    dim_scores: Dict[str, DimScore],
    scenario_ids: List[str],
    skipped: int,
) -> EvalReport:
    total_weight = sum(d.weight for d in dim_scores.values())
    overall = sum(d.weighted for d in dim_scores.values()) / total_weight if total_weight else 0.0
    return EvalReport(
        eval_date=date.today().isoformat(),
        judge_model=JUDGE_MODEL,
        judge_prompt_version=JUDGE_PROMPT_VERSION,
        overall_score=overall,
        dimension_scores=dim_scores,
        scenario_ids=scenario_ids,
        passed=all(d.passed for d in dim_scores.values()),
        skipped_scenarios=skipped,
    )


# ---------------------------------------------------------------------------
# Report writers
# ---------------------------------------------------------------------------

def _write_json(report: EvalReport, path: Path, raw: Dict) -> None:
    payload = {
        "eval_date": report.eval_date,
        "score_type": "llm_judged_analytical_quality",
        "scope": (
            "LLM-judged analytical content quality — plausibility, transparency, depth, "
            "client-readiness, benchmark integrity. Subjective by construction; directional "
            "signal only. Does NOT validate real-world savings accuracy."
        ),
        "judge_model": report.judge_model,
        "judge_prompt_version": report.judge_prompt_version,
        "pass_threshold_per_dimension": PASS_THRESHOLD,
        "overall_score": round(report.overall_score, 3),
        "passed": report.passed,
        "skipped_scenarios": report.skipped_scenarios,
        "scenarios": report.scenario_ids,
        "dimensions": {
            dim_id: {
                "name": d.name,
                "weight": d.weight,
                "average_score": round(d.average, 3),
                "passed": d.passed,
                "per_scenario": {
                    sid: round(sc, 2)
                    for sid, sc in zip(report.scenario_ids, d.scores)
                },
                "justifications": d.justifications,
            }
            for dim_id, d in report.dimension_scores.items()
        },
        "per_scenario_raw": raw,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_markdown(report: EvalReport, path: Path) -> None:
    status = "✅ PASS" if report.passed else "❌ FAIL"
    lines = [
        "# OpEx Platform — LLM-Judged Analytical Quality Eval",
        "",
        f"**Date:** {report.eval_date}  |  **Judge:** `{report.judge_model}`  |"
        f"  **Prompt v{report.judge_prompt_version}**  |"
        f"  **Overall:** {report.overall_score:.2f}/10  |  **Status:** {status}",
        "",
        "> ⚠️ **IMPORTANT — score interpretation:** This eval measures **analytical content quality**",
        "> as assessed by an LLM judge — NOT schema compliance. Scores reflect plausibility,",
        "> transparency, depth, and client-readiness of the analysis content.",
        ">",
        "> These scores are **subjective by construction**. An LLM judge can be inconsistent",
        "> across runs. Treat them as a directional signal, not ground truth.",
        ">",
        "> A score of 9/10 here does NOT mean the savings recommendations are correct —",
        "> it means the LLM judge found them plausible and well-presented.",
        "",
        f"**Scenarios judged:** {len(report.scenario_ids)} | "
        f"**Skipped (pipeline error):** {report.skipped_scenarios}",
        f"**Pass threshold:** {PASS_THRESHOLD}/10 per dimension",
        "",
        "## Dimension Scores",
        "",
        "| ID | Dimension | Weight | Avg Score | Threshold | Status |",
        "|----|-----------|--------|-----------|-----------|--------|",
    ]
    for dim_id, d in report.dimension_scores.items():
        status_d = "✅" if d.passed else "❌"
        lines.append(
            f"| {dim_id} | {d.name} | {d.weight:.0%} | {d.average:.1f} | {PASS_THRESHOLD} | {status_d} |"
        )
    lines.append("")

    # Per-scenario breakdown
    lines += [
        "## Per-Scenario Scores",
        "",
        "| Scenario | " + " | ".join(report.dimension_scores.keys()) + " |",
        "|----------|" + "|".join(["-------" for _ in report.dimension_scores]) + "|",
    ]
    for i, sid in enumerate(report.scenario_ids):
        row_scores = []
        for d in report.dimension_scores.values():
            sc = d.scores[i] if i < len(d.scores) else "—"
            row_scores.append(f"{sc:.1f}" if isinstance(sc, float) else str(sc))
        lines.append(f"| {sid} | " + " | ".join(row_scores) + " |")
    lines.append("")

    # Justifications for failing or below-average dimensions
    for dim_id, d in report.dimension_scores.items():
        if not d.passed or d.average < 8.0:
            lines += [
                f"### {dim_id}: {d.name} — {d.average:.1f}/10",
                "",
            ]
            for sid, just in zip(report.scenario_ids, d.justifications):
                if just:
                    lines.append(f"**{sid}:** {just}")
                    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="LLM-Judged Analytical Quality Evaluator")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_MD)
    parser.add_argument("--json-only", action="store_true")
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print(
            "[CRITICAL] ANTHROPIC_API_KEY not set.\n"
            "This eval requires a live Claude API call to judge analytical quality.\n"
            "Set ANTHROPIC_API_KEY and re-run.",
            file=sys.stderr,
        )
        return 2

    # Verify scenario files
    missing = [f for f in SCENARIO_FILES if not (SCENARIOS_DIR / f).exists()]
    if missing:
        print(f"[CRITICAL] Missing scenario files: {missing}", file=sys.stderr)
        return 2

    # Load scenarios
    scenarios: List[Dict] = []
    for fname in SCENARIO_FILES:
        try:
            scenarios.append(json.loads((SCENARIOS_DIR / fname).read_text(encoding="utf-8")))
        except Exception as exc:
            print(f"[CRITICAL] Cannot load {fname}: {exc}", file=sys.stderr)
            return 2

    print(f"Loaded {len(scenarios)} scenarios. Running pipeline + LLM judge...")
    print(f"  Judge model: {JUDGE_MODEL}  |  Prompt version: {JUDGE_PROMPT_VERSION}")
    print()

    # Initialise dimension score collectors
    dim_scores: Dict[str, DimScore] = {
        dim_id: DimScore(dimension_id=dim_id, name=name, weight=weight)
        for dim_id, (name, weight) in _DIMENSION_META.items()
    }

    scenario_ids: List[str] = []
    skipped = 0
    raw_per_scenario: Dict[str, Any] = {}

    for scenario in scenarios:
        sid = scenario.get("scenario_id", "?")
        scenario_ids.append(sid)
        desc = scenario.get("description", "")[:60]
        print(f"  [{sid}] {desc}...", end=" ", flush=True)

        skill_outputs, err = _run_pipeline(scenario)
        if err or skill_outputs is None:
            print(f"PIPELINE ERROR: {err}")
            skipped += 1
            for d in dim_scores.values():
                d.scores.append(0.0)
                d.justifications.append(f"[pipeline error: {err}]")
            continue

        summary = _summarize_outputs(scenario, skill_outputs)
        print("pipeline OK, calling judge...", end=" ", flush=True)

        judge_result, judge_err = _call_judge(summary, api_key)
        if judge_err or judge_result is None:
            print(f"JUDGE ERROR: {judge_err}")
            skipped += 1
            for d in dim_scores.values():
                d.scores.append(0.0)
                d.justifications.append(f"[judge error: {judge_err}]")
            continue

        # Parse judge scores
        scenario_raw: Dict[str, Any] = {}
        for dim_id, d in dim_scores.items():
            dim_result = judge_result.get(dim_id, {})
            score = float(dim_result.get("score", 0))
            just = dim_result.get("justification", "")
            d.scores.append(score)
            d.justifications.append(just)
            scenario_raw[dim_id] = {"score": score, "justification": just}

        raw_per_scenario[sid] = scenario_raw
        avg = sum(judge_result.get(d, {}).get("score", 0) for d in _DIMENSION_META) / len(_DIMENSION_META)
        print(f"avg={avg:.1f}/10")

        # Small delay to avoid API rate limits
        time.sleep(1)

    report = _build_report(dim_scores, scenario_ids, skipped)

    json_path = args.output.with_suffix(".json") if not args.json_only else args.output
    if args.json_only:
        _write_json(report, json_path, raw_per_scenario)
    else:
        _write_json(report, DEFAULT_OUTPUT_JSON, raw_per_scenario)
        _write_markdown(report, args.output)

    # Summary
    print(f"\n{'='*60}")
    print(f"LLM JUDGE EVAL — {report.eval_date}")
    print(f"{'='*60}")
    print(f"Scope:    LLM-judged analytical quality (NOT schema compliance)")
    print(f"Judge:    {report.judge_model}  |  Prompt v{report.judge_prompt_version}")
    print(f"Overall:  {report.overall_score:.2f}/10  ({'PASS' if report.passed else 'FAIL'})")
    print()
    for dim_id, d in dim_scores.items():
        marker = "✓" if d.passed else "✗"
        print(f"  [{marker}] {dim_id}: {d.name:35s} {d.average:.1f}/{PASS_THRESHOLD}")
    print()

    if not args.json_only:
        print(f"Report: {args.output}")
        print(f"Scores: {DEFAULT_OUTPUT_JSON}")

    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
