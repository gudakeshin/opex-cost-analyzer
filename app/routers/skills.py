from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

from app.opar.plan import get_skill_dep_map
from app.schemas import SkillCreateRequest, SkillDiscoverRequest, SkillEditRequest, SkillStructuredCreateRequest
from app.services.compliance import append_audit_event
from app.skills.dispatch import registered_skills
from app.skills.registry import (
    bump_version,
    compose_frontmatter,
    discover_skills,
    get_skill_meta,
    parse_skill_md,
    validate_skill_md_content,
)
from app.skills.taxonomy import TIER_MAP
from app.skills.validation import (
    FAIL_DEGRADED_REASONS,
    resolve_skill_md_path,
    validate_depends_on,
    validate_skill_slug_http,
)

router = APIRouter()


def _invalidate_discovery_index() -> None:
    from app.skills.discovery import clear_discovery_index

    clear_discovery_index()


def _compose_skill_md(payload: SkillStructuredCreateRequest) -> str:
    inputs_block = "\n".join(f"- `{inp}`" for inp in payload.inputs) or "- *(none)*"
    outputs_block = "\n".join(f"- `{field}`" for field in payload.output_fields) or "- `result`"
    frontmatter = compose_frontmatter({
        "name": payload.name,
        "description": payload.description,
        "kind": payload.kind,
        "runtime": payload.runtime,
        "discoverable": payload.discoverable,
        "weight": payload.weight,
        "version": "0.1.0",
        "status": "draft",
    })
    title = payload.name.replace("-", " ").title()
    return (
        f"{frontmatter}\n"
        f"# {title}\n\n"
        f"{payload.instruction_prompt.strip()}\n\n"
        f"## Inputs\n\n{inputs_block}\n\n"
        f"## Outputs\n\n{outputs_block}\n"
    )


def _skill_execution_status(name: str) -> str:
    meta = get_skill_meta(name)
    if not meta:
        return "missing"
    runtime = meta.get("runtime") or "python"
    if name in registered_skills():
        return "python" if runtime == "python" else "declarative"
    if runtime == "declarative":
        return "declarative"
    return "doc-only"


def _evaluate_smoke_result(
    output: Any,
    degraded: str | None,
    *,
    is_declarative: bool,
) -> tuple[str, str]:
    if is_declarative and degraded == "provider_disabled":
        return "skipped", "LLM provider disabled — declarative skill not executed."
    if not is_declarative and degraded in {"provider_disabled", "provider_unavailable"}:
        return "skipped", f"LLM provider unavailable ({degraded}) — Python handler smoke-run skipped."
    if degraded in FAIL_DEGRADED_REASONS:
        return "fail", f"Degraded execution: {degraded}"
    if not isinstance(output, dict):
        return "fail", "Handler returned a non-dict result."
    if len(output) == 0:
        return "fail", "Handler returned an empty output dict."
    return "pass", f"Executed on synthetic data; returned {len(output)} output field(s)."


@router.get("/api/skills")
@router.get("/api/v1/skills")
def list_skills() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for item in discover_skills():
        row = item.model_dump()
        row["tier"] = TIER_MAP.get(item.name, "Other")
        row["execution_status"] = _skill_execution_status(item.name)
        rows.append(row)
    return rows


@router.get("/api/skills/{name}")
@router.get("/api/v1/skills/{name}")
def get_skill(name: str) -> Dict[str, Any]:
    validate_skill_slug_http(name)
    path = resolve_skill_md_path(name)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Skill not found")
    meta = parse_skill_md(path)
    return {
        "name": name,
        "path": str(path),
        "content": path.read_text(encoding="utf-8"),
        **{k: meta[k] for k in ("kind", "runtime", "discoverable", "weight", "tier", "inputs") if k in meta},
    }


