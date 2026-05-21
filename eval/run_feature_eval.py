#!/usr/bin/env python3
"""
eval/run_feature_eval.py — OpEx Platform Feature Completeness Evaluator

Static analysis of skill wiring, frontend-backend API connectivity, OPAR loop
completeness, and infrastructure readiness. Companion to eval/run_eval.py.

Usage:
    python eval/run_feature_eval.py [--project-root PATH] [--output PATH] [--json-only]

Exit codes:
    0 — all domains pass their weighted threshold
    1 — one or more domains fail
    2 — critical file not found or unrecoverable error
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


# ---------------------------------------------------------------------------
# Data models (mirrored from run_eval.py)
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
    data_sources_missing: List[str] = field(default_factory=list)

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
# File loaders (mirrored from run_eval.py)
# ---------------------------------------------------------------------------

def load_json(project_root: Path, relative_path: str) -> Tuple[Optional[Any], Optional[str]]:
    p = project_root / relative_path
    if not p.exists():
        return None, f"file_not_found: {relative_path}"
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f), None
    except json.JSONDecodeError as e:
        return None, f"json_parse_error: {e}"


def read_text(project_root: Path, relative_path: str) -> Tuple[Optional[str], Optional[str]]:
    p = project_root / relative_path
    if not p.exists():
        return None, f"file_not_found: {relative_path}"
    return p.read_text(encoding="utf-8", errors="ignore"), None


def _clamp(v: float) -> float:
    return max(0.0, min(10.0, v))


def _error_result(dim_id: str, name: str, domain: str, weight: float,
                  threshold: float, exc: str) -> DimensionResult:
    return DimensionResult(
        dimension_id=dim_id, name=name, domain=domain, weight=weight,
        raw_score=0.0, threshold_pass=threshold, passed=False,
        evidence={"error": exc},
        finding_summary=f"EVAL_ERROR: {exc[:120]}",
        finding_detail=exc,
        remediation="Fix the eval error before interpreting this dimension's score.",
    )


# ---------------------------------------------------------------------------
# Shared helpers — skill / route / intent extraction
# ---------------------------------------------------------------------------

#: Skill dirs under skills/ that are NOT individual skills
_NON_SKILL_DIRS = {"sector-packs", "references"}

#: Output contract class names keyed by registered skill name.
#: None means no dedicated Output class expected (skill uses inline dict).
_SKILL_CONTRACT_MAP: Dict[str, Optional[str]] = {
    "spend-profiler":            "SpendProfilerOutput",
    "document-contextualizer":   "DocumentContextOutput",
    "bva-analyzer":              "BvAAnalyzerOutput",
    "temporal-analyzer":         "TemporalAnalyzerOutput",
    "payment-terms-optimizer":   "PaymentTermsOptimizerOutput",
    "heuristic-analyzer":        "HeuristicAnalyzerOutput",
    "internal-benchmarker":      "InternalBenchmarkerOutput",
    "peer-benchmarker":          "PeerBenchmarkerOutput",
    "root-cause-analyzer":       None,
    "savings-modeler":           None,
    "value-bridge-calculator":   "ValueBridgeOutput",
    "data-validator":            None,
    "chart-builder":             None,
    "business-case-builder":     None,
    "analysis-synthesizer":      "AnalysisSynthesizerOutput",
    "executive-communication":   "ExecutiveCommunicationOutput",
}

#: Backend feature groups to check for frontend exposure.
#: Value is a path substring to search for in frontend API calls.
_BACKEND_FEATURE_GROUPS: Dict[str, str] = {
    "benchmarks_api":           "/api/v1/benchmarks",
    "sector_packs":             "/api/v1/sector-packs",
    "initiative_milestones":    "milestones",
    "initiative_actuals":       "actuals",
    "enterprise_consolidation": "/api/v1/consolidate",
    "cost_to_serve":            "/api/v1/cost-to-serve",
    "output_board_cfo":         "/api/v1/business-case",
    "incremental_analyze":      "incremental",
}

#: FP&A endpoints to check in both backend and frontend.
_FPNA_ENDPOINTS = [
    ("trends",        r"/api/v1/trends",        r"/api/v1/trends"),
    ("bva",           r"/api/v1/bva",           r"/api/v1/bva"),
    ("payment-terms", r"/api/v1/payment-terms", r"/api/v1/payment-terms"),
]


def _extract_registered_skills(dispatch_text: str) -> List[str]:
    return re.findall(r'@register\(["\']([^"\']+)["\']\)', dispatch_text)


def _extract_intent_values(models_text: str) -> List[str]:
    match = re.search(
        r'class IntentClass\(.*?\):(.*?)(?=\nclass |\Z)',
        models_text, re.DOTALL,
    )
    if not match:
        return []
    block = match.group(1)
    return re.findall(r'=\s*["\']([a-z_]+)["\']', block)


def _extract_api_calls_from_text(content: str) -> List[str]:
    """Return normalized /api/... paths found in TypeScript source."""
    # Template-literal and quoted string arguments to api* functions
    func_pat = r'(?:apiGet|apiPost|apiPut|apiUpload)\s*(?:<[^>]*>)?\s*\(\s*[`\'"]([^`\'"]+)[`\'"]'
    # Static href links
    href_pat = r'href=["\']([/]api/[^"\'>\s]+)["\']'
    raw = re.findall(func_pat, content) + re.findall(href_pat, content)
    result = []
    for p in raw:
        p = re.sub(r'\$\{[^}]+\}', '{param}', p)   # normalize template params
        p = p.split('?')[0]                          # strip query strings
        if p.startswith('/api/'):
            p = re.sub(r'/[0-9a-f-]{36}', '/{param}', p)    # UUID path params
            p = re.sub(r'\{[^}]+\}', '{param}', p)           # other path params
            result.append(p)
    return result


def _collect_frontend_api_calls(root: Path) -> List[str]:
    calls: List[str] = []
    for tsx in list((root / "frontend" / "src").rglob("*.tsx")) + \
               list((root / "frontend" / "src").rglob("*.ts")):
        try:
            calls.extend(_extract_api_calls_from_text(tsx.read_text(encoding="utf-8", errors="ignore")))
        except Exception:
            pass
    return calls


def _collect_backend_routes(root: Path) -> List[str]:
    routes: List[str] = []
    routers_dir = root / "app" / "routers"
    files = list(routers_dir.glob("*.py")) if routers_dir.exists() else []
    main_py = root / "app" / "main.py"
    if main_py.exists():
        files.append(main_py)
    for py_file in files:
        text = py_file.read_text(encoding="utf-8", errors="ignore")
        # @router.get("/path") or @app.get("/path")
        found = re.findall(r'@(?:router|app)\.\w+\(\s*["\']([^"\']+)["\']', text)
        for path in found:
            normalized = re.sub(r'\{[^}]+\}', '{param}', path)
            routes.append(normalized)
    return routes


def _normalize_for_match(path: str) -> str:
    """Normalize path for fuzzy matching: strip trailing slash, lowercase."""
    return path.rstrip('/').lower()


def _frontend_resolves_to_backend(fe_path: str, backend_routes: List[str]) -> bool:
    """Return True if fe_path matches any backend route (exact or after normalization)."""
    fe_norm = _normalize_for_match(fe_path)
    # Build regex patterns from backend routes, replacing {param} with [^/]+
    for route in backend_routes:
        r_norm = _normalize_for_match(route)
        pattern = re.escape(r_norm).replace(re.escape('{param}'), '[^/]+')
        if re.fullmatch(pattern, fe_norm):
            return True
        # Also try: frontend may use /api/ prefix while backend route is /api/v1/
        # by stripping the /v1 segment from backend and matching again
        r_unver = r_norm.replace('/v1/', '/', 1)
        pattern2 = re.escape(r_unver).replace(re.escape('{param}'), '[^/]+')
        if re.fullmatch(pattern2, fe_norm):
            return True
    return False


# ---------------------------------------------------------------------------
# Skill Pipeline Completeness — sp_01 … sp_04
# ---------------------------------------------------------------------------

def score_sp_01(root: Path) -> DimensionResult:
    DIM = ("sp_01", "Skill Directory-to-Dispatch Parity", "skill_pipeline", 0.30, 9.0)
    try:
        dispatch_text, err = read_text(root, "app/skills/dispatch.py")
        if err:
            return _error_result(*DIM, err)

        registered = set(_extract_registered_skills(dispatch_text))

        skills_root = root / "skills"
        skill_dirs: List[str] = []
        for d in sorted(skills_root.iterdir()):
            if not d.is_dir():
                continue
            if d.name in _NON_SKILL_DIRS or d.name.startswith('_'):
                continue
            if (d / "SKILL.md").exists():
                skill_dirs.append(d.name)

        total = len(skill_dirs)
        matched = [s for s in skill_dirs if s in registered]
        unregistered = [s for s in skill_dirs if s not in registered]

        raw = _clamp(len(matched) / total * 10 if total else 0.0)
        passed = raw >= 9.0

        evidence = {
            "total_skill_dirs_with_SKILL_md": total,
            "registered_count": len(matched),
            "registered": sorted(matched),
            "unregistered": sorted(unregistered),
        }
        summary = (
            f"{len(matched)}/{total} skills registered in dispatch.py"
            + (f"; unregistered: {unregistered}" if unregistered else "")
        )
        detail = (
            f"Found {total} skills/ dirs with SKILL.md. "
            f"{len(matched)} are registered via @register() in dispatch.py. "
            f"Unregistered (dead code): {sorted(unregistered) or 'none'}."
        )
        remediation = (
            f"Add @register() handlers in app/skills/dispatch.py for: {sorted(unregistered)}. "
            "Each handler should call the corresponding engine function. "
            "Consider adding a CI check that asserts len(skill_dirs) == len(registered_skills())."
        ) if unregistered else "All skills registered. Add CI parity check to prevent future drift."

        return DimensionResult(*DIM, raw_score=raw, passed=passed,
                               evidence=evidence, finding_summary=summary,
                               finding_detail=detail, remediation=remediation,
                               data_sources_found=["skills/*/SKILL.md", "app/skills/dispatch.py"])
    except Exception:
        return _error_result(*DIM, traceback.format_exc())


def score_sp_02(root: Path) -> DimensionResult:
    DIM = ("sp_02", "Dispatch Handler Implementation Depth", "skill_pipeline", 0.20, 8.0)
    try:
        dispatch_text, err = read_text(root, "app/skills/dispatch.py")
        if err:
            return _error_result(*DIM, err)

        registered = _extract_registered_skills(dispatch_text)
        if not registered:
            return _error_result(*DIM, "no @register() decorators found in dispatch.py")

        # Split text into per-handler chunks using @register as delimiter
        chunks = re.split(r'@register\(["\'][^"\']+["\']\)', dispatch_text)
        # chunks[0] is preamble; chunks[1..n] correspond to each registered skill in order
        handler_chunks = chunks[1:]  # one per registered skill

        implemented: List[str] = []
        stubs: List[str] = []

        for skill, chunk in zip(registered, handler_chunks):
            # Count non-blank, non-comment lines in the chunk
            lines = [ln for ln in chunk.splitlines()
                     if ln.strip() and not ln.strip().startswith('#')]
            if len(lines) >= 5:
                implemented.append(skill)
            else:
                stubs.append(skill)

        total = len(registered)
        raw = _clamp(len(implemented) / total * 10 if total else 0.0)
        passed = raw >= 8.0

        evidence = {
            "total_registered": total,
            "implemented_count": len(implemented),
            "stubs": stubs,
        }
        summary = f"{len(implemented)}/{total} handlers have ≥5 non-blank lines (implemented)"
        detail = (
            f"Checked {total} @register() handlers. "
            f"{len(implemented)} have ≥5 non-blank lines indicating real logic. "
            f"Potential stubs: {stubs or 'none'}."
        )
        remediation = (
            f"Flesh out stub handlers for: {stubs}."
        ) if stubs else "All handlers appear substantively implemented."

        return DimensionResult(*DIM, raw_score=raw, passed=passed,
                               evidence=evidence, finding_summary=summary,
                               finding_detail=detail, remediation=remediation,
                               data_sources_found=["app/skills/dispatch.py"])
    except Exception:
        return _error_result(*DIM, traceback.format_exc())


def score_sp_03(root: Path) -> DimensionResult:
    DIM = ("sp_03", "Skill Output Contract Coverage", "skill_pipeline", 0.25, 7.0)
    try:
        dispatch_text, err = read_text(root, "app/skills/dispatch.py")
        if err:
            return _error_result(*DIM, err)
        contracts_text, err2 = read_text(root, "app/skills/contracts.py")
        if err2:
            return _error_result(*DIM, err2)

        registered = _extract_registered_skills(dispatch_text)
        with_contract: List[str] = []
        without_contract: List[str] = []
        no_contract_expected: List[str] = []

        for skill in registered:
            expected_class = _SKILL_CONTRACT_MAP.get(skill)
            if expected_class is None:
                no_contract_expected.append(skill)
                with_contract.append(skill)  # count as covered (intentionally no dedicated class)
                continue
            if re.search(r'\bclass\s+' + re.escape(expected_class) + r'\b', contracts_text):
                with_contract.append(skill)
            else:
                without_contract.append(skill)

        total = len(registered)
        raw = _clamp(len(with_contract) / total * 10 if total else 0.0)
        passed = raw >= 7.0

        evidence = {
            "total_registered": total,
            "with_contract_or_intentionally_none": len(with_contract),
            "missing_contract_class": without_contract,
            "intentionally_no_dedicated_class": no_contract_expected,
            "contract_map_used": {k: v for k, v in _SKILL_CONTRACT_MAP.items() if v},
        }
        summary = (
            f"{len(with_contract)}/{total} registered skills have output contracts "
            f"(or intentionally use inline dict)"
        )
        detail = (
            f"Checked contracts.py for Output class per registered skill. "
            f"Skills missing a dedicated contract class: {without_contract or 'none'}. "
            f"Skills intentionally using inline dict (no dedicated class): {no_contract_expected or 'none'}."
        )
        remediation = (
            f"Add Output dataclasses in contracts.py for: {without_contract}. "
            "This enables the Act phase to validate LLM outputs structurally."
        ) if without_contract else "Contract coverage adequate. Consider adding classes for inline-dict skills."

        return DimensionResult(*DIM, raw_score=raw, passed=passed,
                               evidence=evidence, finding_summary=summary,
                               finding_detail=detail, remediation=remediation,
                               data_sources_found=["app/skills/dispatch.py", "app/skills/contracts.py"])
    except Exception:
        return _error_result(*DIM, traceback.format_exc())


def score_sp_04(root: Path) -> DimensionResult:
    DIM = ("sp_04", "OPAR Intent-to-Plan Mapping Coverage", "skill_pipeline", 0.25, 8.0)
    try:
        models_text, err = read_text(root, "app/opar/models.py")
        if err:
            return _error_result(*DIM, err)
        plan_text, err2 = read_text(root, "app/opar/plan.py")
        if err2:
            return _error_result(*DIM, err2)

        intents = _extract_intent_values(models_text)
        if not intents:
            return _error_result(*DIM, "could not extract IntentClass values from models.py")

        handled: List[str] = []
        unhandled: List[str] = []
        for intent in intents:
            # Search for the intent string literal anywhere in plan.py
            if re.search(r'["\']' + re.escape(intent) + r'["\']', plan_text):
                handled.append(intent)
            else:
                unhandled.append(intent)

        total = len(intents)
        raw = _clamp(len(handled) / total * 10 if total else 0.0)
        passed = raw >= 8.0

        evidence = {
            "total_intents": total,
            "handled_in_plan": len(handled),
            "unhandled": unhandled,
            "intents": intents,
        }
        summary = f"{len(handled)}/{total} IntentClass values handled in plan.py"
        detail = (
            f"Extracted {total} IntentClass values from models.py. "
            f"Searched plan.py for each as a string literal. "
            f"Unhandled (fall through to generic_qa): {unhandled or 'none'}."
        )
        remediation = (
            f"Add explicit plan branches in plan.py for: {unhandled}. "
            "Each unhandled intent silently degrades to generic Q&A output."
        ) if unhandled else "All intents handled in plan.py."

        return DimensionResult(*DIM, raw_score=raw, passed=passed,
                               evidence=evidence, finding_summary=summary,
                               finding_detail=detail, remediation=remediation,
                               data_sources_found=["app/opar/models.py", "app/opar/plan.py"])
    except Exception:
        return _error_result(*DIM, traceback.format_exc())


# ---------------------------------------------------------------------------
# Frontend-Backend API Connectivity — api_01 … api_04
# ---------------------------------------------------------------------------

def score_api_01(root: Path) -> DimensionResult:
    DIM = ("api_01", "Frontend Call Resolution Rate", "api_connectivity", 0.25, 9.0)
    try:
        frontend_src = root / "frontend" / "src"
        if not frontend_src.exists():
            return _error_result(*DIM, "frontend/src directory not found")

        all_calls = _collect_frontend_api_calls(root)
        unique_calls = list(dict.fromkeys(all_calls))  # deduplicate preserving order
        backend_routes = _collect_backend_routes(root)

        resolved: List[str] = []
        unresolved: List[str] = []
        for call in unique_calls:
            if _frontend_resolves_to_backend(call, backend_routes):
                resolved.append(call)
            else:
                unresolved.append(call)

        total = len(unique_calls)
        raw = _clamp(len(resolved) / total * 10 if total else 0.0)
        passed = raw >= 9.0

        evidence = {
            "total_unique_frontend_calls": total,
            "resolved_count": len(resolved),
            "unresolved": unresolved,
            "resolved": resolved,
        }
        summary = f"{len(resolved)}/{total} unique frontend API calls resolve to a backend route"
        detail = (
            f"Scanned all .tsx/.ts files under frontend/src for apiGet/apiPost/apiPut/apiUpload "
            f"calls and href=/api/... links. Found {total} unique paths. "
            f"Unresolved (would 404): {unresolved or 'none'}."
        )
        remediation = (
            f"These frontend calls have no matching backend route: {unresolved}. "
            "Either add the backend route or fix the frontend URL."
        ) if unresolved else "All frontend calls resolve. No broken links."

        return DimensionResult(*DIM, raw_score=raw, passed=passed,
                               evidence=evidence, finding_summary=summary,
                               finding_detail=detail, remediation=remediation,
                               data_sources_found=["frontend/src/**/*.tsx", "app/routers/*.py"])
    except Exception:
        return _error_result(*DIM, traceback.format_exc())


def score_api_02(root: Path) -> DimensionResult:
    DIM = ("api_02", "Backend Feature Frontend Exposure", "api_connectivity", 0.30, 6.0)
    try:
        all_calls = _collect_frontend_api_calls(root)
        frontend_call_text = "\n".join(all_calls)

        exposed: Dict[str, bool] = {}
        for group_name, path_substr in _BACKEND_FEATURE_GROUPS.items():
            exposed[group_name] = path_substr in frontend_call_text

        exposed_count = sum(1 for v in exposed.values() if v)
        total = len(_BACKEND_FEATURE_GROUPS)
        raw = _clamp(exposed_count / total * 10 if total else 0.0)
        passed = raw >= 6.0

        not_exposed = [g for g, v in exposed.items() if not v]
        evidence = {
            "total_feature_groups": total,
            "exposed_count": exposed_count,
            "exposure_detail": exposed,
            "not_exposed": not_exposed,
        }
        summary = f"{exposed_count}/{total} backend feature groups have at least one frontend page calling them"
        detail = (
            f"Checked {total} backend feature groups for at least one matching frontend API call. "
            f"Groups with NO frontend exposure: {not_exposed or 'none'}."
        )
        remediation = (
            "Build frontend pages or components for these backend features:\n"
            + "\n".join(f"  - {g}: {_BACKEND_FEATURE_GROUPS[g]}" for g in not_exposed)
        ) if not_exposed else "All backend feature groups have frontend coverage."

        return DimensionResult(*DIM, raw_score=raw, passed=passed,
                               evidence=evidence, finding_summary=summary,
                               finding_detail=detail, remediation=remediation,
                               data_sources_found=["frontend/src/pages/*.tsx", "app/routers/*.py"])
    except Exception:
        return _error_result(*DIM, traceback.format_exc())


def score_api_03(root: Path) -> DimensionResult:
    DIM = ("api_03", "API Version Consistency", "api_connectivity", 0.25, 6.0)
    try:
        all_calls = _collect_frontend_api_calls(root)
        if not all_calls:
            return _error_result(*DIM, "no frontend API calls found")

        unique_calls = list(dict.fromkeys(all_calls))
        v1_calls = [c for c in unique_calls if c.startswith("/api/v1/")]
        unversioned = [c for c in unique_calls if not c.startswith("/api/v1/")]

        total = len(unique_calls)
        raw = _clamp(len(v1_calls) / total * 10)
        passed = raw >= 6.0

        evidence = {
            "total_unique_calls": total,
            "v1_prefixed_count": len(v1_calls),
            "unversioned_count": len(unversioned),
            "v1_calls": sorted(set(v1_calls)),
            "unversioned_calls": sorted(set(unversioned)),
        }
        summary = f"{len(v1_calls)}/{total} unique frontend API calls use /api/v1/ prefix"
        detail = (
            f"Backend marks /api/ (unversioned) paths as deprecated (Sunset: 2027-01-01). "
            f"{len(unversioned)} frontend calls still use the deprecated /api/ prefix: "
            f"{sorted(set(unversioned))}."
        )
        remediation = (
            f"Migrate these frontend calls to /api/v1/ equivalents: {sorted(set(unversioned))}. "
            "The backend already exposes all these routes under /api/v1/. "
            "Update frontend/src/pages/ and frontend/src/context/ accordingly."
        ) if unversioned else "All frontend calls use /api/v1/ prefix."

        return DimensionResult(*DIM, raw_score=raw, passed=passed,
                               evidence=evidence, finding_summary=summary,
                               finding_detail=detail, remediation=remediation,
                               data_sources_found=["frontend/src/**/*.tsx"])
    except Exception:
        return _error_result(*DIM, traceback.format_exc())


def score_api_04(root: Path) -> DimensionResult:
    DIM = ("api_04", "FP&A Endpoint Wiring Completeness", "api_connectivity", 0.20, 9.0)
    try:
        outputs_text, err = read_text(root, "app/routers/outputs.py")
        if err:
            return _error_result(*DIM, err)
        costroom_text, err2 = read_text(root, "frontend/src/pages/CostRoom.tsx")
        if err2:
            return _error_result(*DIM, err2)

        results: Dict[str, Dict] = {}
        points = 0
        for ep_name, backend_substr, frontend_substr in _FPNA_ENDPOINTS:
            backend_ok = bool(re.search(re.escape(backend_substr), outputs_text))
            frontend_ok = bool(re.search(re.escape(frontend_substr), costroom_text))
            results[ep_name] = {"backend": backend_ok, "frontend": frontend_ok}
            points += (1 if backend_ok else 0) + (1 if frontend_ok else 0)

        raw = _clamp(points / 6 * 10)
        passed = raw >= 9.0

        missing: List[str] = []
        for ep, detail_d in results.items():
            if not detail_d["backend"]:
                missing.append(f"{ep} (backend missing)")
            if not detail_d["frontend"]:
                missing.append(f"{ep} (frontend missing)")

        evidence = {
            "endpoints_checked": [e[0] for e in _FPNA_ENDPOINTS],
            "detail": results,
            "points_scored": points,
            "points_possible": 6,
        }
        summary = f"{points}/6 FP&A endpoint check-points pass (backend+frontend per endpoint)"
        detail = (
            "Checked 3 FP&A endpoints for presence in app/routers/outputs.py (backend) "
            "and frontend/src/pages/CostRoom.tsx (frontend). "
            f"Missing: {missing or 'none'}."
        )
        remediation = (
            f"Wire missing FP&A endpoints: {missing}."
        ) if missing else "All 3 FP&A endpoints fully wired in backend and frontend."

        return DimensionResult(*DIM, raw_score=raw, passed=passed,
                               evidence=evidence, finding_summary=summary,
                               finding_detail=detail, remediation=remediation,
                               data_sources_found=["app/routers/outputs.py",
                                                   "frontend/src/pages/CostRoom.tsx"])
    except Exception:
        return _error_result(*DIM, traceback.format_exc())


# ---------------------------------------------------------------------------
# OPAR Loop Completeness — opar_01 … opar_03
# ---------------------------------------------------------------------------

def score_opar_01(root: Path) -> DimensionResult:
    DIM = ("opar_01", "Phase Module Non-Empty Coverage", "opar_loop", 0.30, 9.0)
    PHASES = ["observe", "plan", "act", "reflect"]
    try:
        phase_info: Dict[str, Dict] = {}
        score = 0.0
        for phase in PHASES:
            rel = f"app/opar/{phase}.py"
            text, err = read_text(root, rel)
            if err:
                phase_info[phase] = {"exists": False, "line_count": 0, "error": err}
            else:
                lines = len(text.splitlines())
                phase_info[phase] = {"exists": True, "line_count": lines}
                if lines > 100:
                    score += 2.5

        raw = _clamp(score)
        passed = raw >= 9.0

        thin = [p for p, v in phase_info.items() if v.get("line_count", 0) <= 100]
        evidence = {"phases": phase_info, "thin_or_missing": thin}
        summary = f"{int(score / 2.5)}/4 OPAR phase modules exist with >100 lines"
        detail = (
            "Checked app/opar/observe.py, plan.py, act.py, reflect.py for existence and line count >100. "
            f"Thin/missing: {thin or 'none'}. "
            + ", ".join(f"{p}: {v.get('line_count', 0)} lines" for p, v in phase_info.items())
        )
        remediation = (
            f"Implement these thin/missing phase modules: {thin}."
        ) if thin else "All 4 OPAR phase modules are substantively implemented."

        return DimensionResult(*DIM, raw_score=raw, passed=passed,
                               evidence=evidence, finding_summary=summary,
                               finding_detail=detail, remediation=remediation,
                               data_sources_found=[f"app/opar/{p}.py" for p in PHASES])
    except Exception:
        return _error_result(*DIM, traceback.format_exc())


def score_opar_02(root: Path) -> DimensionResult:
    DIM = ("opar_02", "Intent Handler Coverage in Plan", "opar_loop", 0.40, 8.0)
    try:
        models_text, err = read_text(root, "app/opar/models.py")
        if err:
            return _error_result(*DIM, err)
        plan_text, err2 = read_text(root, "app/opar/plan.py")
        if err2:
            return _error_result(*DIM, err2)

        intents = _extract_intent_values(models_text)
        if not intents:
            return _error_result(*DIM, "could not extract IntentClass values from models.py")

        handled, unhandled = [], []
        for intent in intents:
            if re.search(r'["\']' + re.escape(intent) + r'["\']', plan_text):
                handled.append(intent)
            else:
                unhandled.append(intent)

        total = len(intents)
        raw = _clamp(len(handled) / total * 10 if total else 0.0)
        passed = raw >= 8.0

        evidence = {
            "total_intents": total,
            "handled_count": len(handled),
            "unhandled": unhandled,
        }
        summary = f"{len(handled)}/{total} IntentClass values have a plan branch in plan.py"
        detail = (
            f"{total} IntentClass values in models.py. "
            f"plan.py references {len(handled)} as string literals. "
            f"Not referenced (fallback to generic_qa): {unhandled or 'none'}."
        )
        remediation = (
            f"Add plan branches for: {unhandled}."
        ) if unhandled else "Full intent coverage in plan.py."

        return DimensionResult(*DIM, raw_score=raw, passed=passed,
                               evidence=evidence, finding_summary=summary,
                               finding_detail=detail, remediation=remediation,
                               data_sources_found=["app/opar/models.py", "app/opar/plan.py"])
    except Exception:
        return _error_result(*DIM, traceback.format_exc())


def score_opar_03(root: Path) -> DimensionResult:
    DIM = ("opar_03", "Quality Gate Coverage in Reflect", "opar_loop", 0.30, 8.0)
    REQUIRED_CHECKS = ["validate_core_skill_outputs", "savings", "peer_benchmarker"]
    try:
        reflect_text, err = read_text(root, "app/opar/reflect.py")
        if err:
            return _error_result(*DIM, err)

        present: List[str] = []
        missing: List[str] = []
        for check in REQUIRED_CHECKS:
            if re.search(re.escape(check), reflect_text):
                present.append(check)
            else:
                missing.append(check)

        raw = _clamp(len(present) / len(REQUIRED_CHECKS) * 10)
        passed = raw >= 8.0

        evidence = {
            "required_checks": REQUIRED_CHECKS,
            "present": present,
            "missing": missing,
        }
        summary = f"{len(present)}/{len(REQUIRED_CHECKS)} required quality gate symbols present in reflect.py"
        detail = (
            f"Searched reflect.py for {REQUIRED_CHECKS}. "
            f"Present: {present}. Missing: {missing or 'none'}."
        )
        remediation = (
            f"Add quality gate logic referencing: {missing} in app/opar/reflect.py."
        ) if missing else "All required quality gate references present in reflect.py."

        return DimensionResult(*DIM, raw_score=raw, passed=passed,
                               evidence=evidence, finding_summary=summary,
                               finding_detail=detail, remediation=remediation,
                               data_sources_found=["app/opar/reflect.py"])
    except Exception:
        return _error_result(*DIM, traceback.format_exc())


# ---------------------------------------------------------------------------
# Infrastructure Completeness — infra_01 … infra_03
# ---------------------------------------------------------------------------

def score_infra_01(root: Path) -> DimensionResult:
    DIM = ("infra_01", "Connector Method Completeness", "infrastructure", 0.35, 8.0)
    CONNECTOR_FILES = [
        "app/connectors/ariba_csv.py",
        "app/connectors/bank_mt940.py",
        "app/connectors/gst_portal.py",
        "app/connectors/hrms_csv.py",
        "app/connectors/sap_odata.py",
        "app/connectors/tally_xml.py",
    ]
    REQUIRED_METHODS = ["def ingest", "def fetch", "def authenticate", "def connect"]
    try:
        connector_detail: Dict[str, Dict] = {}
        complete_count = 0

        for rel in CONNECTOR_FILES:
            text, err = read_text(root, rel)
            name = rel.split("/")[-1]
            if err:
                connector_detail[name] = {"exists": False, "has_method": False, "error": err}
                continue
            has_method = any(m in text for m in REQUIRED_METHODS)
            connector_detail[name] = {"exists": True, "has_method": has_method}
            if has_method:
                complete_count += 1

        total = len(CONNECTOR_FILES)
        raw = _clamp(complete_count / total * 10 if total else 0.0)
        passed = raw >= 8.0

        missing_method = [n for n, v in connector_detail.items() if not v.get("has_method")]
        evidence = {"connectors": connector_detail, "missing_method": missing_method}
        summary = f"{complete_count}/{total} connectors have at least one required entry-point method"
        detail = (
            f"Checked for def ingest/fetch/authenticate/connect in each connector. "
            f"Missing: {missing_method or 'none'}."
        )
        remediation = (
            f"Implement required entry-point methods in: {missing_method}."
        ) if missing_method else "All connectors have entry-point methods."

        return DimensionResult(*DIM, raw_score=raw, passed=passed,
                               evidence=evidence, finding_summary=summary,
                               finding_detail=detail, remediation=remediation,
                               data_sources_found=[r for r in CONNECTOR_FILES
                                                   if connector_detail.get(r.split("/")[-1], {}).get("exists")])
    except Exception:
        return _error_result(*DIM, traceback.format_exc())


def score_infra_02(root: Path) -> DimensionResult:
    DIM = ("infra_02", "Health Endpoint Coverage", "infrastructure", 0.30, 9.0)
    try:
        main_text, err = read_text(root, "app/main.py")
        if err:
            return _error_result(*DIM, err)

        health_present = bool(re.search(r'@app\.get\(["\']\/health["\']\)', main_text))
        ready_present = bool(re.search(r'@app\.get\(["\']\/health\/ready["\']\)', main_text))
        raw = (5.0 if health_present else 0.0) + (5.0 if ready_present else 0.0)
        passed = raw >= 9.0

        evidence = {
            "health_endpoint_present": health_present,
            "health_ready_endpoint_present": ready_present,
        }
        summary = (
            f"/health: {'✓' if health_present else '✗'}, "
            f"/health/ready: {'✓' if ready_present else '✗'}"
        )
        missing = [e for e, p in [("/health", health_present), ("/health/ready", ready_present)] if not p]
        detail = f"Searched app/main.py for @app.get('/health') and @app.get('/health/ready'). Missing: {missing or 'none'}."
        remediation = (
            f"Add these health endpoints to app/main.py: {missing}."
        ) if missing else "Both health endpoints present."

        return DimensionResult(*DIM, raw_score=raw, passed=passed,
                               evidence=evidence, finding_summary=summary,
                               finding_detail=detail, remediation=remediation,
                               data_sources_found=["app/main.py"])
    except Exception:
        return _error_result(*DIM, traceback.format_exc())


def score_infra_03(root: Path) -> DimensionResult:
    DIM = ("infra_03", "Rate Limit Coverage for LLM Endpoints", "infrastructure", 0.35, 6.0)
    try:
        main_text, err = read_text(root, "app/main.py")
        if err:
            return _error_result(*DIM, err)
        chat_text, err2 = read_text(root, "app/routers/chat.py")
        if err2:
            return _error_result(*DIM, err2)

        global_limiter = bool(re.search(r'Limiter\s*\(', main_text))
        per_route_limiter = bool(re.search(r'@.*limiter.*\.limit\s*\(', chat_text))

        raw = (7.0 if global_limiter else 0.0) + (3.0 if per_route_limiter else 0.0)
        passed = raw >= 6.0

        evidence = {
            "global_limiter_in_main": global_limiter,
            "per_route_limiter_in_chat": per_route_limiter,
        }
        summary = (
            f"Global limiter: {'✓' if global_limiter else '✗'} (+7), "
            f"per-route limiter in chat: {'✓' if per_route_limiter else '✗'} (+3)"
        )
        detail = (
            "Checked main.py for Limiter() instantiation (global rate limiting) "
            "and chat.py for @limiter.limit() per-route decorators on LLM endpoints."
        )
        remediation = (
            ("Add Limiter() in main.py and attach via app.state.limiter. " if not global_limiter else "")
            + ("Add @limiter.limit('10/minute') to each chat route handler. " if not per_route_limiter else "")
        ).strip() or "Rate limiting fully configured."

        return DimensionResult(*DIM, raw_score=raw, passed=passed,
                               evidence=evidence, finding_summary=summary,
                               finding_detail=detail, remediation=remediation,
                               data_sources_found=["app/main.py", "app/routers/chat.py"])
    except Exception:
        return _error_result(*DIM, traceback.format_exc())


# ---------------------------------------------------------------------------
# Aggregation + report builder
# ---------------------------------------------------------------------------

def compute_domain_score(dims: List[DimensionResult]) -> float:
    total_weight = sum(d.weight for d in dims)
    if total_weight == 0:
        return 0.0
    return sum(d.raw_score * d.weight for d in dims) / total_weight


def compute_overall_score(domains: List[DomainResult]) -> float:
    total_weight = sum(d.domain_weight for d in domains)
    if total_weight == 0:
        return 0.0
    return sum(d.domain_score * d.domain_weight for d in domains) / total_weight


def rank_gaps(domains: List[DomainResult]) -> List[Dict]:
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


def build_remediation_roadmap(gaps: List[Dict]) -> List[Dict]:
    return [
        {
            "priority": i + 1,
            "dimension_id": g["dimension_id"],
            "action": g["remediation"],
            "impact": f"Closes gap of {g['gap']:.1f} pts (severity {g['gap_severity']:.4f})",
        }
        for i, g in enumerate(gaps[:5])
    ]


def build_report(report: EvalReport) -> str:
    lines = [
        f"# OpEx Platform Feature Completeness Eval",
        f"",
        f"**Eval date**: {report.eval_date}  ",
        f"**Platform version**: {report.platform_version}  ",
        f"**Overall score**: {report.overall_score:.2f}/10  ",
        f"**Status**: {'PASS ✓' if report.passed else 'FAIL ✗'}",
        f"",
        f"---",
        f"",
        f"## Domain Summary",
        f"",
        f"| Domain | Score | Status |",
        f"|--------|-------|--------|",
    ]
    for dr in report.domain_results:
        status = "PASS ✓" if dr.passed else "FAIL ✗"
        lines.append(f"| {dr.domain_display} (w={dr.domain_weight:.2f}) | {dr.domain_score:.2f}/10 | {status} |")

    if report.top_gaps:
        lines += [
            f"",
            f"---",
            f"",
            f"## Top Gaps (ranked by severity)",
            f"",
        ]
        for g in report.top_gaps:
            lines += [
                f"### {g['dimension_id'].upper()} — {g['name']}",
                f"- **Score**: {g['raw_score']:.2f}/10 (threshold {g['threshold_pass']:.1f}, gap {g['gap']:.2f})",
                f"- **Finding**: {g['finding_summary']}",
                f"- **Remediation**: {g['remediation']}",
                f"",
            ]

    for dr in report.domain_results:
        lines += [
            f"---",
            f"",
            f"## {dr.domain_display}",
            f"",
            f"Domain score: **{dr.domain_score:.2f}/10** ({'PASS ✓' if dr.passed else 'FAIL ✗'})",
            f"",
            f"| Dimension | Score | Threshold | Status |",
            f"|-----------|-------|-----------|--------|",
        ]
        for dim in dr.dimension_results:
            status = "✓" if dim.passed else "✗"
            lines.append(
                f"| {dim.name} | {dim.raw_score:.2f} | {dim.threshold_pass:.1f} | {status} |"
            )
        lines.append("")
        for dim in dr.dimension_results:
            lines += [
                f"### {dim.dimension_id.upper()} — {dim.name}",
                f"",
                f"**Score**: {dim.raw_score:.2f}/10 (threshold {dim.threshold_pass:.1f}) — "
                f"{'PASS ✓' if dim.passed else 'FAIL ✗'}",
                f"",
                f"**Finding**: {dim.finding_summary}",
                f"",
                f"**Detail**: {dim.finding_detail}",
                f"",
                f"**Remediation**: {dim.remediation}",
                f"",
            ]

    if report.remediation_roadmap:
        lines += [
            f"---",
            f"",
            f"## Remediation Roadmap",
            f"",
        ]
        for item in report.remediation_roadmap:
            lines += [
                f"**{item['priority']}.** `{item['dimension_id']}` — {item['action']}  ",
                f"*{item['impact']}*",
                f"",
            ]

    return "\n".join(lines)


def write_report(report_text: str, scores_data: Dict, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report_text, encoding="utf-8")
    scores_path = output.with_name("feature_eval_scores.json")
    scores_path.write_text(json.dumps(scores_data, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="OpEx Platform Feature Completeness Evaluator")
    parser.add_argument("--project-root", type=Path, default=Path("."),
                        help="Path to project root (default: current directory)")
    parser.add_argument("--output", type=Path, default=None,
                        help="Output path for .md report (default: eval/feature_eval_report.md)")
    parser.add_argument("--json-only", action="store_true",
                        help="Write JSON scores only, skip markdown report")
    args = parser.parse_args()

    root = args.project_root.resolve()
    if args.output is None:
        args.output = root / "eval" / "feature_eval_report.md"

    print(f"Project root : {root}")
    print(f"Eval date    : {date.today()}")
    print()

    # Run all dimensions
    scorers = [
        score_sp_01, score_sp_02, score_sp_03, score_sp_04,
        score_api_01, score_api_02, score_api_03, score_api_04,
        score_opar_01, score_opar_02, score_opar_03,
        score_infra_01, score_infra_02, score_infra_03,
    ]

    all_dims: List[DimensionResult] = []
    for scorer in scorers:
        try:
            result = scorer(root)
        except Exception:
            result = _error_result("unknown", scorer.__name__, "unknown", 0.0, 0.0,
                                   traceback.format_exc())
        all_dims.append(result)

    # Group by domain in defined order
    domain_order = ["skill_pipeline", "api_connectivity", "opar_loop", "infrastructure"]
    domain_display = {
        "skill_pipeline":   "Skill Pipeline Completeness",
        "api_connectivity": "Frontend-Backend API Connectivity",
        "opar_loop":        "OPAR Loop Completeness",
        "infrastructure":   "Infrastructure Completeness",
    }
    domain_weights = {
        "skill_pipeline":   0.35,
        "api_connectivity": 0.35,
        "opar_loop":        0.20,
        "infrastructure":   0.10,
    }
    domain_threshold = 6.5

    domain_map: Dict[str, List[DimensionResult]] = {k: [] for k in domain_order}
    for dim in all_dims:
        if dim.domain in domain_map:
            domain_map[dim.domain].append(dim)

    domain_results: List[DomainResult] = []
    for domain_name in domain_order:
        dims = domain_map[domain_name]
        score = compute_domain_score(dims)
        domain_results.append(DomainResult(
            domain_name=domain_name,
            domain_display=domain_display[domain_name],
            domain_weight=domain_weights[domain_name],
            dimension_results=dims,
            domain_score=round(score, 3),
            passed=score >= domain_threshold,
        ))

    overall = compute_overall_score(domain_results)
    top_gaps = rank_gaps(domain_results)
    roadmap = build_remediation_roadmap(top_gaps)

    eval_report = EvalReport(
        platform_version="2.0",
        eval_date=str(date.today()),
        overall_score=round(overall, 3),
        domain_results=domain_results,
        top_gaps=top_gaps,
        remediation_roadmap=roadmap,
        passed=overall >= 6.0,
    )

    # Console summary
    print(f"{'Domain':<38} {'Score':>8}  {'Status'}")
    print("-" * 58)
    for dr in domain_results:
        status = "PASS ✓" if dr.passed else "FAIL ✗"
        print(f"{dr.domain_display:<38} {dr.domain_score:>6.2f}/10  {status}")
    print("-" * 58)
    print(f"{'OVERALL':<38} {overall:>6.2f}/10  {'PASS ✓' if eval_report.passed else 'FAIL ✗'}")
    print()
    if top_gaps:
        print(f"Top gap: {top_gaps[0]['dimension_id'].upper()} — {top_gaps[0]['name']} "
              f"(gap={top_gaps[0]['gap']:.1f}, severity={top_gaps[0]['gap_severity']:.4f})")
    print()

    # Build scores JSON
    scores_data = {
        "overall_score": eval_report.overall_score,
        "passed": eval_report.passed,
        "eval_date": eval_report.eval_date,
        "dimensions": [
            {
                "dimension_id": d.dimension_id,
                "name": d.name,
                "domain": d.domain,
                "raw_score": round(d.raw_score, 3),
                "threshold_pass": d.threshold_pass,
                "passed": d.passed,
                "gap": round(d.gap, 3),
                "finding_summary": d.finding_summary,
                "evidence": d.evidence,
            }
            for dr in domain_results
            for d in dr.dimension_results
        ],
    }

    if not args.json_only:
        report_text = build_report(eval_report)
        write_report(report_text, scores_data, args.output)
        print(f"Report  : {args.output}")
        print(f"Scores  : {args.output.with_name('feature_eval_scores.json')}")
    else:
        scores_path = args.output.with_name("feature_eval_scores.json")
        scores_path.parent.mkdir(parents=True, exist_ok=True)
        scores_path.write_text(json.dumps(scores_data, indent=2), encoding="utf-8")
        print(f"Scores  : {scores_path}")

    return 0 if eval_report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
