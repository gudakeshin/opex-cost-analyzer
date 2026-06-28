"""Analysis Workbench — compose, validate, run, and persist à-la-carte analysis runs.

The chat path (observe → plan → act → reflect) maps ONE intent to a fixed skill
bundle and overwrites a single session analysis blob. The Workbench exposes the
same underlying skill engine as *user-composed* runs: pick any analyses, edit
assumptions, run, and keep each run as a discrete card on a per-engagement board
that can be branched, chained, and compared.

Design rule — *no hard boundaries unless logically inconsistent*: any skill
combination the canonical DAG (`_DEP_MAP`) can wire is allowed; missing
prerequisites are auto-added (not blocked), and only genuinely impossible runs
(a skill whose required input data is absent and underivable) are blocked.

Reuses:
  * app.skills.registry.discover_skills              — catalog metadata (SKILL.md)
  * app.opar.plan.get_skill_dep_map / resolve_skill_dependencies / build_plan_from_skills
  * app.opar.act.act                                 — the parallel executor
  * app.services.spend_base.load_authoritative_spend_lines — session data/manifest
  * app.memory.MemoryStore (new "workbench_run" scope) — run persistence
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List

from app.config import MEMORY_DIR, logger
from app.memory import MemoryStore
from app.opar.act import act
from app.opar.models import ObserveContext
from app.opar.plan import build_plan_from_skills, get_extended_skill_dep_map, resolve_skill_dependencies
from app.skills.registry import discover_skills_rich
from app.skills.taxonomy import TIER_MAP as _TIER_MAP
from app.storage import read_json

_memory = MemoryStore()
_RUN_SCOPE = "workbench_run"

# ---------------------------------------------------------------------------
# Catalog metadata
# ---------------------------------------------------------------------------

# Group-0 security skills are auto-injected by the planner when tabular spend is
# present (pii-stripper → data-classifier → llm-context-builder); they are not
# user-selectable analyses, so the catalog is built from _DEP_MAP keys only.

_TIER_ORDER: List[str] = [
    "Diagnostics",
    "Benchmarking",
    "Working Capital",
    "Savings & Value",
    "Strategic",
    "Compliance & India",
    "Enterprise Data",
    "Outputs & Reporting",
    "Other",
]

# Editable assumptions — keys map 1:1 onto manifest fields read by SkillContext
# (see app/opar/act.py + app/skills/dispatch.py), so an override dict of these
# keys flows straight into every skill without per-skill plumbing.
ASSUMPTION_FIELDS: List[Dict[str, Any]] = [
    {"key": "wacc", "label": "Discount rate (WACC)", "type": "percent", "default": 0.10},
    {"key": "effective_tax_rate", "label": "Effective tax rate", "type": "percent", "default": 0.0},
    {"key": "planning_horizon_years", "label": "Planning horizon (years)", "type": "int", "default": 3},
    {"key": "annual_revenue", "label": "Annual revenue", "type": "number"},
    {"key": "headcount", "label": "Headcount", "type": "number"},
    {"key": "industry", "label": "Industry / peer set", "type": "text"},
    {"key": "reporting_currency", "label": "Reporting currency", "type": "text", "default": "INR"},
]

# Which assumptions each skill actually consumes — drives UI highlighting only.
_SKILL_PARAMS: Dict[str, List[str]] = {
    "heuristic-analyzer": ["annual_revenue", "headcount", "reporting_currency"],
    "peer-benchmarker": ["industry", "annual_revenue"],
    "payment-terms-optimizer": ["wacc", "industry"],
    "savings-modeler": ["wacc", "effective_tax_rate", "planning_horizon_years", "industry"],
    "value-bridge-calculator": ["wacc", "effective_tax_rate"],
    "scenario-modeler": ["wacc", "effective_tax_rate"],
    "value-to-shareholder-bridge": ["wacc", "annual_revenue"],
    "indian-tax-optimizer": ["effective_tax_rate"],
    "cost-to-serve-analyzer": ["annual_revenue", "headcount"],
    "zbb-modeler": ["annual_revenue"],
}

# HARD requirements — external data a skill is meaningless without and that
# cannot be derived from spend lines. Blocks ONLY when the user explicitly
# selected the skill (these analyses are terminal — never auto-added as deps).
_SKILL_DATA_REQUIREMENTS: Dict[str, List[str]] = {
    "cost-to-serve-analyzer": ["segment_revenue"],
    "consolidation-analyzer": ["entity_tree"],
    "gstr-reconciler": ["gstr_2a_data"],
}

# SOFT requirements — the skill still runs but degrades without the input. If the
# user selected it, we warn and keep it; if it was only auto-added as a dependency
# we drop it (mirrors the chat planner's `include_heuristic = has_annual_revenue`).
_SKILL_SOFT_REQUIREMENTS: Dict[str, str] = {
    "heuristic-analyzer": "annual_revenue",
}

_REQUIREMENT_MESSAGES: Dict[str, str] = {
    "annual_revenue": "needs annual revenue — set it in the assumptions panel.",
    "segment_revenue": "needs per-segment revenue, which this session does not have.",
    "entity_tree": "needs a multi-entity structure (entity tree), which this session does not have.",
    "gstr_2a_data": "needs GSTR-2A/2B data to reconcile against, which this session does not have.",
}


def _selectable_skills() -> Dict[str, tuple]:
    """All user-selectable analyses (canonical DAG + manifest declarative)."""
    return get_extended_skill_dep_map()


def workbench_catalog() -> Dict[str, Any]:
    """Browsable catalog: every selectable analysis with tier, deps, params, and
    data requirements, plus the editable assumption schema. Tiers are ordered."""
    dep_map = _selectable_skills()
    descriptions = {
        m["name"]: m.get("description", "")
        for m in discover_skills_rich()
        if isinstance(m, dict) and m.get("name")
    }
    skills: List[Dict[str, Any]] = []
    for name, (group, deps, _tokens) in dep_map.items():
        skills.append(
            {
                "name": name,
                "tier": _TIER_MAP.get(name, "Other"),
                "description": descriptions.get(name, ""),
                "parallel_group": group,
                "depends_on": deps,
                "params": _SKILL_PARAMS.get(name, []),
                "data_requirements": _SKILL_DATA_REQUIREMENTS.get(name, []),
                "degrades_without": (
                    [_SKILL_SOFT_REQUIREMENTS[name]] if name in _SKILL_SOFT_REQUIREMENTS else []
                ),
            }
        )
    skills.sort(key=lambda s: (_TIER_ORDER.index(s["tier"]) if s["tier"] in _TIER_ORDER else 99, s["name"]))
    return {
        "skills": skills,
        "tiers": _TIER_ORDER,
        "assumptions": ASSUMPTION_FIELDS,
    }


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------

def _load_session(session_id: str) -> tuple[list, list, dict]:
    """Return (spend_lines, docs_text, manifest) — the same loader act() uses."""
    from app.services.spend_base import load_authoritative_spend_lines

    return load_authoritative_spend_lines(session_id)


def _has_requirement(effective: Dict[str, Any], key: str) -> bool:
    value = effective.get(key)
    if key == "annual_revenue":
        return bool(value) and float(value or 0) > 0
    return bool(value)


# ---------------------------------------------------------------------------
# Validation — the consistency engine
# ---------------------------------------------------------------------------

def validate_workbench_run(
    selected_skills: List[str],
    session_id: str,
    overrides: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Validate a composed run.

    Returns ``{selected_skills, resolved_skills, added_deps, warnings,
    blocking_errors, blocked}``. Auto-resolves dependencies (reported, never
    blocked); blocks only when a selected skill's required input data is absent;
    warns for soft mismatches (unknown skill, no spend data).
    """
    overrides = overrides or {}
    dep_map = _selectable_skills()
    selectable = set(dep_map)

    unknown = [s for s in selected_skills if s not in selectable]
    valid_selected = [s for s in selected_skills if s in selectable]
    selected_set = set(valid_selected)
    resolved = resolve_skill_dependencies(valid_selected, extended=True)

    try:
        lines, _docs, manifest = _load_session(session_id)
    except Exception as exc:
        logger.debug('"workbench_validate session_load_failed session=%s err=%s"', session_id, exc)
        lines, manifest = [], {}

    effective = dict(manifest)
    for key, value in overrides.items():
        if value is not None:
            effective[key] = value

    warnings: List[Dict[str, str]] = []
    blocking_errors: List[Dict[str, str]] = []

    for skill in unknown:
        warnings.append({
            "skill": skill,
            "code": "unknown_skill",
            "message": f"'{skill}' is not a runnable analysis and was ignored.",
        })

    if not lines:
        warnings.append({
            "skill": "spend-profiler",
            "code": "no_spend_data",
            "message": "No spend data found in this session — results may be empty until data is uploaded.",
        })

    # Soft requirements: keep (warn) when user-selected; drop (warn) when only an
    # auto-added dependency — mirroring the chat planner's conditional inclusion.
    for skill, req in _SKILL_SOFT_REQUIREMENTS.items():
        if skill not in resolved or _has_requirement(effective, req):
            continue
        if skill in selected_set:
            warnings.append({
                "skill": skill,
                "code": f"degraded_{req}",
                "message": f"{skill} {_REQUIREMENT_MESSAGES.get(req, f'is more accurate with {req}.')} It will run with reduced confidence.",
            })
        else:
            resolved = [s for s in resolved if s != skill]
            warnings.append({
                "skill": skill,
                "code": f"skipped_{req}",
                "message": f"Skipped {skill} (auto-added) — {_REQUIREMENT_MESSAGES.get(req, f'needs {req}.')}",
            })

    # Hard requirements: block only when the user explicitly selected the skill.
    for skill in valid_selected:
        for req in _SKILL_DATA_REQUIREMENTS.get(skill, []):
            if not _has_requirement(effective, req):
                blocking_errors.append({
                    "skill": skill,
                    "code": f"missing_{req}",
                    "message": f"{skill} {_REQUIREMENT_MESSAGES.get(req, f'needs {req}.')}",
                    "fixable_with": req,
                })

    added_deps = [s for s in resolved if s not in selected_set]
    return {
        "selected_skills": valid_selected,
        "resolved_skills": resolved,
        "added_deps": added_deps,
        "warnings": warnings,
        "blocking_errors": blocking_errors,
        "blocked": bool(blocking_errors),
    }