@router.put("/api/skills/{name}")
@router.put("/api/v1/skills/{name}")
def update_skill(name: str, payload: SkillEditRequest) -> Dict[str, str]:
    validate_skill_slug_http(name)
    path = resolve_skill_md_path(name)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Skill not found")
    try:
        fm = validate_skill_md_content(payload.content, registered_name=name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if name in registered_skills() and str(fm.get("runtime") or "python") != "python":
        raise HTTPException(
            status_code=400,
            detail="Registered Python skills must retain runtime: python in frontmatter",
        )
    fm["version"] = bump_version(str(fm.get("version") or "0.1.0"))
    body = payload.content
    m = re.match(r"^---\s*\n.*?\n---\s*\n", body, re.DOTALL)
    if m:
        rest = body[m.end():]
        body = compose_frontmatter(fm) + "\n" + rest.lstrip("\n")
    path.write_text(body, encoding="utf-8")
    _invalidate_discovery_index()
    append_audit_event("skill_updated", data={"skill": name, "version": fm["version"]})
    return {"status": "updated", "version": fm["version"]}


@router.post("/api/skills")
@router.post("/api/v1/skills")
def create_skill(payload: SkillCreateRequest) -> Dict[str, str]:
    skill_dir = resolve_skill_md_path(payload.name).parent
    skill_path = skill_dir / "SKILL.md"
    if skill_path.exists():
        raise HTTPException(status_code=400, detail="Skill already exists")
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_path.write_text(payload.content, encoding="utf-8")
    _invalidate_discovery_index()
    append_audit_event("skill_created", data={"skill": payload.name})
    return {"status": "created", "name": payload.name}


@router.post("/api/skills/structured")
@router.post("/api/v1/skills/structured")
def create_structured_skill(payload: SkillStructuredCreateRequest) -> Dict[str, str]:
    from app.skills.manifest import append_manifest_entry

    deps = validate_depends_on(payload.depends_on)
    content = _compose_skill_md(payload)
    result = create_skill(SkillCreateRequest(name=payload.name, content=content))
    append_manifest_entry({
        "name": payload.name,
        "tier": TIER_MAP.get(payload.name, "Other"),
        "parallel_group": payload.parallel_group,
        "depends_on": deps,
        "estimated_tokens": 400,
        "kind": payload.kind,
        "weight": payload.weight,
        "runtime": payload.runtime,
        "status": "draft",
    })
    return result


@router.post("/api/skills/discover")
@router.post("/api/v1/skills/discover")
def discover_skills_api(payload: SkillDiscoverRequest) -> Dict[str, Any]:
    from app.skills.discovery import discover_relevant_skills

    hits = discover_relevant_skills(payload.query, k=payload.k, kind=payload.kind)
    return {"query": payload.query, "results": hits}


@router.post("/api/skills/reindex")
@router.post("/api/v1/skills/reindex")
def reindex_skills() -> Dict[str, str]:
    _invalidate_discovery_index()
    append_audit_event("skill_catalog_reindexed")
    return {"status": "reindexed"}


@router.get("/api/skills/catalog/dependencies")
@router.get("/api/v1/skills/catalog/dependencies")
def skill_dependencies() -> Dict[str, Any]:
    dep_map = get_skill_dep_map()
    return {
        "skills": [
            {"name": name, "parallel_group": group, "depends_on": deps}
            for name, (group, deps, _tokens) in dep_map.items()
        ]
    }


def _smoke_context():
    """Build a small synthetic SkillContext and pre-seed the deterministic core
    chain so dependent skills have the prior results they read."""
    from app.models import NormalizedSpendLine
    from app.skills.dispatch import SkillContext, invoke_skill

    samples = [
        ("Cloudvendor Pvt Ltd", "Cloud hosting", 1_200_000.0, "IT_SOFTWARE", "IT Software & Licenses", "actual"),
        ("Cloudvendor Pvt Ltd", "Cloud hosting (budget)", 1_000_000.0, "IT_SOFTWARE", "IT Software & Licenses", "budget"),
        ("Advisory Partners LLP", "Management consulting", 800_000.0, "PROF_SERVICES", "Professional Services", "actual"),
        ("Officespace Realty", "Office lease", 650_000.0, "FACILITIES", "Facilities & Real Estate", "actual"),
        ("TravelDesk India", "Corporate travel", 300_000.0, "TRAVEL", "Travel & Entertainment", "actual"),
    ]
    lines = [
        NormalizedSpendLine(
            row_id=i,
            supplier=s,
            description=d,
            amount=amt,
            category_id=cid,
            category_name=cn,
            amount_type=atype,
            business_unit="Corporate",
            spend_date="2025-06-15",
            payment_terms_days=30,
        )
        for i, (s, d, amt, cid, cn, atype) in enumerate(samples, start=1)
    ]
    manifest = {
        "industry": "technology",
        "annual_revenue": 500_000_000.0,
        "company_name": "SmokeTest Co",
        "session_id": "skill-smoke-test",
        "wacc": 0.12,
        "effective_tax_rate": 0.25,
    }
    ctx = SkillContext(
        lines=lines,
        docs_text=["Operating model notes for smoke test."],
        manifest=manifest,
        prior_results={},
        user_message="run analysis",
        headcount=500.0,
    )
    for dep in (
        "spend-profiler", "document-contextualizer", "internal-benchmarker",
        "peer-benchmarker", "heuristic-analyzer", "root-cause-analyzer",
        "savings-modeler", "value-bridge-calculator", "evidence-gatherer",
    ):
        try:
            out, _ = invoke_skill(dep, ctx)
            ctx.prior_results[dep] = out
        except Exception:
            pass
    return ctx


@router.post("/api/skills/{name}/test")
@router.post("/api/v1/skills/{name}/test")
def test_skill(name: str) -> Dict[str, Any]:
    validate_skill_slug_http(name)
    if not resolve_skill_md_path(name).exists():
        raise HTTPException(status_code=404, detail="Skill not found")
    from app.skills.dispatch import invoke_skill

    ts = datetime.now(timezone.utc).isoformat()
    meta = get_skill_meta(name) or {}
    is_declarative = bool(meta.get("runtime") == "declarative")
    if name not in registered_skills() and not is_declarative:
        return {
            "skill": name,
            "status": "skipped",
            "test_run_at": ts,
            "details": "Documentation-only skill — no executable dispatch handler to smoke-run.",
        }

    ctx = _smoke_context()
    try:
        output, degraded = invoke_skill(name, ctx)
        status, details = _evaluate_smoke_result(output, degraded, is_declarative=is_declarative)
        return {
            "skill": name,
            "status": status,
            "test_run_at": ts,
            "degraded_reason": degraded,
            "output_keys": sorted(output.keys())[:12] if isinstance(output, dict) else [],
            "runtime": meta.get("runtime") or "python",
            "details": details,
        }
    except Exception as exc:
        return {
            "skill": name,
            "status": "fail",
            "test_run_at": ts,
            "error": str(exc)[:300],
            "details": "Handler raised an exception on synthetic data.",
        }


@router.post("/api/skills/{name}/activate")
@router.post("/api/v1/skills/{name}/activate")
def activate_skill(name: str) -> Dict[str, str]:
    validate_skill_slug_http(name)
    path = resolve_skill_md_path(name)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Skill not found")

    test_result = test_skill(name)
    if test_result.get("status") != "pass":
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Skill must pass smoke test before activation",
                "test_status": test_result.get("status"),
                "details": test_result.get("details"),
            },
        )

    text = path.read_text(encoding="utf-8")
    fm = parse_skill_md(path)
    m = re.match(r"^---\s*\n.*?\n---\s*\n", text, re.DOTALL)
    if not m:
        raise HTTPException(status_code=400, detail="SKILL.md missing frontmatter")
    rest = text[m.end():]
    frontmatter_keys = (
        "name", "description", "kind", "runtime", "discoverable", "weight", "version", "status",
    )
    updated_fm = {k: fm[k] for k in frontmatter_keys if k in fm}
    updated_fm["status"] = "active"
    path.write_text(compose_frontmatter(updated_fm) + "\n" + rest.lstrip("\n"), encoding="utf-8")

    from app.skills.manifest import update_manifest_skill

    if update_manifest_skill(name, status="active") is None:
        from app.skills.manifest import append_manifest_entry

        append_manifest_entry({
            "name": name,
            "tier": TIER_MAP.get(name, "Other"),
            "parallel_group": 8,
            "depends_on": [],
            "estimated_tokens": 400,
            "kind": fm.get("kind") or "analysis",
            "weight": fm.get("weight") or "light",
            "runtime": fm.get("runtime") or "declarative",
            "status": "active",
        })

    _invalidate_discovery_index()
    append_audit_event("skill_activated", data={"skill": name})
    return {"status": "activated", "name": name}
