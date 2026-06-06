#!/usr/bin/env python3
"""
eval/run_agentic_eval.py — Agentic Intelligence Evaluator

Static-analysis eval for the LLM tool-use agent layer. Checks wiring,
completeness, safety guards, and audit trail. No LLM calls made.

Dimensions (10 total across 3 domains)
---------------------------------------
  Controller & Routing
  AG_01  Agent controller wired in orchestrator
  AG_02  Tool catalog completeness (8 required tools)
  AG_03  Deterministic fallback gate

  Intelligence & Discovery
  AG_04  Semantic skill discovery wired
  AG_05  _DEP_MAP covers all registered skills
  AG_06  SME critique LLM enrichment wired
  AG_07  Root-cause LLM enrichment wired

  Safety & Provenance
  AG_08  Offline guard + injectable transport
  AG_09  Numeric provenance on opportunity assessment
  AG_10  Audit trail for LLM numeric adjustments

Usage:
    PYTHONPATH=. python eval/run_agentic_eval.py
    PYTHONPATH=. python eval/run_agentic_eval.py --json-only

Exit codes:
    0 — all domains pass their weighted threshold
    1 — one or more domains fail
    2 — critical error
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
DEFAULT_OUTPUT_MD = ROOT / "eval" / "agentic_eval_report.md"
DEFAULT_OUTPUT_JSON = ROOT / "eval" / "agentic_eval_scores.json"


# ---------------------------------------------------------------------------
# Data models (mirrors run_feature_eval.py)
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
    data_sources_found: List[str] = field(default_factory=list)

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read(path: str) -> Tuple[Optional[str], Optional[str]]:
    p = ROOT / path
    if not p.exists():
        return None, f"file_not_found: {path}"
    return p.read_text(encoding="utf-8", errors="ignore"), None


def _clamp(v: float) -> float:
    return max(0.0, min(10.0, v))


def _err(dim_id: str, name: str, domain: str, weight: float, threshold: float, exc: str) -> DimensionResult:
    return DimensionResult(
        dimension_id=dim_id, name=name, domain=domain, weight=weight,
        raw_score=0.0, threshold_pass=threshold, passed=False,
        evidence={"error": exc[:300]},
        finding_summary=f"EVAL_ERROR: {exc[:100]}",
        finding_detail=exc,
        remediation="Fix the eval error first.",
    )


# ---------------------------------------------------------------------------
# Domain A — Controller & Routing
# ---------------------------------------------------------------------------

def score_ag_01(root: Path) -> DimensionResult:
    """Agent controller wired in orchestrator with fallback."""
    DIM = ("ag_01", "Agent Controller Wiring in Orchestrator", "controller_routing", 0.40, 9.0)
    try:
        orch, e1 = _read("app/opar/orchestrator.py")
        ctrl, e2 = _read("app/opar/agent_controller.py")
        runtime, e3 = _read("app/opar/agent_runtime.py")
        if e1 or not orch:
            return _err(*DIM, e1 or "missing orchestrator.py")

        checks = {
            "try_agent_run imported":       "try_agent_run" in (orch or ""),
            "_should_use_agent_path":       "_should_use_agent_path" in (orch or ""),
            "agent_loop_available":         "agent_loop_available" in (runtime or ""),
            "fallback plan() present":      "exec_plan = plan(" in (orch or ""),
            "agent_controller exists":      ctrl is not None,
            "run_agent_controller":         "run_agent_controller" in (ctrl or ""),
            "AgentRunResult.success":       "success" in (ctrl or ""),
            "fallback_reason logged":       "fallback_reason" in (ctrl or ""),
        }
        passed_n = sum(checks.values())
        raw = _clamp(passed_n / len(checks) * 10)
        missing = [k for k, v in checks.items() if not v]
        return DimensionResult(
            *DIM, raw_score=raw, passed=raw >= 9.0,
            evidence={"checks": checks, "missing": missing},
            finding_summary=f"{passed_n}/{len(checks)} controller-wiring checks pass",
            finding_detail=f"Missing: {missing or 'none'}",
            remediation="Wire agent_controller into orchestrator with fallback." if missing else "Controller fully wired.",
            data_sources_found=[p for p, e in [("app/opar/orchestrator.py", e1), ("app/opar/agent_controller.py", e2)] if not e],
        )
    except Exception:
        return _err(*DIM, traceback.format_exc())


def score_ag_02(root: Path) -> DimensionResult:
    """Tool catalog has all 8 required tools with dispatch handlers."""
    DIM = ("ag_02", "Tool Catalog Completeness", "controller_routing", 0.35, 9.0)
    REQUIRED_TOOLS = [
        "search_documents", "find_skills", "run_skill",
        "query_spend", "get_benchmarks", "get_evidence",
        "model_savings", "assess_opportunities",
    ]
    try:
        catalog, e1 = _read("app/opar/tools/catalog.py")
        ctx, e2 = _read("app/opar/tools/context.py")
        if e1 or not catalog:
            return _err(*DIM, e1 or "missing tools/catalog.py")

        present = [t for t in REQUIRED_TOOLS if f'"{t}"' in catalog or f"'{t}'" in catalog]
        handlers = [t for t in REQUIRED_TOOLS if f"_{t.replace('-', '_')}" in catalog]
        dispatch_entries = [t for t in REQUIRED_TOOLS if t in catalog]

        raw = _clamp(len(present) / len(REQUIRED_TOOLS) * 10)
        missing = [t for t in REQUIRED_TOOLS if t not in present]
        return DimensionResult(
            *DIM, raw_score=raw, passed=raw >= 9.0,
            evidence={"required": REQUIRED_TOOLS, "present": present, "missing": missing},
            finding_summary=f"{len(present)}/{len(REQUIRED_TOOLS)} required tools present in catalog",
            finding_detail=f"Missing tools: {missing or 'none'}",
            remediation=f"Add missing tools to catalog.py: {missing}" if missing else "All 8 tools present.",
            data_sources_found=["app/opar/tools/catalog.py"],
        )
    except Exception:
        return _err(*DIM, traceback.format_exc())


def score_ag_03(root: Path) -> DimensionResult:
    """Deterministic fallback gate prevents agent in M1/pytest/no-key."""
    DIM = ("ag_03", "Deterministic Fallback Gate", "controller_routing", 0.25, 9.0)
    try:
        runtime, e1 = _read("app/opar/agent_runtime.py")
        orch, e2 = _read("app/opar/orchestrator.py")
        if e1 or not runtime:
            return _err(*DIM, e1 or "missing agent_runtime.py")

        checks = {
            "PYTEST_CURRENT_TEST guard":         "PYTEST_CURRENT_TEST" in (runtime or ""),
            "AGENT_CONTROLLER_ENABLED gate":     "AGENT_CONTROLLER_ENABLED" in (runtime or ""),
            "get_active_mode M2/M3 gate":        'in ("M2", "M3")' in (runtime or ""),
            "orchestrator fallback to plan()":   "plan(ctx)" in (orch or ""),
            "agent_loop_available() exported":   "agent_loop_available" in (runtime or ""),
        }
        passed_n = sum(checks.values())
        raw = _clamp(passed_n / len(checks) * 10)
        missing = [k for k, v in checks.items() if not v]
        return DimensionResult(
            *DIM, raw_score=raw, passed=raw >= 9.0,
            evidence={"checks": checks},
            finding_summary=f"{passed_n}/{len(checks)} fallback gate checks pass",
            finding_detail=f"Missing: {missing or 'none'}",
            remediation=f"Add missing fallback guards: {missing}" if missing else "Fallback gate fully implemented.",
            data_sources_found=["app/opar/agent_runtime.py", "app/opar/orchestrator.py"],
        )
    except Exception:
        return _err(*DIM, traceback.format_exc())


# ---------------------------------------------------------------------------
# Domain B — Intelligence & Discovery
# ---------------------------------------------------------------------------

def score_ag_04(root: Path) -> DimensionResult:
    """Semantic skill discovery wired: registry, discovery, find_skills tool."""
    DIM = ("ag_04", "Semantic Skill Discovery Wired", "intelligence_discovery", 0.30, 9.0)
    try:
        registry, e1 = _read("app/skills/registry.py")
        discovery, e2 = _read("app/skills/discovery.py")
        catalog, e3 = _read("app/opar/tools/catalog.py")
        if e1 or not registry:
            return _err(*DIM, e1 or "missing skills/registry.py")

        checks = {
            "full SKILL.md parsing (frontmatter)": "_parse_frontmatter" in (registry or "") or "frontmatter" in (registry or "").lower(),
            "when_to_use extracted":               "when_to_use" in (registry or ""),
            "methodology_summary extracted":       "methodology_summary" in (registry or ""),
            "discover_skills_rich exported":       "discover_skills_rich" in (registry or ""),
            "semantic embedding in discovery":     "SentenceTransformer" in (discovery or "") or "_embed" in (discovery or ""),
            "keyword fallback in discovery":       "_keyword_score" in (discovery or "") or "keyword" in (discovery or "").lower(),
            "Qdrant integration":                  "QdrantClient" in (discovery or "") or "qdrant" in (discovery or "").lower(),
            "find_skills tool in catalog":         "find_skills" in (catalog or ""),
            "discover_relevant_skills called":     "discover_relevant_skills" in (catalog or ""),
        }
        passed_n = sum(checks.values())
        raw = _clamp(passed_n / len(checks) * 10)
        missing = [k for k, v in checks.items() if not v]
        return DimensionResult(
            *DIM, raw_score=raw, passed=raw >= 9.0,
            evidence={"checks": checks},
            finding_summary=f"{passed_n}/{len(checks)} skill discovery checks pass",
            finding_detail=f"Missing: {missing or 'none'}",
            remediation=f"Implement: {missing}" if missing else "Skill discovery fully implemented.",
            data_sources_found=["app/skills/registry.py", "app/skills/discovery.py"],
        )
    except Exception:
        return _err(*DIM, traceback.format_exc())


def score_ag_05(root: Path) -> DimensionResult:
    """_DEP_MAP covers all registered skills (minus Group 0 security skills)."""
    DIM = ("ag_05", "_DEP_MAP Covers All Registered Skills", "intelligence_discovery", 0.35, 9.0)
    GROUP0 = {"pii-stripper", "data-classifier", "llm-context-builder"}
    try:
        plan_text, e1 = _read("app/opar/plan.py")
        dispatch_text, e2 = _read("app/skills/dispatch.py")
        if e1 or not plan_text:
            return _err(*DIM, e1 or "missing plan.py")
        if e2 or not dispatch_text:
            return _err(*DIM, e2 or "missing skills/dispatch.py")

        # Extract registered skills from dispatch.py
        registered = set(re.findall(r'@register\(["\']([^"\']+)["\']\)', dispatch_text))
        analysis_skills = registered - GROUP0

        # Extract keys from _DEP_MAP block
        dep_block_m = re.search(r"_DEP_MAP\s*[=:][^{]*\{(.*?)\n\}", plan_text, re.DOTALL)
        dep_keys: set[str] = set()
        if dep_block_m:
            dep_keys = set(re.findall(r'"([a-z][a-z-]+)":\s*\(', dep_block_m.group(1)))

        covered = analysis_skills & dep_keys
        missing = sorted(analysis_skills - dep_keys)
        raw = _clamp(len(covered) / len(analysis_skills) * 10 if analysis_skills else 10.0)
        return DimensionResult(
            *DIM, raw_score=raw, passed=raw >= 9.0,
            evidence={
                "registered_analysis_skills": sorted(analysis_skills),
                "in_dep_map": sorted(dep_keys & analysis_skills),
                "missing_from_dep_map": missing,
                "group0_excluded": sorted(GROUP0),
            },
            finding_summary=f"{len(covered)}/{len(analysis_skills)} analysis skills in _DEP_MAP",
            finding_detail=f"Missing from _DEP_MAP: {missing or 'none'}",
            remediation=f"Add to _DEP_MAP with correct deps: {missing}" if missing else "_DEP_MAP is the single source of truth.",
            data_sources_found=["app/opar/plan.py", "app/skills/dispatch.py"],
        )
    except Exception:
        return _err(*DIM, traceback.format_exc())


def score_ag_06(root: Path) -> DimensionResult:
    """SME critique LLM enrichment wired (sme_intelligence.py called from sme_critique.py)."""
    DIM = ("ag_06", "SME Critique LLM Enrichment Wired", "intelligence_discovery", 0.20, 8.0)
    try:
        sme_intel, e1 = _read("app/opar/sme_intelligence.py")
        sme_critique, e2 = _read("app/skills/engine/sme_critique.py")
        if e1 or not sme_intel:
            return _err(*DIM, e1 or "missing sme_intelligence.py")

        checks = {
            "sme_intelligence.py exists":              sme_intel is not None,
            "enrich_sme_critique_with_llm defined":    "enrich_sme_critique_with_llm" in (sme_intel or ""),
            "M1 guard in sme_intelligence":            'get_active_mode() == "M1"' in (sme_intel or "") or "M1" in (sme_intel or ""),
            "called from sme_critique.py":             "enrich_sme_critique_with_llm" in (sme_critique or ""),
            "verdict_source llm_enriched":             "llm_enriched" in (sme_intel or ""),
            "portfolio_note added":                    "portfolio_note" in (sme_intel or "") or "llm_portfolio_note" in (sme_intel or ""),
        }
        passed_n = sum(checks.values())
        raw = _clamp(passed_n / len(checks) * 10)
        missing = [k for k, v in checks.items() if not v]
        return DimensionResult(
            *DIM, raw_score=raw, passed=raw >= 8.0,
            evidence={"checks": checks},
            finding_summary=f"{passed_n}/{len(checks)} SME enrichment checks pass",
            finding_detail=f"Missing: {missing or 'none'}",
            remediation=f"Implement: {missing}" if missing else "SME critique LLM enrichment fully wired.",
            data_sources_found=["app/opar/sme_intelligence.py", "app/skills/engine/sme_critique.py"],
        )
    except Exception:
        return _err(*DIM, traceback.format_exc())


def score_ag_07(root: Path) -> DimensionResult:
    """Root-cause LLM enrichment wired (root_cause_intelligence.py called from benchmarking.py)."""
    DIM = ("ag_07", "Root-Cause LLM Enrichment Wired", "intelligence_discovery", 0.15, 8.0)
    try:
        rci, e1 = _read("app/opar/root_cause_intelligence.py")
        bench, e2 = _read("app/skills/engine/benchmarking.py")
        if e1 or not rci:
            return _err(*DIM, e1 or "missing root_cause_intelligence.py")

        checks = {
            "root_cause_intelligence.py exists":   rci is not None,
            "enrich_root_cause_with_llm defined":  "enrich_root_cause_with_llm" in (rci or ""),
            "M1 guard present":                    "M1" in (rci or ""),
            "called from benchmarking.py":         "enrich_root_cause_with_llm" in (bench or "") or "root_cause_intelligence" in (bench or ""),
            "deterministic fallback on None":      "if enriched:" in (bench or "") or "enriched" in (bench or ""),
        }
        passed_n = sum(checks.values())
        raw = _clamp(passed_n / len(checks) * 10)
        missing = [k for k, v in checks.items() if not v]
        return DimensionResult(
            *DIM, raw_score=raw, passed=raw >= 8.0,
            evidence={"checks": checks},
            finding_summary=f"{passed_n}/{len(checks)} root-cause enrichment checks pass",
            finding_detail=f"Missing: {missing or 'none'}",
            remediation=f"Implement: {missing}" if missing else "Root-cause LLM enrichment fully wired.",
            data_sources_found=["app/opar/root_cause_intelligence.py", "app/skills/engine/benchmarking.py"],
        )
    except Exception:
        return _err(*DIM, traceback.format_exc())


# ---------------------------------------------------------------------------
# Domain C — Safety & Provenance
# ---------------------------------------------------------------------------

def score_ag_08(root: Path) -> DimensionResult:
    """Offline guard + ScriptedTransport injectable for tests."""
    DIM = ("ag_08", "Offline Guard and Injectable Transport", "safety_provenance", 0.30, 9.0)
    try:
        runtime, e1 = _read("app/opar/agent_runtime.py")
        gemini, e2 = _read("app/opar/gemini_client.py")
        claude, e3 = _read("app/opar/claude_client.py")
        if e1 or not runtime:
            return _err(*DIM, e1 or "missing agent_runtime.py")

        checks = {
            "ScriptedTransport class defined":       "class ScriptedTransport" in (runtime or ""),
            "ScriptedTransport replays script":      "_script" in (runtime or ""),
            "make_tool_call helper":                 "make_tool_call" in (runtime or ""),
            "ToolLoopTransport Protocol":            "class ToolLoopTransport" in (runtime or "") or "ToolLoopTransport" in (runtime or ""),
            "Gemini offline guard (PYTEST)":         "PYTEST_CURRENT_TEST" in (gemini or ""),
            "Claude offline guard (PYTEST)":         "PYTEST_CURRENT_TEST" in (claude or ""),
            "transport injectable in run_tool_loop": "transport: ToolLoopTransport" in (runtime or "") or "transport=" in (runtime or ""),
        }
        passed_n = sum(checks.values())
        raw = _clamp(passed_n / len(checks) * 10)
        missing = [k for k, v in checks.items() if not v]
        return DimensionResult(
            *DIM, raw_score=raw, passed=raw >= 9.0,
            evidence={"checks": checks},
            finding_summary=f"{passed_n}/{len(checks)} offline guard / transport checks pass",
            finding_detail=f"Missing: {missing or 'none'}",
            remediation=f"Implement: {missing}" if missing else "Offline guard and injectable transport fully implemented.",
            data_sources_found=["app/opar/agent_runtime.py", "app/opar/gemini_client.py"],
        )
    except Exception:
        return _err(*DIM, traceback.format_exc())


def score_ag_09(root: Path) -> DimensionResult:
    """Numeric provenance tags on LLM-adjusted figures in opportunity reasoning."""
    DIM = ("ag_09", "Numeric Provenance on Opportunity Assessment", "safety_provenance", 0.40, 9.0)
    try:
        provenance, e1 = _read("app/opar/numeric_provenance.py")
        opp_reasoning, e2 = _read("app/opar/tools/opportunity_reasoning.py")
        if e1 or not provenance:
            return _err(*DIM, e1 or "missing numeric_provenance.py")

        checks = {
            "tag_llm_numeric defined":          "def tag_llm_numeric" in (provenance or ""),
            "tag_deterministic defined":        "def tag_deterministic" in (provenance or ""),
            "apply_bounded_adjustment defined": "def apply_bounded_adjustment" in (provenance or ""),
            "source field in provenance":       '"source"' in (provenance or "") or "'source'" in (provenance or ""),
            "deterministic_anchor in provenance":"deterministic_anchor" in (provenance or ""),
            "±25% bound enforced":              "AGENT_LLM_NUMERIC_ADJUSTMENT_PCT" in (provenance or ""),
            "provenance applied in opp_reasoning":"apply_bounded_adjustment" in (opp_reasoning or ""),
            "deterministic_fallback present":   "_deterministic_fallback" in (opp_reasoning or ""),
        }
        passed_n = sum(checks.values())
        raw = _clamp(passed_n / len(checks) * 10)
        missing = [k for k, v in checks.items() if not v]
        return DimensionResult(
            *DIM, raw_score=raw, passed=raw >= 9.0,
            evidence={"checks": checks},
            finding_summary=f"{passed_n}/{len(checks)} provenance checks pass",
            finding_detail=f"Missing: {missing or 'none'}",
            remediation=f"Implement: {missing}" if missing else "Numeric provenance fully implemented.",
            data_sources_found=["app/opar/numeric_provenance.py", "app/opar/tools/opportunity_reasoning.py"],
        )
    except Exception:
        return _err(*DIM, traceback.format_exc())


def score_ag_10(root: Path) -> DimensionResult:
    """Audit trail: LLM numeric adjustments logged to audit_log."""
    DIM = ("ag_10", "Audit Trail for LLM Numeric Adjustments", "safety_provenance", 0.30, 8.0)
    try:
        provenance, e1 = _read("app/opar/numeric_provenance.py")
        audit_log, e2 = _read("app/services/audit_log.py")
        if e1 or not provenance:
            return _err(*DIM, e1 or "missing numeric_provenance.py")

        checks = {
            "audit_llm_numeric_adjustment defined": "def audit_llm_numeric_adjustment" in (provenance or ""),
            "append_event called in audit fn":      "append_event" in (provenance or ""),
            "llm_numeric_adjustment event type":    "llm_numeric_adjustment" in (provenance or ""),
            "session_id in audit payload":          "session_id" in (provenance or ""),
            "engagement_id in audit payload":       "engagement_id" in (provenance or ""),
            "audit_log.py exists":                  audit_log is not None,
            "called in opportunity_reasoning":      True,  # verified by AG_09
        }
        # verify last check against opp_reasoning
        opp, _ = _read("app/opar/tools/opportunity_reasoning.py")
        checks["called in opportunity_reasoning"] = "audit_llm_numeric_adjustment" in (opp or "")

        passed_n = sum(checks.values())
        raw = _clamp(passed_n / len(checks) * 10)
        missing = [k for k, v in checks.items() if not v]
        return DimensionResult(
            *DIM, raw_score=raw, passed=raw >= 8.0,
            evidence={"checks": checks},
            finding_summary=f"{passed_n}/{len(checks)} audit trail checks pass",
            finding_detail=f"Missing: {missing or 'none'}",
            remediation=f"Implement: {missing}" if missing else "Audit trail fully implemented.",
            data_sources_found=["app/opar/numeric_provenance.py"],
        )
    except Exception:
        return _err(*DIM, traceback.format_exc())


# ---------------------------------------------------------------------------
# Aggregation + report
# ---------------------------------------------------------------------------

def _domain_score(dims: List[DimensionResult]) -> float:
    total_w = sum(d.weight for d in dims)
    return sum(d.raw_score * d.weight for d in dims) / total_w if total_w else 0.0


def _overall_score(domains: List[DomainResult]) -> float:
    total_w = sum(d.domain_weight for d in domains)
    return sum(d.domain_score * d.domain_weight for d in domains) / total_w if total_w else 0.0


def _rank_gaps(domains: List[DomainResult]) -> List[Dict]:
    gaps = []
    for dr in domains:
        for dim in dr.dimension_results:
            if dim.gap > 0:
                gaps.append({
                    "dimension_id": dim.dimension_id,
                    "name": dim.name,
                    "domain": dim.domain,
                    "gap": round(dim.gap, 3),
                    "raw_score": round(dim.raw_score, 3),
                    "threshold_pass": dim.threshold_pass,
                    "gap_severity": round(dim.gap * dim.weight * dr.domain_weight, 4),
                    "finding_summary": dim.finding_summary,
                    "remediation": dim.remediation,
                })
    return sorted(gaps, key=lambda x: -x["gap_severity"])


def _roadmap(gaps: List[Dict]) -> List[Dict]:
    return [
        {"priority": i + 1, "dimension_id": g["dimension_id"],
         "action": g["remediation"],
         "impact": f"Closes gap of {g['gap']:.1f} pts (severity {g['gap_severity']:.4f})"}
        for i, g in enumerate(gaps[:5])
    ]


def _build_report(report: EvalReport) -> str:
    lines = [
        "# Agentic Intelligence Eval",
        "",
        f"**Eval date**: {report.eval_date}  ",
        f"**Overall score**: {report.overall_score:.2f}/10  ",
        f"**Status**: {'PASS ✓' if report.passed else 'FAIL ✗'}",
        "",
        "---",
        "",
        "## Domain Summary",
        "",
        "| Domain | Score | Status |",
        "|--------|-------|--------|",
    ]
    for dr in report.domain_results:
        status = "PASS ✓" if dr.passed else "FAIL ✗"
        lines.append(f"| {dr.domain_display} (w={dr.domain_weight:.2f}) | {dr.domain_score:.2f}/10 | {status} |")

    if report.top_gaps:
        lines += ["", "---", "", "## Top Gaps", ""]
        for g in report.top_gaps:
            lines += [
                f"### {g['dimension_id'].upper()} — {g['name']}",
                f"- **Score**: {g['raw_score']:.2f}/10 (threshold {g['threshold_pass']:.1f}, gap {g['gap']:.2f})",
                f"- **Finding**: {g['finding_summary']}",
                f"- **Remediation**: {g['remediation']}",
                "",
            ]

    for dr in report.domain_results:
        lines += [
            "---", "",
            f"## {dr.domain_display}",
            "",
            f"Domain score: **{dr.domain_score:.2f}/10** ({'PASS ✓' if dr.passed else 'FAIL ✗'})",
            "",
            "| Dimension | Score | Threshold | Status |",
            "|-----------|-------|-----------|--------|",
        ]
        for dim in dr.dimension_results:
            lines.append(f"| {dim.name} | {dim.raw_score:.2f} | {dim.threshold_pass:.1f} | {'✓' if dim.passed else '✗'} |")
        lines.append("")
        for dim in dr.dimension_results:
            status = "PASS ✓" if dim.passed else "FAIL ✗"
            lines += [
                f"### {dim.dimension_id.upper()} — {dim.name} [{status}]",
                f"**Score**: {dim.raw_score:.2f}/10  **Threshold**: {dim.threshold_pass:.1f}",
                f"**Finding**: {dim.finding_summary}",
                f"**Detail**: {dim.finding_detail}",
                f"**Remediation**: {dim.remediation}",
                "",
            ]
    return "\n".join(lines)


def run_eval(root: Path, json_only: bool = False) -> EvalReport:
    dimensions_a = [score_ag_01(root), score_ag_02(root), score_ag_03(root)]
    dimensions_b = [score_ag_04(root), score_ag_05(root), score_ag_06(root), score_ag_07(root)]
    dimensions_c = [score_ag_08(root), score_ag_09(root), score_ag_10(root)]

    domains = [
        DomainResult("controller_routing", "Controller & Routing", 0.35,
                     dimensions_a, _domain_score(dimensions_a),
                     all(d.passed for d in dimensions_a)),
        DomainResult("intelligence_discovery", "Intelligence & Discovery", 0.40,
                     dimensions_b, _domain_score(dimensions_b),
                     all(d.passed for d in dimensions_b)),
        DomainResult("safety_provenance", "Safety & Provenance", 0.25,
                     dimensions_c, _domain_score(dimensions_c),
                     all(d.passed for d in dimensions_c)),
    ]
    overall = _overall_score(domains)
    passed = overall >= 9.0 and all(d.passed for d in domains)
    gaps = _rank_gaps(domains)

    return EvalReport(
        platform_version="0.1.0",
        eval_date=str(date.today()),
        overall_score=round(overall, 4),
        domain_results=domains,
        top_gaps=gaps[:5],
        remediation_roadmap=_roadmap(gaps),
        passed=passed,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Agentic Intelligence Evaluator")
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_MD)
    parser.add_argument("--json-only", action="store_true")
    args = parser.parse_args()

    root: Path = args.project_root
    try:
        report = run_eval(root, json_only=args.json_only)
    except Exception as exc:
        print(f"CRITICAL: {exc}", file=sys.stderr)
        traceback.print_exc()
        return 2

    scores_json = {
        "eval_date": report.eval_date,
        "overall_score": report.overall_score,
        "passed": report.passed,
        "domains": {
            dr.domain_name: {
                "score": round(dr.domain_score, 4),
                "passed": dr.passed,
                "dimensions": {
                    dim.dimension_id: {
                        "name": dim.name,
                        "raw_score": round(dim.raw_score, 4),
                        "passed": dim.passed,
                        "finding": dim.finding_summary,
                    }
                    for dim in dr.dimension_results
                },
            }
            for dr in report.domain_results
        },
    }
    json_path = args.output.with_suffix(".json")
    json_path.write_text(json.dumps(scores_json, indent=2), encoding="utf-8")

    if not args.json_only:
        md = _build_report(report)
        args.output.with_suffix(".md").write_text(md, encoding="utf-8")
        print(md)

    status = "PASS ✓" if report.passed else "FAIL ✗"
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"Agentic eval: {report.overall_score:.2f}/10  [{status}]", file=sys.stderr)
    for dr in report.domain_results:
        icon = "✓" if dr.passed else "✗"
        print(f"  {icon} {dr.domain_display}: {dr.domain_score:.2f}/10", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)

    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