# ---------------------------------------------------------------------------
# Headline extraction (for board cards)
# ---------------------------------------------------------------------------

def _extract_headline(skill_outputs: Dict[str, Any]) -> Dict[str, Any]:
    headline: Dict[str, Any] = {}
    profile = skill_outputs.get("spend-profiler") or {}
    if isinstance(profile, dict) and profile.get("total_spend") is not None:
        headline["total_spend"] = profile.get("total_spend")

    bridge = skill_outputs.get("value-bridge-calculator") or {}
    bands = bridge.get("confidence_bands") if isinstance(bridge, dict) else None
    if isinstance(bands, dict):
        headline["savings_low"] = bands.get("low")
        headline["savings_mid"] = bands.get("mid")
        headline["savings_high"] = bands.get("high")

    savings = skill_outputs.get("savings-modeler") or {}
    inits = savings.get("initiatives") if isinstance(savings, dict) else None
    if isinstance(inits, list) and inits:
        headline["initiative_count"] = len(inits)
        npv = 0.0
        for item in inits:
            if isinstance(item, dict):
                npv += float((item.get("net_savings") or {}).get("npv_aftertax") or 0.0)
        if npv:
            headline["npv"] = round(npv, 2)
        summary = savings.get("summary") if isinstance(savings, dict) else None
        if isinstance(summary, dict) and summary.get("portfolio_ebitda_impact_bps") is not None:
            headline["ebitda_bps"] = summary.get("portfolio_ebitda_impact_bps")
    return headline


