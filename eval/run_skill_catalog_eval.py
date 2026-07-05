#!/usr/bin/env python3
"""Deterministic skill catalog eval — no live LLM calls."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.skills.discovery import discover_relevant_skills
from app.skills.manifest import manifest_skills, validate_manifest_drift
from app.skills.registry import parse_skill_md, validate_declarative_output
from app.config import SKILLS_DIR

DISCOVERY_CASES = [
    (
        "compare my spend to industry peers and benchmark gaps",
        {"peer-benchmarker", "internal-benchmarker"},
    ),
    (
        "model savings NPV phased initiatives cost to achieve",
        {"savings-modeler", "value-bridge-calculator"},
    ),
    (
        "diagnose why spend is above peers root cause",
        {"root-cause-analyzer"},
    ),
    (
        "categorize and profile uploaded spend data",
        {"spend-profiler"},
    ),
]

SCORES_PATH = ROOT / "eval" / "skill_catalog_scores.json"
REPORT_PATH = ROOT / "eval" / "skill_catalog_report.md"


def score_discovery() -> dict:
    hits = 0
    total = len(DISCOVERY_CASES)
    details = []
    for query, expected in DISCOVERY_CASES:
        results = discover_relevant_skills(query, k=5)
        names = {r["name"] for r in results}
        ok = bool(names & expected)
        hits += int(ok)
        details.append({"query": query, "expected_any": sorted(expected), "top5": [r["name"] for r in results], "hit": ok})
    return {"mrr_at_3": round(hits / total, 3), "cases": details}


def score_rubric(min_score: float = 3.0) -> dict:
    rows = []
    below = []
    for path in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        meta = parse_skill_md(path)
        text = path.read_text(encoding="utf-8")
        score = 0.0
        fm = meta.get("description") and len(str(meta.get("description") or "")) >= 30
        if fm:
            score += 1
        if meta.get("methodology_summary"):
            score += 1
        if meta.get("inputs"):
            score += 1
        if meta.get("output_fields"):
            score += 1
        if len(text.splitlines()) >= 15:
            score += 1
        rows.append({"name": path.parent.name, "score": score})
        if score < min_score:
            below.append(path.parent.name)
    return {"avg_score": round(sum(r["score"] for r in rows) / max(len(rows), 1), 2), "below_threshold": below}


def score_declarative_schema() -> dict:
    ok = validate_declarative_output({"a": 1, "b": 2}, ["a", "b"]) is None
    fail = validate_declarative_output({"a": 1}, ["a", "b"]) == "schema_parse_fail"
    return {"passes": ok and fail}


def run_eval() -> dict:
    drift = validate_manifest_drift()
    report = {
        "discovery": score_discovery(),
        "rubric": score_rubric(),
        "declarative_schema": score_declarative_schema(),
        "manifest_drift_errors": drift,
        "manifest_skill_count": len(manifest_skills()),
    }
    report["overall_pass"] = (
        report["discovery"]["mrr_at_3"] >= 0.75
        and not drift
        and report["declarative_schema"]["passes"]
    )
    return report


def render_markdown(report: dict) -> str:
    lines = [
        "# Skill Catalog Eval",
        "",
        f"**Overall:** {'PASS' if report['overall_pass'] else 'FAIL'}",
        f"**Manifest skill count:** {report['manifest_skill_count']}",
        "",
        "## Discovery Routing",
        "",
        f"MRR@3: {report['discovery']['mrr_at_3']}",
        "",
        "| Query | Expected (any) | Top 5 | Hit |",
        "|---|---|---|---|",
    ]
    for case in report["discovery"]["cases"]:
        lines.append(
            f"| {case['query']} | {', '.join(case['expected_any'])} | "
            f"{', '.join(case['top5'])} | {'yes' if case['hit'] else 'no'} |"
        )
    lines += [
        "",
        "## Rubric (SKILL.md quality)",
        "",
        f"Average score: {report['rubric']['avg_score']} / 5",
    ]
    below = report["rubric"]["below_threshold"]
    if below:
        lines += ["", "**Below threshold (<3.0):** " + ", ".join(below)]
    else:
        lines += ["", "No skills below the 3.0 threshold."]
    lines += [
        "",
        "## Declarative Output Schema Enforcement",
        "",
        f"Passes: {report['declarative_schema']['passes']}",
        "",
        "## Manifest Drift",
        "",
    ]
    if report["manifest_drift_errors"]:
        lines += [f"- {err}" for err in report["manifest_drift_errors"]]
    else:
        lines.append("No drift errors.")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    report = run_eval()
    SCORES_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    REPORT_PATH.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["overall_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
