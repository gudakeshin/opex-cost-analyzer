#!/usr/bin/env python3
"""
eval/run_document_processing_eval.py — OpEx Platform Document-Processing Quality Evaluator

Exercises the *document ingestion* pipeline (parse → schema inference → sheet
selection → normalization → hierarchical chunking → retrieval) against synthetic
golden fixtures and scores it on 8 dimensions across 3 domains.

Most dimensions are deterministic (rule-based against structured pipeline output);
DP-07 (parse fidelity) uses a provider-agnostic LLM judge (Claude default, Gemini
when LLM_PROVIDER=gemini) and is gracefully *skipped* when no provider is
configured (e.g. CI/pytest), so the eval always runs deterministically.

Retrieval (DP-06) is scored against the local keyword index (LocalDocumentIndex)
so results are deterministic and require no live Qdrant / embedding model.

Complements:
  eval/run_analysis_quality_eval.py — analysis output quality (post-ingestion)
  eval/run_feature_eval.py          — feature completeness (wiring, routes, OPAR)

Usage:
    PYTHONPATH=. python eval/run_document_processing_eval.py
    PYTHONPATH=. python eval/run_document_processing_eval.py --json-only

Exit codes:
    0 — all (non-skipped) dimensions pass their threshold
    1 — one or more dimensions fail
    2 — critical error (fixture build / import failure)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from app.config import DOC_CHILD_CHARS  # noqa: E402

# Load the sibling fixtures module by file path rather than `from eval...`. Under
# pytest, tests/ is prepended to sys.path and tests/eval/ (the golden-fixtures
# package) shadows the top-level eval/ package, so `import eval.<x>` resolves to
# the wrong package. Importing by path sidesteps the collision in both script and
# pytest contexts.
import importlib.util as _ilu  # noqa: E402


def _load_fixtures_module() -> Any:
    path = Path(__file__).resolve().parent / "_fixtures_document_processing.py"
    spec = _ilu.spec_from_file_location("dp_fixtures", path)
    module = _ilu.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["dp_fixtures"] = module
    spec.loader.exec_module(module)
    return module


_FIX = _load_fixtures_module()
ensure_fixtures = _FIX.ensure_fixtures
FIXTURES_DIR = _FIX.FIXTURES_DIR

CRITERIA_PATH = ROOT / "eval" / "document_processing_criteria.json"
DEFAULT_OUTPUT_MD = ROOT / "eval" / "document_processing_report.md"
DEFAULT_OUTPUT_JSON = ROOT / "eval" / "document_processing_scores.json"


# ---------------------------------------------------------------------------
# Data models (mirrors run_analysis_quality_eval.py)
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
    skipped: bool = False

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
    fixture_count: int
    judge_active: bool


# ---------------------------------------------------------------------------
# Fixture processing — run the real pipeline once per fixture
# ---------------------------------------------------------------------------

def _process_tabular(name: str, path: Path) -> Dict[str, Any]:
    from app.services.analysis import load_taxonomy
    from app.services.ingestion import (
        infer_tabular_schema,
        parse_spend_file_with_report,
        parse_spend_json_with_report,
        score_workbook_sheets,
    )

    obs: Dict[str, Any] = {"kind": "tabular", "parse_ok": False, "error": None}
    tax = load_taxonomy()
    try:
        if path.suffix.lower() == ".json":
            lines, report = parse_spend_json_with_report(path, tax, reporting_currency="INR")
        else:
            lines, report = parse_spend_file_with_report(path, tax, reporting_currency="INR")
        obs["parse_ok"] = True
        obs["lines"] = lines
        obs["line_count"] = len(lines)
        obs["report"] = report
        obs["quality"] = report.get("quality", {})
        obs["warnings"] = report.get("warnings", [])
    except Exception as exc:  # noqa: BLE001
        obs["error"] = f"{type(exc).__name__}: {exc}"
        return obs

    # Column schema inference (csv/xlsx only — json has no tabular schema pass).
    if path.suffix.lower() in (".csv", ".xlsx", ".xls"):
        try:
            obs["semantic_map"] = infer_tabular_schema(path).get("semantic_map", {})
        except Exception as exc:  # noqa: BLE001
            obs["semantic_map"] = {}
            obs["schema_error"] = str(exc)
    if path.suffix.lower() in (".xlsx", ".xls"):
        try:
            ranked = score_workbook_sheets(path)
            obs["top_sheet"] = (
                {"name": ranked[0].sheet_name, "role": ranked[0].inferred_role, "header_row": ranked[0].header_row}
                if ranked
                else {}
            )
        except Exception as exc:  # noqa: BLE001
            obs["top_sheet"] = {}
            obs["sheet_error"] = str(exc)
    return obs


def _process_document(name: str, path: Path, spec: Dict[str, Any], judge: bool) -> Dict[str, Any]:
    from app.services.chunking import split_markdown_hierarchical
    from app.services.document_index import LocalDocumentIndex
    from app.services.engagements_store import (
        add_document_record,
        create_engagement_manifest,
        delete_engagement,
        write_parent_nodes,
    )
    from app.services.ingestion import parse_document

    obs: Dict[str, Any] = {"kind": "document", "parse_ok": False, "error": None}
    try:
        text = parse_document(path)
        obs["parse_ok"] = bool(text and text.strip())
        obs["text"] = text
        obs["char_count"] = len(text)
    except Exception as exc:  # noqa: BLE001
        obs["error"] = f"{type(exc).__name__}: {exc}"
        return obs

    parents, children = split_markdown_hierarchical(
        text, doc_id="d", engagement_id="e", filename=name
    )
    parent_ids = {p.parent_id for p in parents}
    obs["parents"] = parents
    obs["children"] = children
    obs["parent_count"] = len(parents)
    obs["child_count"] = len(children)
    obs["empty_children"] = sum(1 for c in children if not c.text.strip())
    obs["orphans"] = sum(1 for c in children if c.parent_id not in parent_ids)
    obs["children_with_heading"] = sum(1 for c in children if (c.heading_path or "").strip())
    obs["max_child_len"] = max((len(c.text) for c in children), default=0)
    obs["has_table_row_child"] = any(
        ("|" in c.text or "1,200" in c.text or "800" in c.text) for c in children
    )

    # Retrieval via the deterministic local keyword index over a throwaway engagement.
    results: List[Dict[str, Any]] = []
    pairs = spec.get("expected", {}).get("retrieval", []) or []
    if pairs:
        eid = str(uuid.uuid4())
        did = str(uuid.uuid4())
        try:
            create_engagement_manifest(engagement_id=eid, company_name="DocEval")
            add_document_record(
                eid, document_id=did, filename=name,
                content_type="text/plain", size_bytes=obs["char_count"], raw_path="x",
            )
            rparents, rchildren = split_markdown_hierarchical(
                text, doc_id=did, engagement_id=eid, filename=name
            )
            write_parent_nodes(eid, did, rparents)
            LocalDocumentIndex().index_document(eid, did, rchildren)
            idx = LocalDocumentIndex()
            for pair in pairs:
                blocks = idx.retrieve(eid, pair["query"])
                texts = [b.get("text", "") for b in blocks]
                rank = next((i + 1 for i, t in enumerate(texts) if pair["expect_contains"] in t), None)
                results.append({"query": pair["query"], "hit": rank is not None, "rank": rank})
        finally:
            delete_engagement(eid)
    obs["retrieval"] = results

    # DP-07 — LLM-judged parse fidelity (docx/pdf where extraction is non-trivial).
    obs["fidelity_score"] = None
    if judge and spec.get("format") in ("docx", "pdf"):
        obs["fidelity_score"] = _judge_parse_fidelity(name, obs["text"])
    return obs


def _judge_parse_fidelity(name: str, parsed_text: str) -> Optional[float]:
    """Provider-agnostic LLM judge of extraction fidelity. None on any failure."""
    try:
        from app.opar.claude_client import _call_claude, _extract_json
    except Exception:  # noqa: BLE001
        return None
    system = "You are a document-extraction QA judge. Output ONLY valid JSON."
    prompt = (
        f"A document named '{name}' was parsed to plain text by an automated ingestion "
        "pipeline. Rate the extraction fidelity from 0-10: is the text coherent and "
        "complete, with section headings, numbers, and dates intact and no garbled or "
        "duplicated content? "
        'Return JSON only: {"score": <0-10 number>, "rationale": "<one sentence>"}\n\n'
        f"PARSED TEXT:\n{parsed_text[:3000]}"
    )
    try:
        raw = _call_claude(system=system, user_content=prompt, max_tokens=300)
        data = _extract_json(raw)
        return max(0.0, min(10.0, float(data.get("score"))))
    except Exception:  # noqa: BLE001
        return None


def _judge_available() -> bool:
    from app.config import ANTHROPIC_ENABLED, GEMINI_ENABLED

    return bool(ANTHROPIC_ENABLED or GEMINI_ENABLED) and not os.getenv("PYTEST_CURRENT_TEST")


def process_fixtures(specs: List[Dict[str, Any]], judge: bool) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for spec in specs:
        name = spec["name"]
        path = FIXTURES_DIR / name
        if spec["kind"] == "tabular":
            out[name] = _process_tabular(name, path)
        else:
            out[name] = _process_document(name, path, spec, judge)
        out[name]["spec"] = spec
    return out


# ---------------------------------------------------------------------------
# Scorers (one per dimension)
# ---------------------------------------------------------------------------

def _avg(xs: List[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def score_dp01_parse_success(obs: Dict[str, Dict]) -> Tuple[float, Dict]:
    total = len(obs)
    ok = sum(1 for o in obs.values() if o.get("parse_ok"))
    errors = {n: o["error"] for n, o in obs.items() if o.get("error")}
    return (ok / total * 10.0 if total else 0.0), {"parsed": ok, "total": total, "errors": errors}


def score_dp02_schema_role_accuracy(obs: Dict[str, Dict]) -> Tuple[float, Dict]:
    per: Dict[str, Any] = {}
    scores: List[float] = []
    for name, o in obs.items():
        expected = (o.get("spec", {}).get("expected", {}) or {}).get("schema_roles") or {}
        if not expected:
            continue
        smap = o.get("semantic_map", {}) or {}
        correct = sum(1 for role, col in expected.items() if smap.get(role) == col)
        sc = correct / len(expected) * 10.0
        scores.append(sc)
        per[name] = {"correct": correct, "expected": len(expected), "score": round(sc, 1)}
    return _avg(scores), per


def score_dp03_sheet_selection(obs: Dict[str, Dict]) -> Tuple[float, Dict]:
    per: Dict[str, Any] = {}
    scores: List[float] = []
    for name, o in obs.items():
        exp = o.get("spec", {}).get("expected", {}) or {}
        ledger = exp.get("ledger_sheet")
        if not ledger:
            continue
        top = o.get("top_sheet", {}) or {}
        sc = 0.0
        sc += 4.0 if top.get("name") == ledger else 0.0
        sc += 3.0 if top.get("role") == "transaction_ledger" else 0.0
        sc += 3.0 if top.get("header_row") == exp.get("ledger_header_row", 0) else 0.0
        scores.append(sc)
        per[name] = {"selected": top, "expected_ledger": ledger, "score": sc}
    return _avg(scores), per


def score_dp04_normalization_fidelity(obs: Dict[str, Dict]) -> Tuple[float, Dict]:
    per: Dict[str, Any] = {}
    scores: List[float] = []
    for name, o in obs.items():
        exp = o.get("spec", {}).get("expected", {}) or {}
        if "line_count" not in exp:
            continue  # skip malformed / non-normalizing fixtures
        sc = 0.0
        lc_ok = o.get("line_count") == exp["line_count"]
        sc += 4.0 if lc_ok else 0.0
        total = float((o.get("quality") or {}).get("total_amount", 0.0))
        tot_ok = abs(total - float(exp.get("total_amount", 0.0))) <= max(1.0, 0.01 * float(exp.get("total_amount", 1.0)))
        sc += 4.0 if tot_ok else 0.0
        lines = o.get("lines") or []
        ccy_ok = bool(lines) and bool(getattr(lines[0], "currency", None))
        sc += 2.0 if ccy_ok else 0.0
        scores.append(sc)
        per[name] = {"line_count_ok": lc_ok, "total_ok": tot_ok, "currency_ok": ccy_ok, "score": sc}
    return _avg(scores), per


def score_dp05_chunk_structure(obs: Dict[str, Dict]) -> Tuple[float, Dict]:
    per: Dict[str, Any] = {}
    scores: List[float] = []
    for name, o in obs.items():
        if o.get("kind") != "document":
            continue
        exp = o.get("spec", {}).get("expected", {}) or {}
        earned = 0.0
        possible = 0.0

        possible += 1.0
        earned += 1.0 if o.get("parent_count", 0) >= exp.get("min_parents", 1) else 0.0
        possible += 1.0
        earned += 1.0 if o.get("child_count", 0) >= exp.get("min_children", 1) else 0.0
        possible += 2.0
        earned += 2.0 if o.get("empty_children", 1) == 0 else 0.0
        possible += 2.0
        earned += 2.0 if o.get("orphans", 1) == 0 else 0.0
        possible += 1.0
        earned += 1.0 if o.get("max_child_len", 0) <= DOC_CHILD_CHARS * 1.5 else 0.0
        if exp.get("expect_heading_path"):
            possible += 2.0
            earned += 2.0 if o.get("children_with_heading", 0) == o.get("child_count", -1) else 0.0
        if exp.get("expect_table_rows"):
            possible += 1.0
            earned += 1.0 if o.get("has_table_row_child") else 0.0

        sc = (earned / possible * 10.0) if possible else 0.0
        scores.append(sc)
        per[name] = {
            "parents": o.get("parent_count"),
            "children": o.get("child_count"),
            "empty": o.get("empty_children"),
            "orphans": o.get("orphans"),
            "score": round(sc, 1),
        }
    return _avg(scores), per


def score_dp06_retrieval_precision(obs: Dict[str, Dict]) -> Tuple[float, Dict]:
    hits = 0
    total = 0
    rr: List[float] = []
    per: Dict[str, Any] = {}
    for name, o in obs.items():
        results = o.get("retrieval") or []
        if not results:
            continue
        per[name] = results
        for r in results:
            total += 1
            if r["hit"]:
                hits += 1
                rr.append(1.0 / r["rank"])
            else:
                rr.append(0.0)
    if total == 0:
        return 0.0, {"note": "no retrieval pairs"}
    hit_rate = hits / total
    mrr = _avg(rr)
    score = (0.6 * hit_rate + 0.4 * mrr) * 10.0
    return score, {"hit_rate": round(hit_rate, 2), "mrr": round(mrr, 2), "hits": hits, "total": total, "per_fixture": per}


def score_dp07_parse_fidelity(obs: Dict[str, Dict], judge_active: bool) -> Tuple[float, Dict, bool]:
    """Returns (score, evidence, skipped)."""
    scored = {n: o["fidelity_score"] for n, o in obs.items() if o.get("fidelity_score") is not None}
    if not judge_active or not scored:
        return 0.0, {"note": "skipped — no LLM provider (set ANTHROPIC_API_KEY or GEMINI_API_KEY)"}, True
    return _avg(list(scored.values())), {"per_fixture": {n: round(s, 1) for n, s in scored.items()}}, False


def score_dp08_quality_flag_capture(obs: Dict[str, Dict]) -> Tuple[float, Dict]:
    per: Dict[str, Any] = {}
    scores: List[float] = []
    for name, o in obs.items():
        if o.get("kind") != "tabular":
            continue
        exp = o.get("spec", {}).get("expected", {}) or {}
        q = o.get("quality") or {}
        sc = 0.0
        flags_present = all(k in q for k in ("rows_parsed", "rows_with_amount", "total_amount", "zero_spend_warning"))
        sc += 4.0 if flags_present else 0.0
        zsw_ok = bool(q.get("zero_spend_warning")) == bool(exp.get("zero_spend_warning"))
        sc += 4.0 if zsw_ok else 0.0
        if exp.get("expect_warnings"):
            sc += 2.0 if (o.get("warnings")) else 0.0
        else:
            sc += 2.0  # no warnings expected — full marks when none erroneously raised
            if o.get("warnings"):
                sc -= 2.0
        scores.append(max(0.0, sc))
        per[name] = {"flags_present": flags_present, "zero_spend_warning_ok": zsw_ok, "score": max(0.0, sc)}
    return _avg(scores), per


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

_DIMENSION_META = {
    "DP-01": ("Parse Success Rate", "parse_normalize", 0.30, 9.0),
    "DP-02": ("Schema Role Accuracy", "parse_normalize", 0.30, 7.0),
    "DP-03": ("Sheet Selection Correctness", "parse_normalize", 0.15, 7.0),
    "DP-04": ("Normalization Fidelity", "parse_normalize", 0.25, 7.0),
    "DP-05": ("Chunk Structure Integrity", "chunk_retrieve", 0.40, 7.0),
    "DP-06": ("Retrieval Precision", "chunk_retrieve", 0.40, 6.0),
    "DP-07": ("Parse Fidelity (LLM judge)", "chunk_retrieve", 0.20, 6.0),
    "DP-08": ("Quality-Flag Capture", "quality_signals", 1.00, 7.0),
}

_DOMAIN_META = {
    "parse_normalize": ("Parse & Normalize", 0.45),
    "chunk_retrieve": ("Chunk & Retrieve", 0.35),
    "quality_signals": ("Quality Signals", 0.20),
}

_REMEDIATION = {
    "DP-01": "Inspect parse_document / parse_spend_file_with_report for the failing format; add a parser branch or fix the reader.",
    "DP-02": "Extend the token lists in ingestion.infer_tabular_schema role_map so the column header maps to the right semantic_role.",
    "DP-03": "Tune ingestion.score_workbook_sheets header/role heuristics so the transaction ledger outranks summary/assumptions sheets.",
    "DP-04": "Check _dataframe_to_spend_lines amount coercion and currency capture; ensure all data rows normalize to NormalizedSpendLine.",
    "DP-05": "Review chunking.split_markdown_hierarchical: avoid empty children, propagate heading_path, keep child sizes under DOC_CHILD_CHARS, split table rows.",
    "DP-06": "Improve retrieval recall — chunk granularity, keyword/embedding scoring, or auto-merge thresholds in document_index.",
    "DP-07": "Improve extraction fidelity (enable LlamaParse for PDF/DOCX, or fix native parse_document) so headings/numbers survive.",
    "DP-08": "Ensure _enrich_ingestion_report sets rows_parsed/rows_with_amount/total_amount and raises zero_spend_warning + warnings on bad input.",
}


def _aggregate(raw: Dict[str, Tuple], skipped_ids: set) -> Dict[str, DimensionResult]:
    results: Dict[str, DimensionResult] = {}
    for dim_id, (name, domain, weight, threshold) in _DIMENSION_META.items():
        score, evidence = raw[dim_id][0], raw[dim_id][1]
        skipped = dim_id in skipped_ids
        passed = True if skipped else (score >= threshold)
        if skipped:
            summary = "Skipped (no LLM provider)"
            detail = "SKIPPED — DP-07 needs ANTHROPIC_API_KEY or GEMINI_API_KEY; not counted in pass/fail."
        else:
            summary = f"{score:.1f}/10 (threshold {threshold})"
            detail = ("PASS" if passed else "FAIL") + f" — {score:.1f} vs {threshold}"
        results[dim_id] = DimensionResult(
            dimension_id=dim_id, name=name, domain=domain, weight=weight,
            threshold_pass=threshold, raw_score=score, passed=passed,
            evidence=evidence, finding_summary=summary, finding_detail=detail,
            remediation=_REMEDIATION.get(dim_id, ""), skipped=skipped,
        )
    return results


def _build_report(dim_results: Dict[str, DimensionResult], fixture_count: int, judge_active: bool) -> EvalReport:
    domain_results: List[DomainResult] = []
    for domain_key, (domain_display, domain_weight) in _DOMAIN_META.items():
        dims = [d for d in dim_results.values() if d.domain == domain_key and not d.skipped]
        if not dims:
            # All dims in this domain skipped — represent with the skipped ones.
            dims = [d for d in dim_results.values() if d.domain == domain_key]
        total_weight = sum(d.weight for d in dims)
        domain_score = sum(d.raw_score * d.weight for d in dims) / total_weight if total_weight else 0.0
        domain_results.append(DomainResult(
            domain_name=domain_key, domain_display=domain_display, domain_weight=domain_weight,
            dimension_results=[d for d in dim_results.values() if d.domain == domain_key],
            domain_score=domain_score,
            passed=all(d.passed for d in dim_results.values() if d.domain == domain_key),
        ))
    overall = sum(dr.domain_score * dr.domain_weight for dr in domain_results)
    top_gaps = sorted(
        [
            {"dimension_id": d.dimension_id, "name": d.name, "score": round(d.raw_score, 2),
             "threshold": d.threshold_pass, "gap": round(d.gap, 2), "remediation": d.remediation}
            for d in dim_results.values() if not d.passed
        ],
        key=lambda x: x["gap"], reverse=True,
    )
    roadmap = [
        {"priority": i + 1, "dimension": g["name"], "gap": g["gap"], "action": g["remediation"]}
        for i, g in enumerate(top_gaps)
    ]
    return EvalReport(
        platform_version="v2.1", eval_date=date.today().isoformat(), overall_score=overall,
        domain_results=domain_results, top_gaps=top_gaps, remediation_roadmap=roadmap,
        passed=all(d.passed for d in dim_results.values()),
        fixture_count=fixture_count, judge_active=judge_active,
    )


# ---------------------------------------------------------------------------
# Report writers
# ---------------------------------------------------------------------------

def _write_json(report: EvalReport, dim_results: Dict[str, DimensionResult], path: Path) -> None:
    payload = {
        "eval_date": report.eval_date,
        "score_type": "structural",
        "scope": (
            "Document ingestion pipeline quality: parse, schema inference, sheet selection, "
            "normalization, chunking, retrieval. Does NOT validate downstream analytical accuracy."
        ),
        "platform_version": report.platform_version,
        "overall_score": round(report.overall_score, 3),
        "passed": report.passed,
        "fixture_count": report.fixture_count,
        "llm_judge_active": report.judge_active,
        "domains": [
            {
                "name": dr.domain_name, "display": dr.domain_display, "weight": dr.domain_weight,
                "score": round(dr.domain_score, 3), "passed": dr.passed,
                "dimensions": [
                    {"id": d.dimension_id, "name": d.name, "weight": d.weight,
                     "threshold": d.threshold_pass, "score": round(d.raw_score, 3),
                     "passed": d.passed, "skipped": d.skipped, "gap": round(d.gap, 3),
                     "evidence": d.evidence, "remediation": d.remediation}
                    for d in dr.dimension_results
                ],
            }
            for dr in report.domain_results
        ],
        "top_gaps": report.top_gaps,
        "remediation_roadmap": report.remediation_roadmap,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_markdown(report: EvalReport, path: Path) -> None:
    status = "✅ PASS" if report.passed else "❌ FAIL"
    judge = "active" if report.judge_active else "skipped (no LLM provider)"
    lines = [
        "# OpEx Platform — Document Processing Quality Eval",
        "",
        f"**Date:** {report.eval_date}  |  **Platform:** {report.platform_version}  |  "
        f"**Overall:** {report.overall_score:.2f}/10  |  **Status:** {status}",
        "",
        f"Fixtures: {report.fixture_count}  |  LLM judge (DP-07): {judge}  |  "
        f"Retrieval backend: local keyword index (deterministic)",
        "",
        "> Scores the document ingestion pipeline — parse → schema inference → sheet "
        "selection → normalization → hierarchical chunking → retrieval — against synthetic "
        "golden fixtures. DP-01..06 and DP-08 are deterministic; DP-07 uses a provider-agnostic LLM judge.",
        ">",
        "> ⚠️ **SCORE TYPE: STRUCTURAL** — Pipeline correctness, not analytical quality. "
        "Does NOT validate savings recommendations. See `run_llm_judge_eval.py`.",
        "",
    ]
    for dr in report.domain_results:
        sd = "PASS" if dr.passed else "FAIL"
        lines += [
            f"## {dr.domain_display} — {dr.domain_score:.1f}/10 [{sd}]",
            "",
            "| ID | Dimension | Weight | Score | Threshold | Status |",
            "|----|-----------|--------|-------|-----------|--------|",
        ]
        for d in dr.dimension_results:
            ds = "⏭️ SKIP" if d.skipped else ("✅" if d.passed else "❌")
            lines.append(
                f"| {d.dimension_id} | {d.name} | {d.weight:.0%} | {d.raw_score:.1f} | {d.threshold_pass} | {ds} |"
            )
        lines.append("")
        for d in dr.dimension_results:
            if not d.passed or d.skipped:
                lines += [
                    f"### {d.dimension_id}: {d.name}",
                    "",
                    f"**Finding:** {d.finding_detail}",
                    "",
                    f"**Evidence:** `{json.dumps(d.evidence)[:400]}`",
                    "",
                    f"**Remediation:** {d.remediation}",
                    "",
                ]
    if report.remediation_roadmap:
        lines += ["## Improvement Roadmap", ""]
        for item in report.remediation_roadmap:
            lines.append(f"{item['priority']}. **{item['dimension']}** (gap {item['gap']}): {item['action']}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="OpEx Document Processing Quality Evaluator")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_MD)
    parser.add_argument("--json-only", action="store_true")
    parser.add_argument("--no-judge", action="store_true", help="Disable the DP-07 LLM judge even if a provider is configured.")
    args = parser.parse_args()

    try:
        specs = ensure_fixtures()
    except Exception as exc:  # noqa: BLE001
        print(f"[CRITICAL] Fixture build failed: {exc}", file=sys.stderr)
        return 2

    judge_active = _judge_available() and not args.no_judge
    print(f"Loaded {len(specs)} fixtures. LLM judge: {'active' if judge_active else 'skipped'}. Running pipeline...")

    try:
        obs = process_fixtures(specs, judge_active)
    except Exception as exc:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        print(f"[CRITICAL] Processing failed: {exc}", file=sys.stderr)
        return 2

    for name, o in obs.items():
        flag = "OK" if o.get("parse_ok") else f"FAIL ({o.get('error')})"
        extra = (
            f"{o.get('line_count', '?')} lines"
            if o.get("kind") == "tabular"
            else f"{o.get('parent_count', '?')}p/{o.get('child_count', '?')}c"
        )
        print(f"  [{name}] {flag} — {extra}")

    raw = {
        "DP-01": score_dp01_parse_success(obs),
        "DP-02": score_dp02_schema_role_accuracy(obs),
        "DP-03": score_dp03_sheet_selection(obs),
        "DP-04": score_dp04_normalization_fidelity(obs),
        "DP-05": score_dp05_chunk_structure(obs),
        "DP-06": score_dp06_retrieval_precision(obs),
        "DP-08": score_dp08_quality_flag_capture(obs),
    }
    dp07_score, dp07_ev, dp07_skipped = score_dp07_parse_fidelity(obs, judge_active)
    raw["DP-07"] = (dp07_score, dp07_ev)
    skipped_ids = {"DP-07"} if dp07_skipped else set()

    dim_results = _aggregate(raw, skipped_ids)
    # judge "active" in the report means it actually produced fidelity scores.
    report = _build_report(dim_results, len(specs), judge_active and not dp07_skipped)

    _write_json(report, dim_results, DEFAULT_OUTPUT_JSON)
    if not args.json_only:
        _write_markdown(report, args.output)

    print(f"\n{'='*60}")
    print(f"DOCUMENT PROCESSING EVAL — {report.eval_date}")
    print(f"{'='*60}")
    print(f"Overall: {report.overall_score:.2f}/10  ({'PASS' if report.passed else 'FAIL'})")
    for dr in report.domain_results:
        print(f"  {dr.domain_display}: {dr.domain_score:.1f}/10")
        for d in dr.dimension_results:
            mark = "⏭" if d.skipped else ("✓" if d.passed else "✗")
            print(f"    [{mark}] {d.dimension_id}: {d.name:32s} {d.raw_score:.1f}/{d.threshold_pass}")
    if report.top_gaps:
        print("\nTop gaps:")
        for g in report.top_gaps[:4]:
            print(f"  {g['dimension_id']} {g['name']}: {g['score']:.1f} (gap {g['gap']:.1f})")
    if not args.json_only:
        print(f"\nReport: {args.output}\nScores: {DEFAULT_OUTPUT_JSON}")
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
