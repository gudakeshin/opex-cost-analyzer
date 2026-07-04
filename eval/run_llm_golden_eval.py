#!/usr/bin/env python3
"""
eval/run_llm_golden_eval.py — Golden-set evals for NL→SQL and what-if parsing.

Deterministic (no live LLM): rule-based NL tiers, mocked empty LLM parse path,
fixed spend fixture. Re-run this script rather than trusting committed reports.

Usage:
    PYTHONPATH=. python eval/run_llm_golden_eval.py
    PYTHONPATH=. python eval/run_llm_golden_eval.py --json-only
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

ROOT = Path(__file__).parent.parent
GOLDEN_DIR = ROOT / "tests" / "eval" / "golden" / "llm_golden"
DEFAULT_JSON = ROOT / "eval" / "llm_golden_scores.json"
DEFAULT_MD = ROOT / "eval" / "llm_golden_report.md"

os.environ.setdefault("PYTEST_CURRENT_TEST", "llm_golden_eval")


@dataclass
class CaseResult:
    case_id: str
    domain: str
    passed: bool
    detail: str


@dataclass
class SuiteResult:
    name: str
    cases_run: int = 0
    cases_passed: int = 0
    case_results: List[CaseResult] = field(default_factory=list)

    @property
    def score(self) -> float:
        if self.cases_run == 0:
            return 0.0
        return self.cases_passed / self.cases_run

    @property
    def passed(self) -> bool:
        return self.cases_passed == self.cases_run


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _result_rows(out: Dict[str, Any]) -> List[Dict[str, Any]]:
    result = out.get("result")
    if isinstance(result, dict):
        rows = result.get("rows")
        columns = result.get("columns")
        if isinstance(rows, list) and isinstance(columns, list) and rows and isinstance(rows[0], list):
            return [dict(zip(columns, row)) for row in rows]
        if isinstance(rows, list) and rows and isinstance(rows[0], dict):
            return rows
    prov = out.get("provenance")
    if isinstance(prov, dict):
        inner = prov.get("result")
        if isinstance(inner, dict) and inner:
            return [inner]
    return []


def _supplier_column(rows: List[Dict[str, Any]]) -> str | None:
    for key in ("supplier", "Supplier", "SUPPLIER"):
        if rows and key in rows[0]:
            return key
    return None


def run_nl_sql_suite(tmp_path: Path) -> SuiteResult:
    from eval._fixtures_llm_golden import GOLDEN_SESSION_ID, build_golden_store
    from app.opar.models import ObserveContext
    from app.opar.tools.context import ToolSessionContext
    from app.opar.tools.nl_query import classify_nl_query_tier, run_natural_language_query

    spec = _load_json(GOLDEN_DIR / "nl_sql_cases.json")
    suite = SuiteResult(name="nl_sql")
    store = build_golden_store(tmp_path)

    ctx = ObserveContext(
        user_message="golden",
        session_id=GOLDEN_SESSION_ID,
        engagement_id=store.engagement_id,
    )
    session = ToolSessionContext(ctx=ctx)

    with patch("app.opar.tools.nl_query._open_agent_store", return_value=store), patch(
        "app.opar.tools.nl_query._llm_aggregate_or_sql", return_value=None
    ), patch("app.opar.tools.nl_query._execute_skill_tier") as mock_skill:
        mock_skill.return_value = {
            "skill": "spend-profiler",
            "reason": "mock",
            "result": {"category_profile": []},
        }
        for case in spec.get("cases") or []:
            case_id = str(case.get("id") or "")
            question = str(case.get("question") or "")
            prefer = case.get("prefer") or "auto"
            expected_tier = str(case.get("expected_tier") or "")

            tier = classify_nl_query_tier(question, prefer=prefer)  # type: ignore[arg-type]
            if expected_tier and tier != expected_tier:
                suite.case_results.append(
                    CaseResult(case_id, "nl_sql", False, f"tier={tier} expected={expected_tier}")
                )
                suite.cases_run += 1
                continue

            out = run_natural_language_query(session, question=question, prefer=prefer)  # type: ignore[arg-type]
            actual_tier = str(out.get("tier") or "")
            ok = actual_tier == expected_tier
            detail = f"tier={actual_tier}"

            if ok and expected_tier in ("aggregate", "sql"):
                rows = _result_rows(out)
                min_rows = int(case.get("expect_min_rows") or 0)
                if min_rows and len(rows) < min_rows:
                    ok = False
                    detail = f"rows={len(rows)} expected>={min_rows}"
                ordered = case.get("expect_ordered_suppliers")
                if ok and ordered:
                    col = _supplier_column(rows)
                    if not col:
                        ok = False
                        detail = "missing supplier column"
                    else:
                        actual = [str(r.get(col)) for r in rows[: len(ordered)]]
                        if actual != ordered:
                            ok = False
                            detail = f"suppliers={actual} expected={ordered}"
                if ok and out.get("error"):
                    ok = False
                    detail = str(out.get("error"))

            suite.cases_run += 1
            if ok:
                suite.cases_passed += 1
            suite.case_results.append(CaseResult(case_id, "nl_sql", ok, detail))

    return suite


def run_scenario_parse_suite() -> SuiteResult:
    from eval._fixtures_llm_golden import GOLDEN_SESSION_ID, golden_categories
    from app.opar.models import ObserveContext
    from app.opar.tools.context import ToolSessionContext
    from app.opar.tools.scenario_parser import parse_what_if_request

    spec = _load_json(GOLDEN_DIR / "scenario_parse_cases.json")
    suite = SuiteResult(name="scenario_parse")

    ctx = ObserveContext(user_message="what-if", session_id=GOLDEN_SESSION_ID)
    session = ToolSessionContext(ctx=ctx)
    session.skill_outputs = {
        "spend-profiler": {"category_profile": golden_categories()},
    }

    empty_llm = {"scenarios": [], "drivers": {}}
    with patch("app.opar.tools.scenario_parser._llm_parse_what_if", return_value=empty_llm):
        for case in spec.get("cases") or []:
            case_id = str(case.get("id") or "")
            question = str(case.get("question") or "")
            parsed = parse_what_if_request(session, question)
            ok = True
            detail = "ok"

            for key, val in (case.get("expect_drivers") or {}).items():
                actual = parsed.get("drivers", {}).get(key)
                if actual is None or abs(float(actual) - float(val)) > 1e-6:
                    ok = False
                    detail = f"driver {key}={actual} expected={val}"
                    break

            if ok and case.get("expect_scenario_fields"):
                scenarios = parsed.get("scenarios") or []
                if not scenarios:
                    ok = False
                    detail = "no scenarios parsed"
                else:
                    first = scenarios[0]
                    for key, val in case["expect_scenario_fields"].items():
                        actual = first.get(key)
                        if isinstance(val, float):
                            if actual is None or abs(float(actual) - val) > 1e-6:
                                ok = False
                                detail = f"scenario.{key}={actual} expected={val}"
                                break
                        elif str(actual or "").lower() != str(val).lower():
                            ok = False
                            detail = f"scenario.{key}={actual} expected={val}"
                            break

            suite.cases_run += 1
            if ok:
                suite.cases_passed += 1
            suite.case_results.append(CaseResult(case_id, "scenario_parse", ok, detail))

    return suite


def run_all() -> Dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        nl = run_nl_sql_suite(Path(tmp))
    scenario = run_scenario_parse_suite()
    suites = [nl, scenario]
    total_run = sum(s.cases_run for s in suites)
    total_pass = sum(s.cases_passed for s in suites)
    return {
        "total_cases": total_run,
        "total_passed": total_pass,
        "overall_score": total_pass / total_run if total_run else 0.0,
        "passed": all(s.passed for s in suites),
        "suites": {
            s.name: {
                "cases_run": s.cases_run,
                "cases_passed": s.cases_passed,
                "score": s.score,
                "passed": s.passed,
                "failures": [
                    {"id": c.case_id, "detail": c.detail}
                    for c in s.case_results
                    if not c.passed
                ],
            }
            for s in suites
        },
    }


def _write_report(payload: Dict[str, Any], md_path: Path) -> None:
    lines = [
        "# LLM Golden-Set Eval Report",
        "",
        f"**Overall:** {payload['total_passed']}/{payload['total_cases']} "
        f"({payload['overall_score'] * 100:.1f}%) — "
        f"{'PASS' if payload['passed'] else 'FAIL'}",
        "",
    ]
    for name, suite in payload.get("suites", {}).items():
        lines.append(f"## {name}")
        lines.append(
            f"- Score: {suite['cases_passed']}/{suite['cases_run']} ({suite['score'] * 100:.1f}%)"
        )
        for fail in suite.get("failures") or []:
            lines.append(f"- FAIL `{fail['id']}`: {fail['detail']}")
        lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run LLM golden-set evals (deterministic).")
    parser.add_argument("--json-only", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--report", type=Path, default=DEFAULT_MD)
    args = parser.parse_args()

    try:
        payload = run_all()
    except Exception as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        return 2

    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _write_report(payload, args.report)
    if not args.json_only:
        print(json.dumps(payload, indent=2))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