def _light_reflect_summary(skill_outputs: Dict[str, Any], run_name: str) -> str:
    """Deterministic narrative stub — no LLM, no session overwrite."""
    parts: List[str] = [f"Workbench run «{run_name}» completed."]
    profile = skill_outputs.get("spend-profiler") or {}
    if isinstance(profile, dict) and profile.get("total_spend"):
        parts.append(f"Spend base analysed: ₹{float(profile['total_spend']):,.0f}.")
    bench = skill_outputs.get("peer-benchmarker") or {}
    if isinstance(bench, dict) and bench.get("benchmark_source"):
        parts.append(f"Benchmarks: {bench.get('benchmark_source')}.")
    savings = skill_outputs.get("savings-modeler") or {}
    inits = savings.get("initiatives") if isinstance(savings, dict) else None
    if isinstance(inits, list) and inits:
        parts.append(f"{len(inits)} savings initiative(s) modelled.")
    critique = skill_outputs.get("sme-critique") or {}
    if isinstance(critique, dict) and critique.get("overall_verdict"):
        parts.append(f"SME verdict: {critique.get('overall_verdict')}.")
    return " ".join(parts)


def promote_run_initiatives(run_id: str) -> Dict[str, Any]:
    """Push savings-modeler initiatives from a completed workbench run into the pipeline store."""
    from app.services.pipeline import create_initiative

    run = get_run(run_id)
    if not run:
        raise ValueError("Run not found")
    if run.get("status") != "complete":
        raise ValueError("Run must be complete before promotion")
    savings = (run.get("skill_outputs") or {}).get("savings-modeler") or {}
    inits = savings.get("initiatives") if isinstance(savings, dict) else None
    if not isinstance(inits, list) or not inits:
        raise ValueError("No savings-modeler initiatives in this run")

    promoted: List[Dict[str, Any]] = []
    bench = (run.get("skill_outputs") or {}).get("peer-benchmarker") or {}
    provenance = {
        "workbench_run_id": run_id,
        "overrides": run.get("overrides") or {},
        "benchmark_source": bench.get("benchmark_source") if isinstance(bench, dict) else None,
    }
    for item in inits:
        if not isinstance(item, dict):
            continue
        gross = item.get("gross_savings") or {}
        net = item.get("net_savings") or {}
        gross_y1 = float(
            item.get("gross_savings_y1")
            or gross.get("y1")
            or net.get("year1")
            or 0
        )
        p50 = float(
            item.get("p50_savings")
            or gross.get("y1")
            or net.get("annual_run_rate")
            or 0
        )
        net_npv = float(
            item.get("net_npv")
            or net.get("npv_10pct")
            or net.get("npv_aftertax")
            or 0
        )
        candidate = {"p50_savings": p50, "gross_savings_y1": gross_y1, "net_npv": net_npv}
        from app.services.pipeline import _positive_savings

        if not _positive_savings(candidate):
            continue
        session_id = run.get("session_id")
        engagement_id = _resolve_engagement_id(session_id, run.get("engagement_id"))
        payload = {
            "session_id": session_id,
            "engagement_id": engagement_id,
            "analysis_id": run_id,
            "category": item.get("category") or item.get("category_name") or "General",
            "lever": item.get("lever") or item.get("lever_name") or "cost_reduction",
            "root_cause": item.get("root_cause"),
            "gross_savings_y1": gross_y1,
            "net_npv": net_npv,
            "p50_savings": p50,
            "ebitda_bps": item.get("ebitda_bps"),
            "stage": "identified",
            "evidence": [{"type": "workbench_provenance", **provenance}],
        }
        promoted.append(create_initiative(payload))
    run["promoted_initiative_ids"] = [p.get("initiative_id") for p in promoted]
    save_run(run)
    return {"run_id": run_id, "promoted": promoted, "count": len(promoted)}


