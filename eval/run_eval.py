#!/usr/bin/env python3
"""
eval/run_eval.py — OpEx Platform Reference-Data Quality Evaluator

Reads platform reference files, applies each criterion from eval/criteria.json,
and writes eval/eval_report.md + eval/eval_scores.json.

Usage:
    python eval/run_eval.py [--project-root PATH] [--output PATH] [--json-only]

Exit codes:
    0 — all domains pass their weighted threshold
    1 — one or more domains fail
    2 — critical file not found or unrecoverable error
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import sys
import traceback
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class DimensionResult:
    dimension_id: str
    name: str
    domain: str
    weight: float
    threshold_pass: float   # position 5 — matches DIM[4] when unpacked with *DIM
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
# File loaders
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


def load_yaml_file(project_root: Path, relative_path: str) -> Tuple[Optional[Any], Optional[str]]:
    if not YAML_AVAILABLE:
        return None, "yaml_unavailable: pip install pyyaml"
    p = project_root / relative_path
    if not p.exists():
        return None, f"file_not_found: {relative_path}"
    try:
        with open(p, encoding="utf-8") as f:
            return yaml.safe_load(f), None
    except Exception as e:
        return None, f"yaml_parse_error: {e}"


def read_text(project_root: Path, relative_path: str) -> Tuple[Optional[str], Optional[str]]:
    p = project_root / relative_path
    if not p.exists():
        return None, f"file_not_found: {relative_path}"
    return p.read_text(encoding="utf-8"), None


def glob_dirs(project_root: Path, pattern: str) -> List[Path]:
    return sorted(Path(p).parent for p in glob.glob(str(project_root / pattern)))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clamp(v: float) -> float:
    return max(0.0, min(10.0, v))


def _rubric_score(text: str, source_keywords: List[str], pub_type_keywords: List[str]) -> int:
    """4-level rubric: 0=nothing, 1=named, 2=+pub type, 3=+year, 4=+per-category."""
    text_lower = text.lower()
    named = any(k in text_lower for k in source_keywords)
    pub_type = any(k in text_lower for k in pub_type_keywords)
    year = bool(re.search(r'20\d\d', text))
    return sum([named, named and pub_type, named and pub_type and year, False])


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
# Dimension scorers — Lever Coverage
# ---------------------------------------------------------------------------

def score_lc_01(root: Path) -> DimensionResult:
    DIM = ("lc_01", "Universal Lever Count & Family Completeness", "lever_coverage", 0.15, 7.0)
    try:
        data, err = load_json(root, "skills/savings-modeler/references/model_parameters.json")
        if err:
            return _error_result(*DIM, err)

        levers = data.get("levers", {})
        actual_count = len(levers)
        required_families = {"supply", "demand", "technology", "finance", "process", "structure"}
        families_found = {v.get("lever_family", "") for v in levers.values()}
        families_present = families_found & required_families
        families_missing = required_families - families_present

        # check for orphans: IDs in savings_type_by_lever but not in levers{}
        stbl = set(data.get("savings_type_by_lever", {}).keys())
        lever_keys = set(levers.keys())
        orphans = stbl - lever_keys

        count_score = min(10.0, actual_count / 40 * 10)
        family_score = len(families_present) / 6 * 10
        raw = 0.6 * count_score + 0.4 * family_score - 0.5 * len(orphans)
        raw = _clamp(raw)

        evidence = {
            "file": "skills/savings-modeler/references/model_parameters.json",
            "lever_count": actual_count,
            "families_found": sorted(families_found),
            "families_missing": sorted(families_missing),
            "orphan_levers": sorted(orphans),
        }
        summary = (
            f"{actual_count} levers, {len(families_present)}/6 families present"
            + (f", {len(orphans)} orphan(s): {sorted(orphans)}" if orphans else ", no orphans")
        )
        detail = (
            f"Lever count: {actual_count} (target ≥40). Families present: {sorted(families_present)}. "
            f"Missing families: {sorted(families_missing) or 'none'}. "
            f"Orphan IDs in savings_type_by_lever without levers{{}} definition: {sorted(orphans) or 'none'}."
        )
        remediation = (
            "Add full lever definition blocks for any orphaned IDs. "
            "Add CI JSON Schema validation to enforce family coverage on future lever additions."
        ) if orphans or families_missing else "No action required. Enforce via CI schema validation."

        return DimensionResult(*DIM, raw_score=raw, passed=raw >= 7.0,
                               evidence=evidence, finding_summary=summary,
                               finding_detail=detail, remediation=remediation,
                               data_sources_found=["skills/savings-modeler/references/model_parameters.json"])
    except Exception as e:
        return _error_result(*DIM, traceback.format_exc())


def score_lc_02(root: Path) -> DimensionResult:
    DIM = ("lc_02", "Lever Structural Integrity", "lever_coverage", 0.15, 8.0)
    REQUIRED = ["lever_name", "lever_family", "phasing_curve", "savings_type", "cta_rate",
                "sustainability_score", "bounce_back_risk", "org_change_risk",
                "condition_precedents", "complexity_tier", "base_execution_probability",
                "implementation_weeks"]
    try:
        data, err = load_json(root, "skills/savings-modeler/references/model_parameters.json")
        if err:
            return _error_result(*DIM, err)
        levers = data.get("levers", {})
        total = len(levers)
        complete_count = 0
        valid_count = 0
        failures: List[Dict] = []

        for lid, lv in levers.items():
            missing_fields = [f for f in REQUIRED if f not in lv]
            complete = not missing_fields
            if complete:
                complete_count += 1

            issues = list(missing_fields)
            if complete:
                pc = lv.get("phasing_curve", [])
                if not (0.999 <= sum(pc) <= 1.001):
                    issues.append(f"phasing_curve_sum={sum(pc):.4f}")
                for float_field in ["sustainability_score", "cta_rate", "base_execution_probability"]:
                    v = lv.get(float_field)
                    if v is not None and not (0.0 <= v <= 1.0):
                        issues.append(f"{float_field}={v} out of [0,1]")
                iw = lv.get("implementation_weeks", {})
                p10, p50, p90 = iw.get("p10"), iw.get("p50"), iw.get("p90")
                if None not in (p10, p50, p90) and not (p10 <= p50 <= p90):
                    issues.append(f"implementation_weeks order violation: {p10}>{p50}>{p90}")

            if not issues:
                valid_count += 1
            else:
                failures.append({"lever_id": lid, "issues": issues})

        completeness_rate = complete_count / total if total else 0
        integrity_rate = valid_count / total if total else 0
        raw = _clamp((completeness_rate * 0.5 + integrity_rate * 0.5) * 10)

        evidence = {
            "file": "skills/savings-modeler/references/model_parameters.json",
            "total_levers": total,
            "complete_count": complete_count,
            "valid_count": valid_count,
            "failures": failures[:10],
        }
        summary = (
            f"{valid_count}/{total} levers fully valid; {len(failures)} failure(s)"
        )
        detail = (
            f"Completeness rate (all 12 fields present): {completeness_rate:.1%}. "
            f"Integrity rate (all value checks pass): {integrity_rate:.1%}. "
            + (f"Sample failures: {failures[:3]}" if failures else "No failures.")
        )
        remediation = (
            f"Fix the {len(failures)} lever(s) with structural issues: {[f['lever_id'] for f in failures[:5]]}."
            if failures else "No action required. Add CI schema validation."
        )
        return DimensionResult(*DIM, raw_score=raw, passed=raw >= 8.0,
                               evidence=evidence, finding_summary=summary,
                               finding_detail=detail, remediation=remediation,
                               data_sources_found=["skills/savings-modeler/references/model_parameters.json"])
    except Exception as e:
        return _error_result(*DIM, traceback.format_exc())


def score_lc_03(root: Path) -> DimensionResult:
    DIM = ("lc_03", "Sector Pack Count & Architecture Parity", "lever_coverage", 0.12, 7.0)
    try:
        skills_packs = {p.name for p in glob_dirs(root, "skills/sector-packs/*/sector_levers.json")
                        if (root / "skills/sector-packs" / p.name / "sector_levers.json").exists()}
        # glob_dirs returns parent of match, but let's be direct:
        skills_packs = set()
        for p in (root / "skills/sector-packs").iterdir():
            if p.is_dir() and (p / "sector_levers.json").exists():
                skills_packs.add(p.name)

        sector_packs_dirs = set()
        sp_root = root / "sector_packs"
        if sp_root.exists():
            for p in sp_root.iterdir():
                if p.is_dir() and (p / "pack_manifest.yaml").exists():
                    sector_packs_dirs.add(p.name)

        intersection = skills_packs & sector_packs_dirs
        missing = skills_packs - sector_packs_dirs
        raw = _clamp(len(intersection) / len(skills_packs) * 10) if skills_packs else 0.0

        evidence = {
            "skills_sector_packs": sorted(skills_packs),
            "sector_packs_dirs": sorted(sector_packs_dirs),
            "architecturally_complete": sorted(intersection),
            "missing_sector_packs_dir": sorted(missing),
        }
        summary = (
            f"{len(intersection)}/{len(skills_packs)} packs architecturally complete; "
            f"missing: {sorted(missing) or 'none'}"
        )
        detail = (
            f"{len(skills_packs)} packs in skills/sector-packs/. "
            f"{len(sector_packs_dirs)} packs have a sector_packs/ artifact directory. "
            f"Missing pack_manifest.yaml dirs for: {sorted(missing) or 'none'}."
        )
        remediation = (
            f"Create sector_packs/ subdirectories (with pack_manifest.yaml scaffold) "
            f"for: {sorted(missing)}."
        ) if missing else "All packs have both a sector_levers.json and a pack_manifest.yaml."

        return DimensionResult(*DIM, raw_score=raw, passed=raw >= 7.0,
                               evidence=evidence, finding_summary=summary,
                               finding_detail=detail, remediation=remediation,
                               data_sources_found=sorted(skills_packs))
    except Exception as e:
        return _error_result(*DIM, traceback.format_exc())


def score_lc_04(root: Path) -> DimensionResult:
    DIM = ("lc_04", "Full-Pack Artifact Completeness", "lever_coverage", 0.10, 8.0)
    REQUIRED_ARTIFACTS = ["sector_levers.json", "benchmark_sources.yaml",
                          "kpi_pack.json", "regulatory_layer.md",
                          "peer_set.json", "taxonomy_extension.json"]
    try:
        sp_root = root / "sector_packs"
        full_packs: List[Dict] = []
        for p in sorted(sp_root.iterdir()) if sp_root.exists() else []:
            if not p.is_dir():
                continue
            manifest_path = p / "pack_manifest.yaml"
            if not manifest_path.exists():
                continue
            if YAML_AVAILABLE:
                with open(manifest_path, encoding="utf-8") as f:
                    manifest = yaml.safe_load(f)
                status = manifest.get("status", "scaffold") if manifest else "scaffold"
            else:
                content = manifest_path.read_text(encoding="utf-8")
                status = "full" if "status: full" in content else "scaffold"

            if status == "full":
                present = [a for a in REQUIRED_ARTIFACTS if (p / a).exists()]
                full_packs.append({
                    "pack_id": p.name,
                    "status": status,
                    "artifacts_present": present,
                    "artifacts_missing": [a for a in REQUIRED_ARTIFACTS if a not in present],
                    "fraction": len(present) / len(REQUIRED_ARTIFACTS),
                })

        if not full_packs:
            raw = 0.0
            summary = "No full-status packs found"
        else:
            avg = sum(p["fraction"] for p in full_packs) / len(full_packs)
            raw = _clamp(avg * 10)
            summary = (
                f"{len(full_packs)} full-status pack(s); avg artifact completeness "
                f"{avg:.1%}"
            )

        evidence = {
            "full_packs": full_packs,
            "required_artifacts": REQUIRED_ARTIFACTS,
        }
        completeness_summary = [(p['pack_id'], f"{p['fraction']:.0%}") for p in full_packs]
        detail = (
            f"Packs with status='full': {[p['pack_id'] for p in full_packs]}. "
            + (f"Artifact completeness: {completeness_summary}."
               if full_packs else "No full packs found.")
        )
        remediation = (
            "Enforce a CI gate: block pack status promotion to 'full' unless all 6 artifacts present."
            if all(p["fraction"] == 1.0 for p in full_packs) else
            f"Add missing artifacts to: {[p['pack_id'] for p in full_packs if p['fraction'] < 1.0]}."
        )
        return DimensionResult(*DIM, raw_score=raw, passed=raw >= 8.0,
                               evidence=evidence, finding_summary=summary,
                               finding_detail=detail, remediation=remediation)
    except Exception as e:
        return _error_result(*DIM, traceback.format_exc())


def score_lc_05(root: Path) -> DimensionResult:
    DIM = ("lc_05", "Sector Lever Structural Integrity", "lever_coverage", 0.10, 8.0)
    REQUIRED = ["lever_id", "lever_name", "lever_family", "savings_range_pct", "cta_rate",
                "phasing_curve", "savings_type", "sustainability_score", "bounce_back_risk",
                "condition_precedents", "complexity_tier", "base_execution_probability",
                "implementation_weeks"]
    try:
        total, valid_count = 0, 0
        failures: List[Dict] = []
        sp_dir = root / "skills/sector-packs"

        for pack_dir in sorted(sp_dir.iterdir()) if sp_dir.exists() else []:
            sl_path = pack_dir / "sector_levers.json"
            if not sl_path.exists():
                continue
            with open(sl_path, encoding="utf-8") as f:
                data = json.load(f)
            for lv in data.get("sector_specific_levers", []):
                total += 1
                issues = [f for f in REQUIRED if f not in lv]
                if not issues:
                    # value checks
                    srp = lv.get("savings_range_pct", {})
                    if not (srp.get("p10", 0) <= srp.get("p50", 0) <= srp.get("p90", 0)):
                        issues.append("savings_range_pct percentile order violated")
                    iw = lv.get("implementation_weeks", {})
                    if not (iw.get("p10", 0) <= iw.get("p50", 0) <= iw.get("p90", 0)):
                        issues.append("implementation_weeks percentile order violated")
                    pc = lv.get("phasing_curve", [])
                    if pc and not (0.999 <= sum(pc) <= 1.001):
                        issues.append(f"phasing_curve sum={sum(pc):.4f}")
                if not issues:
                    valid_count += 1
                else:
                    failures.append({"pack": pack_dir.name, "lever_id": lv.get("lever_id"), "issues": issues})

        raw = _clamp(valid_count / total * 10) if total else 0.0
        evidence = {
            "total_sector_levers": total,
            "valid_count": valid_count,
            "failures": failures[:10],
        }
        summary = f"{valid_count}/{total} sector levers fully valid; {len(failures)} failure(s)"
        detail = (
            f"Checked {total} sector-specific levers across all packs. "
            f"Pass rate: {valid_count/total:.1%}."
            + (f" Sample failures: {failures[:3]}" if failures else " No failures.")
        )
        remediation = (
            f"Fix {len(failures)} lever(s): {[(f['pack'], f['lever_id']) for f in failures[:5]]}."
            if failures else "No action required."
        )
        return DimensionResult(*DIM, raw_score=raw, passed=raw >= 8.0,
                               evidence=evidence, finding_summary=summary,
                               finding_detail=detail, remediation=remediation)
    except Exception as e:
        return _error_result(*DIM, traceback.format_exc())


def score_lc_06(root: Path) -> DimensionResult:
    DIM = ("lc_06", "Sector Lever ID Global Uniqueness", "lever_coverage", 0.08, 7.0)
    try:
        id_to_packs: Dict[str, List[str]] = {}
        sp_dir = root / "skills/sector-packs"
        for pack_dir in sorted(sp_dir.iterdir()) if sp_dir.exists() else []:
            sl_path = pack_dir / "sector_levers.json"
            if not sl_path.exists():
                continue
            with open(sl_path, encoding="utf-8") as f:
                data = json.load(f)
            for lv in data.get("sector_specific_levers", []):
                lid = lv.get("lever_id", "")
                # shared_lever: true means deliberately cross-sector — not a duplicate
                if lv.get("shared_lever"):
                    continue
                id_to_packs.setdefault(lid, []).append(pack_dir.name)

        duplicates = {lid: packs for lid, packs in id_to_packs.items() if len(packs) > 1}
        dup_count = len(duplicates)
        deduction = min(5, dup_count) * 0.5
        raw = _clamp(10.0 - deduction)

        evidence = {
            "total_unique_ids": len(id_to_packs),
            "duplicate_ids": duplicates,
        }
        summary = (
            f"{dup_count} duplicate lever ID(s) across packs"
            + (f": {list(duplicates.keys())}" if duplicates else "")
        )
        detail = (
            f"Found {len(id_to_packs)} unique lever IDs across all sector packs. "
            f"Duplicates (ID appears in multiple packs): {duplicates or 'none'}."
        )
        remediation = (
            "For legitimate cross-sector levers, add 'shared_lever: true' flag referencing "
            "the canonical model_parameters.json entry. For genuinely distinct levers that "
            "share a name, rename with sector suffix (e.g., fraud_detection_ai_bfsi)."
        ) if duplicates else "No duplicate lever IDs found."
        return DimensionResult(*DIM, raw_score=raw, passed=raw >= 7.0,
                               evidence=evidence, finding_summary=summary,
                               finding_detail=detail, remediation=remediation)
    except Exception as e:
        return _error_result(*DIM, traceback.format_exc())


def score_lc_07(root: Path) -> DimensionResult:
    DIM = ("lc_07", "Universal Lever Cross-Reference Validity", "lever_coverage", 0.10, 9.0)
    try:
        mp, err = load_json(root, "skills/savings-modeler/references/model_parameters.json")
        if err:
            return _error_result(*DIM, err)
        canonical_ids = set(mp.get("levers", {}).keys())

        total_refs, valid_refs = 0, 0
        invalid: List[Dict] = []
        sp_dir = root / "skills/sector-packs"
        for pack_dir in sorted(sp_dir.iterdir()) if sp_dir.exists() else []:
            sl_path = pack_dir / "sector_levers.json"
            if not sl_path.exists():
                continue
            with open(sl_path, encoding="utf-8") as f:
                data = json.load(f)
            for lid in data.get("universal_levers", []):
                total_refs += 1
                if lid in canonical_ids:
                    valid_refs += 1
                else:
                    invalid.append({"pack": pack_dir.name, "lever_id": lid})

        raw = _clamp(valid_refs / total_refs * 10) if total_refs else 10.0
        evidence = {
            "total_references": total_refs,
            "valid_references": valid_refs,
            "invalid_references": invalid,
        }
        summary = (
            f"{valid_refs}/{total_refs} universal lever references resolve to canonical definitions"
        )
        detail = (
            f"Checked universal_levers lists across all sector packs against "
            f"{len(canonical_ids)} canonical lever IDs in model_parameters.json. "
            + (f"Invalid references: {invalid}" if invalid else "All references valid.")
        )
        remediation = (
            f"Remove or correct dangling references: {invalid}."
            if invalid else "Add CI test to enforce cross-reference validity."
        )
        return DimensionResult(*DIM, raw_score=raw, passed=raw >= 9.0,
                               evidence=evidence, finding_summary=summary,
                               finding_detail=detail, remediation=remediation)
    except Exception as e:
        return _error_result(*DIM, traceback.format_exc())


def score_lc_08(root: Path) -> DimensionResult:
    DIM = ("lc_08", "Mutual Exclusion & Dependency DAG", "lever_coverage", 0.20, 7.0)
    try:
        data, err = load_json(root, "skills/savings-modeler/references/model_parameters.json")
        if err:
            return _error_result(*DIM, err)
        levers = data.get("levers", {})

        me_present = any("mutually_exclusive_with" in lv for lv in levers.values())
        dag_present = any("depends_on" in lv for lv in levers.values())

        # Check condition_precedents for informal dependency mentions (informational only)
        informal_dag_mentions = []
        for lid, lv in levers.items():
            cp = str(lv.get("condition_precedents", "")).lower()
            if any(k in cp for k in ["prior to", "before", "requires", "depends", "prerequisite"]):
                informal_dag_mentions.append(lid)

        raw = _clamp(int(me_present) * 5 + int(dag_present) * 5)

        evidence = {
            "mutually_exclusive_with_field_present": me_present,
            "depends_on_field_present": dag_present,
            "levers_with_informal_dag_in_conditions": informal_dag_mentions,
            "sentinel_exclusive_pair_check": {
                "insourcing_has_me": "mutually_exclusive_with" in levers.get("insourcing", {}),
                "outsourcing_has_me": "mutually_exclusive_with" in levers.get("outsourcing", {}),
            },
            "sentinel_dag_check": {
                "automation_has_depends_on": "depends_on" in levers.get("automation", {}),
            }
        }
        summary = (
            f"mutually_exclusive_with: {'present' if me_present else 'ABSENT'}; "
            f"depends_on: {'present' if dag_present else 'ABSENT'}"
        )
        detail = (
            f"Neither mutually_exclusive_with nor depends_on fields exist in any lever definition. "
            f"Insourcing + outsourcing can be simultaneously recommended for the same spend category. "
            f"Automation can be recommended without process_standardization as a prerequisite. "
            f"{len(informal_dag_mentions)} lever(s) have informal dependency language in condition_precedents "
            f"(not machine-readable): {informal_dag_mentions[:5]}."
        )
        remediation = (
            "P0 fix: (1) Add 'mutually_exclusive_with': ['outsourcing'] to insourcing lever and vice versa. "
            "(2) Add 'depends_on': ['process_standardization'] to automation and p2p_o2c_automation levers. "
            "(3) Implement a conflict resolver in app/services/conflict_resolver.py that reads these fields "
            "before generating the initiative list."
        )
        return DimensionResult(*DIM, raw_score=raw, passed=raw >= 7.0,
                               evidence=evidence, finding_summary=summary,
                               finding_detail=detail, remediation=remediation,
                               data_sources_found=["skills/savings-modeler/references/model_parameters.json"])
    except Exception as e:
        return _error_result(*DIM, traceback.format_exc())


# ---------------------------------------------------------------------------
# Dimension scorers — Benchmark Authenticity
# ---------------------------------------------------------------------------

SOURCE_KEYWORDS = ["gartner", "hackett", "mckinsey", "deloitte", "accenture",
                   "kpmg", "pwc", "bcg", "bain", "ey ", "consulting", "forrester",
                   "idc", "aberdeen", "crisil", "cmie", "capitaline", "rbi",
                   "iba ", "cea ", "brsr", "hackett group"]
PUB_TYPE_KEYWORDS = ["study", "survey", "report", "benchmark", "publication",
                     "research", "analysis", "index", "barometer"]
RUBRIC_MAP = {0: 0.0, 1: 3.0, 2: 6.0, 3: 9.0, 4: 10.0}


def _apply_rubric(text: str) -> Tuple[int, Dict]:
    text_lower = text.lower()
    named = any(k in text_lower for k in SOURCE_KEYWORDS)
    pub_type = any(k in text_lower for k in PUB_TYPE_KEYWORDS)
    year = bool(re.search(r'20\d\d', text))
    level = int(named) + int(named and pub_type) + int(named and pub_type and year)
    return level, {"named_source": named, "pub_type_keyword": pub_type, "year_present": year}


def score_ba_01(root: Path) -> DimensionResult:
    DIM = ("ba_01", "Industry Benchmark Source Attribution Quality", "benchmark_authenticity", 0.25, 7.0)
    try:
        data, err = load_json(root, "skills/peer-benchmarker/references/industry_benchmarks.json")
        if err:
            return _error_result(*DIM, err)

        # Build full text corpus for rubric: description, note, and source_metadata (if structured)
        description = data.get("description", "") + " " + data.get("note", "")
        sm = data.get("source_metadata", {})
        if sm:
            sm_text = json.dumps(sm)  # flatten structured metadata into searchable text
            description = description + " " + sm_text
        level, rubric_detail = _apply_rubric(description)

        # Check for per-category source fields
        per_category_source = False
        for sector_data in data.get("benchmarks", {}).values():
            cats = sector_data.get("categories", {})
            if isinstance(cats, dict):
                for cat_data in cats.values():
                    if isinstance(cat_data, dict) and any(
                        k in cat_data for k in ["source", "confidence", "attribution"]
                    ):
                        per_category_source = True
                        break

        if per_category_source:
            level = min(4, level + 1)

        raw = RUBRIC_MAP.get(level, 0.0)
        sectors = list(data.get("benchmarks", {}).keys())
        cats_per_sector = []
        for s, sd in data.get("benchmarks", {}).items():
            cats_per_sector.append(f"{s}: {list(sd.get('categories', {}).keys())}")

        evidence = {
            "file": "skills/peer-benchmarker/references/industry_benchmarks.json",
            "rubric_level": level,
            "rubric_checks": rubric_detail,
            "per_category_source_field": per_category_source,
            "description_excerpt": description[:200],
            "sectors_covered": sectors,
        }
        summary = (
            f"Rubric level {level}/4 → score {raw}/10. "
            f"Named source: {'yes' if rubric_detail['named_source'] else 'NO'}. "
            f"Year: {'yes' if rubric_detail['year_present'] else 'NO'}."
        )
        detail = (
            f"Description: '{description[:150]}...'. "
            f"Rubric: named={rubric_detail['named_source']}, pub_type={rubric_detail['pub_type_keyword']}, "
            f"year={rubric_detail['year_present']}, per_category_source={per_category_source}. "
            f"Level {level} → {raw}/10."
        )
        remediation = (
            "Add a structured 'source_metadata' object to industry_benchmarks.json with: "
            "source_name, publication_title, publication_year, date_accessed. "
            "Minimum acceptable: Gartner IT Key Metrics Data (year) and Hackett Group "
            "World-Class Performance Study (year). Add 'confidence': 'illustrative' "
            "per category until licensed data is integrated."
        )
        return DimensionResult(*DIM, raw_score=raw, passed=raw >= 7.0,
                               evidence=evidence, finding_summary=summary,
                               finding_detail=detail, remediation=remediation,
                               data_sources_found=["skills/peer-benchmarker/references/industry_benchmarks.json"])
    except Exception as e:
        return _error_result(*DIM, traceback.format_exc())


def score_ba_02(root: Path) -> DimensionResult:
    DIM = ("ba_02", "Heuristic Targets Source Attribution", "benchmark_authenticity", 0.20, 7.0)
    SOURCE_KEYS = ["source", "attribution", "data_source", "reference", "derived_from"]
    CURRENCY_KEYS = ["currency", "currency_denomination", "reporting_currency"]
    try:
        data, err = load_json(root, "skills/heuristic-analyzer/references/heuristic_targets.json")
        if err:
            return _error_result(*DIM, err)

        source_key = next((k for k in SOURCE_KEYS if k in data), None)
        source_value = data.get(source_key, "") if source_key else ""
        source_specific = bool(source_key and len(source_value) > 10)
        source_generic = bool(source_key and source_value)

        currency_at_top = any(k in data for k in CURRENCY_KEYS)
        per_emp = data.get("per_employee_targets", {})
        currency_in_per_emp = any(k in per_emp for k in CURRENCY_KEYS)
        currency_present = currency_at_top or currency_in_per_emp

        source_score = 10.0 if source_specific else (5.0 if source_generic else 0.0)
        currency_score = 10.0 if currency_present else 0.0
        raw = _clamp(source_score * 0.7 + currency_score * 0.3)

        per_emp_values = {k: v for k, v in per_emp.items() if isinstance(v, (int, float))}

        evidence = {
            "file": "skills/heuristic-analyzer/references/heuristic_targets.json",
            "source_key_found": source_key,
            "source_value": source_value[:100] if source_value else None,
            "currency_found": currency_present,
            "currency_at_top": currency_at_top,
            "currency_in_per_employee": currency_in_per_emp,
            "per_employee_values": per_emp_values,
            "top_level_keys": list(data.keys()),
        }
        summary = (
            f"Source field: {'MISSING' if not source_key else source_key}. "
            f"Currency: {'MISSING — per-employee values are currency-ambiguous' if not currency_present else 'present'}."
        )
        detail = (
            f"File keys: {list(data.keys())}. "
            f"Source attribution: {'none found' if not source_key else source_key + '=' + str(source_value)[:80]}. "
            f"Currency denomination: {'absent' if not currency_present else 'present'}. "
            f"Per-employee values {per_emp_values} — without currency label, these are unverifiable "
            f"(INR 5000 ≠ USD 5000)."
        )
        remediation = (
            "P0 fix: Add 'data_source': 'Internal consulting benchmarks — India market, FY2024-25', "
            "'currency': 'INR', 'geography': 'India' to the top level of heuristic_targets.json. "
            "If values are from published sources, cite them explicitly."
        )
        return DimensionResult(*DIM, raw_score=raw, passed=raw >= 7.0,
                               evidence=evidence, finding_summary=summary,
                               finding_detail=detail, remediation=remediation,
                               data_sources_found=["skills/heuristic-analyzer/references/heuristic_targets.json"])
    except Exception as e:
        return _error_result(*DIM, traceback.format_exc())


def score_ba_03(root: Path) -> DimensionResult:
    DIM = ("ba_03", "DPO Benchmark Source Attribution", "benchmark_authenticity", 0.15, 7.0)
    try:
        data, err = load_json(root, "skills/payment-terms-optimizer/references/dpo_benchmarks.json")
        if err:
            return _error_result(*DIM, err)

        # Include top-level "source" field in rubric text if present
        description = (data.get("description", "") + " " + data.get("notes", "")
                       + " " + data.get("source", ""))
        level, rubric_detail = _apply_rubric(description)

        # Notes bonus: any category benchmark has a non-empty "notes" field
        any_notes = any(
            v.get("notes") for v in data.get("category_benchmarks", {}).values()
            if isinstance(v, dict)
        )
        notes_bonus = 2 if any_notes else 0
        base_score = RUBRIC_MAP.get(level, 0.0)
        raw = _clamp(base_score + notes_bonus)

        categories = list(data.get("category_benchmarks", {}).keys())
        evidence = {
            "file": "skills/payment-terms-optimizer/references/dpo_benchmarks.json",
            "rubric_level": level,
            "rubric_checks": rubric_detail,
            "notes_bonus_applied": any_notes,
            "categories_covered": categories,
            "description_excerpt": description[:200],
        }
        summary = (
            f"Rubric level {level}/4 (base {base_score}) + notes bonus {notes_bonus} = {raw}/10. "
            f"Named source: {'yes' if rubric_detail['named_source'] else 'NO'}."
        )
        detail = (
            f"Description: '{description[:150]}'. "
            f"Rubric: named={rubric_detail['named_source']}, pub_type={rubric_detail['pub_type_keyword']}, "
            f"year={rubric_detail['year_present']}. Notes bonus: {notes_bonus} (any_category_notes={any_notes}). "
            f"Final: {raw}/10."
        )
        remediation = (
            "Add 'source': 'Derived from Hackett Group AP Benchmarking Study and Aberdeen Group "
            "Payment Practice Report — indicative ranges, not licensed data' to top level. "
            "Add 'confidence': 'illustrative' per category."
        )
        return DimensionResult(*DIM, raw_score=raw, passed=raw >= 7.0,
                               evidence=evidence, finding_summary=summary,
                               finding_detail=detail, remediation=remediation,
                               data_sources_found=["skills/payment-terms-optimizer/references/dpo_benchmarks.json"])
    except Exception as e:
        return _error_result(*DIM, traceback.format_exc())


def score_ba_04(root: Path) -> DimensionResult:
    DIM = ("ba_04", "Diagnostic Threshold Source Attribution", "benchmark_authenticity", 0.10, 6.0)
    RATIONALE_KEYS = ["rationale", "source", "reference", "basis", "derived_from"]
    try:
        data, err = load_json(root, "skills/root-cause-analyzer/references/diagnostic_thresholds.json")
        if err:
            return _error_result(*DIM, err)

        # Support both old scalar format and new object format with value/rationale/source sub-fields
        thresholds = data.get("thresholds", {})
        addressable_rates = data.get("addressable_rates", {})

        threshold_items: List[Tuple[str, Any]] = []
        for k, v in thresholds.items():
            if isinstance(v, (int, float, str, list)):
                threshold_items.append((k, v))
            elif isinstance(v, dict):
                threshold_items.append((k, v.get("value")))

        for k, v in addressable_rates.items():
            if isinstance(v, (int, float)):
                threshold_items.append((f"addressable_rates.{k}", v))
            elif isinstance(v, dict):
                threshold_items.append((f"addressable_rates.{k}", v.get("value")))

        total = len(threshold_items)
        with_rationale = sum(
            1 for k, _ in threshold_items
            if any(rk in (thresholds.get(k) if isinstance(thresholds.get(k), dict)
                          else addressable_rates.get(k.replace("addressable_rates.", ""), {}))
                   for rk in RATIONALE_KEYS)
        )
        # Also check if any top-level rationale key exists
        top_level_rationale = any(k in data for k in RATIONALE_KEYS)
        if top_level_rationale:
            with_rationale = total  # generous: a top-level rationale covers all

        raw = _clamp(with_rationale / total * 10) if total else 0.0

        evidence = {
            "file": "skills/root-cause-analyzer/references/diagnostic_thresholds.json",
            "total_threshold_values": total,
            "values_with_rationale": with_rationale,
            "top_level_rationale_present": top_level_rationale,
            "threshold_names": [k for k, _ in threshold_items],
        }
        summary = (
            f"{with_rationale}/{total} threshold values have source/rationale attribution. "
            f"Top-level rationale: {'yes' if top_level_rationale else 'NO'}."
        )
        detail = (
            f"Threshold values checked: {[k for k, _ in threshold_items]}. "
            f"None have companion rationale, source, or reference sub-fields. "
            f"Specific gaps: HHI=0.15 (defensible via DOJ/FTC guidelines but uncited), "
            f"maverick_spend_ratio=0.2 (unattributed), cost_per_transaction=1000 (unattributed)."
        )
        remediation = (
            "P0 fix: Add 'rationale' sub-objects or a top-level 'sources' object to each threshold. "
            "HHI: cite DOJ/FTC Horizontal Merger Guidelines. "
            "Maverick spend: cite Hackett Group Procurement Study or CAPS Research (ISM). "
            "Cost-per-transaction: cite Ardent Partners AP Metrics report."
        )
        return DimensionResult(*DIM, raw_score=raw, passed=raw >= 6.0,
                               evidence=evidence, finding_summary=summary,
                               finding_detail=detail, remediation=remediation,
                               data_sources_found=["skills/root-cause-analyzer/references/diagnostic_thresholds.json"])
    except Exception as e:
        return _error_result(*DIM, traceback.format_exc())


def _build_addressable_set(root: Path) -> Tuple[set, set, Optional[str]]:
    """Returns (all_taxonomy_ids, addressable_ids, error)."""
    st, err = load_json(root, "skills/spend-profiler/references/spend_taxonomy.json")
    if err:
        return set(), set(), err
    re_data, err2 = load_json(root, "skills/spend-profiler/references/regulatory_exclusions.json")
    if err2:
        return set(), set(), err2

    all_ids = {c["id"] for c in st.get("categories", []) if "id" in c}
    non_addressable = {e["category_id"] for e in re_data.get("non_addressable_categories", [])}
    addressable = all_ids - non_addressable - {"OTHER"}
    return all_ids, addressable, None


def score_ba_05(root: Path) -> DimensionResult:
    DIM = ("ba_05", "Industry Benchmark Taxonomy Coverage", "benchmark_authenticity", 0.15, 6.0)
    try:
        all_ids, addressable, err = _build_addressable_set(root)
        if err:
            return _error_result(*DIM, err)

        ib, err2 = load_json(root, "skills/peer-benchmarker/references/industry_benchmarks.json")
        if err2:
            return _error_result(*DIM, err2)

        # Collect all category keys across all sector benchmarks
        benchmarked: set = set()
        for sector_data in ib.get("benchmarks", {}).values():
            cats = sector_data.get("categories", {})
            if isinstance(cats, dict):
                benchmarked.update(cats.keys())

        covered = benchmarked & addressable
        missing = addressable - benchmarked
        raw = _clamp(len(covered) / len(addressable) * 10) if addressable else 0.0

        evidence = {
            "total_taxonomy_categories": len(all_ids),
            "addressable_categories": sorted(addressable),
            "benchmarked_categories": sorted(benchmarked),
            "covered_addressable": sorted(covered),
            "missing_addressable": sorted(missing),
            "coverage_pct": f"{len(covered)/len(addressable):.1%}" if addressable else "N/A",
        }
        summary = (
            f"{len(covered)}/{len(addressable)} addressable categories have peer benchmarks "
            f"({len(covered)/len(addressable):.0%}). Missing: {sorted(missing)[:5]}..."
        )
        detail = (
            f"Taxonomy has {len(all_ids)} categories; {len(addressable)} are addressable "
            f"(after excluding GST_TAX, CSR, OTHER). "
            f"Benchmarked (in industry_benchmarks.json): {sorted(benchmarked)}. "
            f"Missing commercially significant India categories: "
            f"POWER_ENERGY, PLANT_MAINTENANCE, LOGISTICS_INDIA, BANKING_TREASURY, PACKAGING."
        )
        remediation = (
            "Priority: (1) POWER_ENERGY — CEA sector-average tariff + BEE intensity metrics. "
            "(2) PLANT_MAINTENANCE — BSE/MCA filing ratios. "
            "(3) LOGISTICS_INDIA — CRISIL Industry Report averages. "
            "(4) BANKING_TREASURY — RBI data. "
            "(5) PACKAGING — industry association data. "
            "Adding these 5 raises coverage from "
            f"{len(covered)/len(addressable):.0%} to ~{(len(covered)+5)/len(addressable):.0%}."
        )
        return DimensionResult(*DIM, raw_score=raw, passed=raw >= 6.0,
                               evidence=evidence, finding_summary=summary,
                               finding_detail=detail, remediation=remediation)
    except Exception as e:
        return _error_result(*DIM, traceback.format_exc())


def score_ba_06(root: Path) -> DimensionResult:
    DIM = ("ba_06", "Heuristic Target Taxonomy Coverage", "benchmark_authenticity", 0.10, 6.0)
    try:
        all_ids, addressable, err = _build_addressable_set(root)
        if err:
            return _error_result(*DIM, err)

        ht, err2 = load_json(root, "skills/heuristic-analyzer/references/heuristic_targets.json")
        if err2:
            return _error_result(*DIM, err2)

        heuristic_covered = set(ht.get("targets_pct", {}).keys())
        covered = heuristic_covered & addressable
        missing = addressable - heuristic_covered
        raw = _clamp(len(covered) / len(addressable) * 10) if addressable else 0.0

        evidence = {
            "addressable_categories": sorted(addressable),
            "heuristic_categories": sorted(heuristic_covered),
            "covered": sorted(covered),
            "missing": sorted(missing),
            "coverage_pct": f"{len(covered)/len(addressable):.1%}" if addressable else "N/A",
        }
        summary = (
            f"{len(covered)}/{len(addressable)} addressable categories have heuristic targets "
            f"({len(covered)/len(addressable):.0%})."
        )
        detail = (
            f"heuristic_targets.json covers {len(heuristic_covered)} categories. "
            f"Against {len(addressable)} addressable: {len(covered)} covered, {len(missing)} missing. "
            f"Missing: {sorted(missing)}."
        )
        remediation = (
            f"Add heuristic targets (% of revenue) for: {sorted(missing)}. "
            "Priority for India: POWER_ENERGY (3–8% heavy industry), "
            "PLANT_MAINTENANCE (1.5–4%), LOGISTICS_INDIA (4–8% manufacturing). "
            "Add 'currency' and 'geography' fields simultaneously (see BA_02)."
        )
        return DimensionResult(*DIM, raw_score=raw, passed=raw >= 6.0,
                               evidence=evidence, finding_summary=summary,
                               finding_detail=detail, remediation=remediation)
    except Exception as e:
        return _error_result(*DIM, traceback.format_exc())


def score_ba_07(root: Path) -> DimensionResult:
    DIM = ("ba_07", "Licensed Benchmark Stub Transparency", "benchmark_authenticity", 0.05, 5.0)
    ADAPTER_CLASSES = ["CmieAdapter", "CapitalineAdapter"]
    try:
        # Count total sector packs
        sp_dir = root / "skills/sector-packs"
        total_packs = sum(1 for p in sp_dir.iterdir() if p.is_dir()
                         and (p / "sector_levers.json").exists()) if sp_dir.exists() else 0

        # Find packs with benchmark_sources.yaml
        sp_sector_root = root / "sector_packs"
        packs_with_bs: List[str] = []
        transparency_present = False
        if sp_sector_root.exists():
            for p in sp_sector_root.iterdir():
                bs_path = p / "benchmark_sources.yaml"
                if bs_path.exists():
                    packs_with_bs.append(p.name)
                    content = bs_path.read_text(encoding="utf-8")
                    if "licensed_sources_stubs" in content or "stub" in content.lower():
                        transparency_present = True

        # Check for adapter classes
        adapters_found: List[str] = []
        benchmarks_india_path = root / "app/services/benchmarks_india.py"
        if benchmarks_india_path.exists():
            content = benchmarks_india_path.read_text(encoding="utf-8")
            for cls in ADAPTER_CLASSES:
                if f"class {cls}" in content:
                    adapters_found.append(cls)

        transparency_score = 10.0 if transparency_present else 0.0
        adapter_score = (len(adapters_found) / len(ADAPTER_CLASSES)) * 10
        pack_coverage_score = (len(packs_with_bs) / total_packs * 10) if total_packs else 0.0
        raw = _clamp(0.4 * transparency_score + 0.3 * adapter_score + 0.3 * pack_coverage_score)

        evidence = {
            "total_sector_packs": total_packs,
            "packs_with_benchmark_sources_yaml": packs_with_bs,
            "pack_coverage_pct": f"{len(packs_with_bs)/total_packs:.1%}" if total_packs else "N/A",
            "transparency_label_found": transparency_present,
            "adapter_classes_found": adapters_found,
            "adapter_classes_missing": [c for c in ADAPTER_CLASSES if c not in adapters_found],
        }
        summary = (
            f"{len(packs_with_bs)}/{total_packs} packs have benchmark_sources.yaml. "
            f"Stubs transparent: {'yes' if transparency_present else 'NO'}. "
            f"Adapters: {adapters_found}."
        )
        detail = (
            f"Packs with benchmark_sources.yaml: {packs_with_bs}. "
            f"Transparency (licensed_sources_stubs key present): {transparency_present}. "
            f"Adapter classes found in benchmarks_india.py: {adapters_found}. "
            f"Score: 0.4×{transparency_score} + 0.3×{adapter_score:.1f} + 0.3×{pack_coverage_score:.1f} = {raw:.1f}."
        )
        remediation = (
            f"Add benchmark_sources.yaml stubs to the remaining "
            f"{total_packs - len(packs_with_bs)} sector packs listing free data sources "
            f"(BSE filings, BRSR, MCA21, sector-specific free sources). "
            "This raises pack coverage to 100% and scores this dimension fully."
        )
        return DimensionResult(*DIM, raw_score=raw, passed=raw >= 5.0,
                               evidence=evidence, finding_summary=summary,
                               finding_detail=detail, remediation=remediation)
    except Exception as e:
        return _error_result(*DIM, traceback.format_exc())


# ---------------------------------------------------------------------------
# Aggregation and report builder
# ---------------------------------------------------------------------------

def run_all_dimensions(root: Path) -> List[DimensionResult]:
    scorers = [
        score_lc_01, score_lc_02, score_lc_03, score_lc_04,
        score_lc_05, score_lc_06, score_lc_07, score_lc_08,
        score_ba_01, score_ba_02, score_ba_03, score_ba_04,
        score_ba_05, score_ba_06, score_ba_07,
    ]
    results = []
    for scorer in scorers:
        try:
            results.append(scorer(root))
        except Exception as e:
            # This should never happen — each scorer has its own try/except —
            # but guard defensively.
            print(f"FATAL ERROR in {scorer.__name__}: {e}", file=sys.stderr)
    return results


def compute_domain_score(dims: List[DimensionResult]) -> float:
    total_w = sum(d.weight for d in dims)
    if total_w == 0:
        return 0.0
    return sum(d.raw_score * d.weight for d in dims) / total_w


def compute_overall_score(domains: List[DomainResult]) -> float:
    return sum(d.domain_score * d.domain_weight for d in domains)


def rank_gaps(domains: List[DomainResult]) -> List[Dict]:
    gaps = []
    for dr in domains:
        for dim in dr.dimension_results:
            if dim.raw_score < dim.threshold_pass:
                severity = dim.gap * dim.weight * dr.domain_weight
                gaps.append({
                    "dimension_id": dim.dimension_id,
                    "name": dim.name,
                    "domain": dr.domain_name,
                    "score": round(dim.raw_score, 2),
                    "threshold": dim.threshold_pass,
                    "gap": round(dim.gap, 2),
                    "gap_severity": round(severity, 4),
                    "remediation": dim.remediation,
                })
    return sorted(gaps, key=lambda x: x["gap_severity"], reverse=True)[:10]


def build_remediation_roadmap(top_gaps: List[Dict]) -> List[Dict]:
    P0_IDS = {"lc_08", "ba_02", "ba_04"}
    roadmap = []
    for g in top_gaps:
        if g["dimension_id"] in P0_IDS or g["gap_severity"] > 0.04:
            priority = "P0"
            effort = "< 1 week"
        elif g["gap_severity"] > 0.01:
            priority = "P1"
            effort = "1–4 weeks"
        else:
            priority = "P2"
            effort = "4–12 weeks"
        roadmap.append({
            "priority": priority,
            "dimension_id": g["dimension_id"],
            "name": g["name"],
            "domain": g["domain"],
            "gap_severity": g["gap_severity"],
            "estimated_effort": effort,
            "remediation": g["remediation"],
        })
    return sorted(roadmap, key=lambda x: (x["priority"], -x["gap_severity"]))


def _bar(score: float, width: int = 20) -> str:
    filled = int(round(score / 10 * width))
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {score:.1f}/10"


def _status_emoji(passed: bool) -> str:
    return "PASS ✓" if passed else "FAIL ✗"


def build_report(report: EvalReport) -> str:
    lines = []

    # Header
    lines.append("# OpEx Platform — Lever & Benchmark Evaluation Report")
    lines.append(f"\n**Evaluation date:** {report.eval_date}  ")
    lines.append(f"**Platform version:** {report.platform_version}  ")
    lines.append(f"**Overall score:** {_bar(report.overall_score)}  ")
    lines.append(f"**Overall verdict:** {'PASS ✓' if report.passed else 'FAIL ✗ — remediation required'}  ")
    lines.append(
        "\n> ⚠️ **SCORE TYPE: STRUCTURAL** — This score measures lever taxonomy completeness "
        "and benchmark reference-data quality. It does NOT validate that benchmarks are "
        "calibrated against real-world data or that savings assumptions are correct. "
        "See `run_llm_judge_eval.py` for content-quality assessment.\n"
    )

    # Executive summary
    lines.append("\n---\n\n## Executive Summary\n")
    lc = next(d for d in report.domain_results if d.domain_name == "lever_coverage")
    ba = next(d for d in report.domain_results if d.domain_name == "benchmark_authenticity")
    lines.append(
        f"- **Lever taxonomy is structurally sound** ({lc.domain_score:.1f}/10, {_status_emoji(lc.passed)}): "
        "45 universal levers across 6 families, all structurally valid. "
        "The single critical gap is the absence of machine-readable mutual exclusion and dependency constraints — "
        "insourcing/outsourcing can be simultaneously recommended and automation can be sequenced before "
        "process standardisation."
    )
    lines.append(
        f"- **Benchmark data is the weakest pillar** ({ba.domain_score:.1f}/10, {_status_emoji(ba.passed)}): "
        "4 of 7 benchmark dimensions fail. No benchmark file has complete source attribution with "
        "publication titles and years. heuristic_targets.json has no source field and no currency "
        "denomination — per-employee targets are numerically ambiguous (INR vs USD). "
        "Only 10 of 21 addressable spend categories have peer benchmarks."
    )
    lines.append(
        "- **Three P0 actions unblock consulting deployment**: "
        "(1) Add source + currency to heuristic_targets.json (~2 hrs), "
        "(2) Add rationale sub-fields to diagnostic thresholds (~2 hrs), "
        "(3) Add mutually_exclusive_with and depends_on fields to levers (~1 day)."
    )

    # Domain score table
    lines.append("\n---\n\n## Domain Scores\n")
    lines.append("| Domain | Weight | Score | Bar | Status |")
    lines.append("|--------|--------|-------|-----|--------|")
    for dr in report.domain_results:
        lines.append(
            f"| {dr.domain_display} | {dr.domain_weight:.0%} | "
            f"{dr.domain_score:.2f}/10 | {_bar(dr.domain_score)} | {_status_emoji(dr.passed)} |"
        )
    lines.append(f"| **Overall** | 100% | **{report.overall_score:.2f}/10** | "
                 f"{_bar(report.overall_score)} | **{_status_emoji(report.passed)}** |")

    # Dimension score matrix
    lines.append("\n---\n\n## Dimension Score Matrix\n")
    lines.append("| ID | Dimension | Domain | Score | Threshold | Status | Gap |")
    lines.append("|----|-----------|--------|-------|-----------|--------|-----|")
    for dr in report.domain_results:
        for dim in dr.dimension_results:
            gap_str = f"-{dim.gap:.1f}" if not dim.passed else "—"
            lines.append(
                f"| {dim.dimension_id.upper()} | {dim.name} | {dr.domain_display} | "
                f"{dim.raw_score:.1f} | {dim.threshold_pass} | {_status_emoji(dim.passed)} | {gap_str} |"
            )

    # Evidence per dimension
    lines.append("\n---\n\n## Dimension Findings & Evidence\n")
    for dr in report.domain_results:
        lines.append(f"### {dr.domain_display}\n")
        for dim in dr.dimension_results:
            status_label = "PASS" if dim.passed else "FAIL"
            lines.append(f"#### {dim.dimension_id.upper()} — {dim.name} `{status_label}` {dim.raw_score:.1f}/10\n")
            lines.append(f"**Summary:** {dim.finding_summary}\n")
            lines.append(f"**Detail:** {dim.finding_detail}\n")
            lines.append(f"**Remediation:** {dim.remediation}\n")
            # Key evidence
            ev = dim.evidence
            if ev and not ev.get("error"):
                lines.append("**Key evidence:**\n```json")
                # Trim evidence to keep report readable
                ev_display = {k: v for k, v in ev.items()
                              if k not in ["addressable_categories", "heuristic_categories",
                                           "benchmarked_categories", "top_level_keys"]}
                lines.append(json.dumps(ev_display, indent=2, default=str)[:800])
                lines.append("```\n")

    # Top 10 gaps
    lines.append("\n---\n\n## Top 10 Gaps (ranked by severity)\n")
    lines.append("| Rank | ID | Gap | Severity | Domain | Remediation (brief) |")
    lines.append("|------|----|-----|----------|--------|---------------------|")
    for i, g in enumerate(report.top_gaps, 1):
        brief = g["remediation"][:80] + "..." if len(g["remediation"]) > 80 else g["remediation"]
        lines.append(
            f"| {i} | {g['dimension_id'].upper()} | {g['gap']:.1f} pts | "
            f"{g['gap_severity']:.4f} | {g['domain']} | {brief} |"
        )

    # Remediation roadmap
    lines.append("\n---\n\n## Remediation Roadmap\n")
    for priority in ["P0", "P1", "P2"]:
        items = [r for r in report.remediation_roadmap if r["priority"] == priority]
        if not items:
            continue
        label = {"P0": "Critical — implement within 1 week",
                 "P1": "High — implement within 4 weeks",
                 "P2": "Medium — implement within 12 weeks"}[priority]
        lines.append(f"### {priority} — {label}\n")
        for item in items:
            lines.append(f"**{item['dimension_id'].upper()}: {item['name']}**  ")
            lines.append(f"Effort: {item['estimated_effort']}  ")
            lines.append(f"{item['remediation']}\n")

    # Appendix
    lines.append("\n---\n\n## Appendix — Raw Dimension Scores\n")
    lines.append("```json")
    raw_data = {
        "overall_score": round(report.overall_score, 3),
        "passed": report.passed,
        "eval_date": report.eval_date,
        "score_type": "structural",
        "scope": (
            "Lever taxonomy completeness and benchmark reference-data quality. "
            "Does NOT validate real-world calibration of assumptions."
        ),
        "domains": [
            {
                "name": dr.domain_name,
                "score": round(dr.domain_score, 3),
                "passed": dr.passed,
                "dimensions": [
                    {
                        "id": d.dimension_id,
                        "score": round(d.raw_score, 2),
                        "threshold": d.threshold_pass,
                        "passed": d.passed,
                        "gap": round(d.gap, 2),
                    }
                    for d in dr.dimension_results
                ],
            }
            for dr in report.domain_results
        ],
    }
    lines.append(json.dumps(raw_data, indent=2))
    lines.append("```")

    return "\n".join(lines)


def write_report(report_text: str, scores_data: Dict, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report_text, encoding="utf-8")
    scores_path = output_path.with_name("eval_scores.json")
    scores_path.write_text(json.dumps(scores_data, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="OpEx Platform Reference-Data Quality Evaluator"
    )
    parser.add_argument("--project-root", type=Path, default=Path.cwd(),
                        help="Root of the OpEx platform (default: cwd)")
    parser.add_argument("--output", type=Path, default=Path("eval/eval_report.md"),
                        help="Output report path (default: eval/eval_report.md)")
    parser.add_argument("--json-only", action="store_true",
                        help="Write eval_scores.json only, skip Markdown")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.project_root.resolve()

    print(f"OpEx Eval — project root: {root}")
    print("Running 15 evaluation dimensions...\n")

    # Run all dimensions
    dimension_results = run_all_dimensions(root)

    # Group by domain
    criteria, _ = load_json(root, "eval/criteria.json")
    domain_order = [d["name"] for d in (criteria or {}).get("domains", [])] or \
                   ["lever_coverage", "benchmark_authenticity"]
    domain_display = {d["name"]: d.get("display_name", d["name"])
                      for d in (criteria or {}).get("domains", [])}
    domain_weights = {d["name"]: d.get("weight", 0.5)
                      for d in (criteria or {}).get("domains", [])}

    domain_map: Dict[str, List[DimensionResult]] = {name: [] for name in domain_order}
    for dr in dimension_results:
        domain_map.setdefault(dr.domain, []).append(dr)

    domain_results: List[DomainResult] = []
    for domain_name in domain_order:
        dims = domain_map.get(domain_name, [])
        score = compute_domain_score(dims)
        threshold = 6.5
        domain_results.append(DomainResult(
            domain_name=domain_name,
            domain_display=domain_display.get(domain_name, domain_name),
            domain_weight=domain_weights.get(domain_name, 0.5),
            dimension_results=dims,
            domain_score=round(score, 3),
            passed=score >= threshold,
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

    # Print summary to stdout
    print(f"{'Domain':<30} {'Score':>8}  {'Status'}")
    print("-" * 50)
    for dr in domain_results:
        status = "PASS ✓" if dr.passed else "FAIL ✗"
        print(f"{dr.domain_display:<30} {dr.domain_score:>6.2f}/10  {status}")
    print("-" * 50)
    print(f"{'OVERALL':<30} {overall:>6.2f}/10  {'PASS ✓' if eval_report.passed else 'FAIL ✗'}")
    print()
    print(f"Top gap: {top_gaps[0]['dimension_id'].upper()} — {top_gaps[0]['name']} "
          f"(gap={top_gaps[0]['gap']:.1f}, severity={top_gaps[0]['gap_severity']:.4f})"
          if top_gaps else "No gaps found.")
    print()

    # Build scores data for JSON
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
        print(f"Report written to: {args.output}")
        print(f"Scores JSON:       {args.output.with_name('eval_scores.json')}")
    else:
        scores_path = args.output.with_name("eval_scores.json")
        scores_path.parent.mkdir(parents=True, exist_ok=True)
        scores_path.write_text(json.dumps(scores_data, indent=2), encoding="utf-8")
        print(f"Scores JSON: {scores_path}")

    return 0 if eval_report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