# ---------------------------------------------------------------------------
# Persistence — workbench_run MemoryStore scope, indexed per engagement
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def save_run(run: Dict[str, Any]) -> None:
    _memory.put(_RUN_SCOPE, run["run_id"], run)


def get_run(run_id: str) -> Dict[str, Any] | None:
    data = _memory.get(_RUN_SCOPE, run_id)
    return data or None


def delete_run(run_id: str) -> bool:
    if not get_run(run_id):
        return False
    _memory.delete(_RUN_SCOPE, run_id)
    return True


def list_runs(engagement_id: str | None = None, session_id: str | None = None) -> List[Dict[str, Any]]:
    """Return all runs, newest first, filtered by engagement and/or session."""
    runs_dir = MEMORY_DIR / _RUN_SCOPE
    out: List[Dict[str, Any]] = []
    if not runs_dir.exists():
        return out
    for f in runs_dir.glob("*.json"):
        data = read_json(f, {})
        if not data:
            continue
        if engagement_id and data.get("engagement_id") != engagement_id:
            continue
        if session_id and data.get("session_id") != session_id:
            continue
        out.append(data)
    out.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    return out


def _resolve_engagement_id(session_id: str, fallback: str | None) -> str:
    """Resolve the engagement a run belongs to (caller-supplied → manifest → memory).

    A caller-supplied id wins: the frontend passes a stable engagement, and a branch
    inherits its parent's board membership. We only fall back to the session manifest
    / memory when no id was supplied — the spend loader can auto-reassign the
    manifest's engagement_id mid-run, which would otherwise drift the board.
    """
    if fallback:
        return str(fallback)
    try:
        from app.routers._shared import read_manifest

        eid = read_manifest(session_id).get("engagement_id")
        if eid:
            return str(eid)
    except Exception:
        pass
    blob = _memory.get("session", session_id)
    if isinstance(blob, dict) and blob.get("engagement_id"):
        return str(blob["engagement_id"])
    return ""


def create_draft(
    *,
    session_id: str,
    name: str,
    selected_skills: List[str],
    overrides: Dict[str, Any] | None = None,
    seed_from_run_id: str | None = None,
    parent_run_id: str | None = None,
    engagement_id: str | None = None,
    user_id: str | None = None,
) -> Dict[str, Any]:
    return {
        "run_id": str(uuid.uuid4()),
        "engagement_id": _resolve_engagement_id(session_id, engagement_id),
        "session_id": session_id,
        "user_id": user_id or "",
        "name": name or "Untitled run",
        "selected_skills": list(selected_skills),
        "resolved_skills": [],
        "overrides": overrides or {},
        "seed_from_run_id": seed_from_run_id,
        "parent_run_id": parent_run_id,
        "status": "draft",
        "skill_outputs": {},
        "errors": {},
        "validation": {},
        "headline": {},
        "created_at": _now(),
        "completed_at": None,
    }


def branch_run(run_id: str, name: str | None = None) -> Dict[str, Any] | None:
    """Clone a run's composition (skills + overrides) into a fresh draft that
    records its parent for lineage. Outputs are NOT copied — the branch is re-run."""
    parent = get_run(run_id)
    if not parent:
        return None
    draft = create_draft(
        session_id=parent["session_id"],
        name=name or f"{parent.get('name', 'Run')} (branch)",
        selected_skills=parent.get("selected_skills", []),
        overrides=dict(parent.get("overrides") or {}),
        parent_run_id=run_id,
        engagement_id=parent.get("engagement_id"),
        user_id=parent.get("user_id"),
    )
    save_run(draft)
    return draft


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

async def run_workbench_run(
    run: Dict[str, Any],
    progress_callback: Callable[[str, str], None] | None = None,
    *,
    include_quality_gates: bool = False,
    include_light_reflect: bool = False,
) -> Dict[str, Any]:
    """Validate, execute, and persist a composed run. Mutates and returns *run*.

    Blocked runs (missing required data) are persisted with status ``failed`` and
    the blocking errors, without executing.
    """
    session_id = run["session_id"]
    overrides = run.get("overrides") or {}

    validation = validate_workbench_run(run.get("selected_skills", []), session_id, overrides)
    run["validation"] = validation
    run["resolved_skills"] = validation["resolved_skills"]

    if validation["blocked"]:
        run["status"] = "failed"
        run["completed_at"] = _now()
        save_run(run)
        if progress_callback:
            progress_callback("reflect", "Run blocked: required data is missing.")
        return run

    if not validation["resolved_skills"]:
        run["status"] = "failed"
        run["errors"] = {"_run": "No runnable analyses selected."}
        run["completed_at"] = _now()
        save_run(run)
        return run

    run["status"] = "running"
    save_run(run)

    # Seed prior outputs for chaining.
    seed_outputs: Dict[str, Any] = {}
    if run.get("seed_from_run_id"):
        prior = get_run(run["seed_from_run_id"])
        if prior and isinstance(prior.get("skill_outputs"), dict):
            seed_outputs = prior["skill_outputs"]

    try:
        _lines, _docs, _manifest = _load_session(session_id)
        has_spend = bool(_lines)
    except Exception:
        has_spend = True

    ctx = ObserveContext(
        user_message=run.get("name") or "Workbench analysis run",
        session_id=session_id,
        user_id=run.get("user_id") or "",
        turn_id=run["run_id"],
        engagement_id=run.get("engagement_id") or "",
        has_tabular_spend=has_spend,
        workbench_overrides=overrides,
        workbench_seed_outputs=seed_outputs,
    )
    exec_plan = build_plan_from_skills(
        validation["resolved_skills"],
        ctx,
        user_summary=run.get("name") or "Workbench analysis run",
        include_quality_gates=include_quality_gates,
    )
    run["resolved_skills"] = [t.skill_name for t in exec_plan.tasks]

    try:
        act_result = await act(exec_plan, ctx, progress_callback=progress_callback)
    except Exception as exc:
        logger.warning('"workbench_run_failed run=%s err=%s"', run["run_id"], exc)
        run["status"] = "failed"
        run["errors"] = {"_run": str(exc)[:300]}
        run["completed_at"] = _now()
        save_run(run)
        return run

    # Seeded outputs are part of the run's result set so chained cards stay complete.
    merged_outputs = dict(seed_outputs)
    merged_outputs.update(act_result.skill_outputs)
    run["skill_outputs"] = merged_outputs
    run["errors"] = act_result.errors
    run["degradation_reasons"] = getattr(act_result, "degradation_reasons", {}) or {}

    if include_light_reflect:
        run["reflect_summary"] = _light_reflect_summary(merged_outputs, run.get("name") or "")
        if progress_callback:
            progress_callback("reflect", "Light synthesis complete.")

    run["headline"] = _extract_headline(merged_outputs)
    run["status"] = "complete"
    run["completed_at"] = _now()
    save_run(run)
    return run
