from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

from app.config import ROOT_DIR
from app.opar.plan import get_skill_dep_map
from app.schemas import SkillCreateRequest, SkillDiscoverRequest, SkillEditRequest, SkillStructuredCreateRequest
from app.services.compliance import append_audit_event
from app.skills.dispatch import registered_skills
from app.skills.registry import discover_skills, get_skill_meta, parse_skill_md
from app.skills.taxonomy import TIER_MAP

router = APIRouter()


def _compose_skill_md(payload: SkillStructuredCreateRequest) -> str:
    inputs_block = "\n".join(f"- `{inp}`" for inp in payload.inputs) or "- *(none)*"
    outputs_block = "\n".join(f"- `{field}`" for field in payload.output_fields) or "- `result`"
    return (
        f"---\n"
        f"name: {payload.name}\n"
        f"description: \"{payload.description.replace(chr(34), chr(39))}\"\n"
        f"kind: {payload.kind}\n"
        f"runtime: {payload.runtime}\n"
        f"discoverable: {'true' if payload.discoverable else 'false'}\n"
        f"weight: {payload.weight}\n"
        f"version: 0.1.0\n"
        f"status: active\n"
        f"---\n\n"
        f"# {payload.name.replace('-', ' ').title()}\n\n"
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
    path = ROOT_DIR / "skills" / name / "SKILL.md"
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
    path = ROOT_DIR / "skills" / name / "SKILL.md"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Skill not found")
    path.write_text(payload.content, encoding="utf-8")
    append_audit_event("skill_updated", data={"skill": name})
    return {"status": "updated"}


@router.post("/api/skills")
@router.post("/api/v1/skills")
def create_skill(payload: SkillCreateRequest) -> Dict[str, str]:
    skill_dir = ROOT_DIR / "skills" / payload.name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_path = skill_dir / "SKILL.md"
    if skill_path.exists():
        raise HTTPException(status_code=400, detail="Skill already exists")
    skill_path.write_text(payload.content, encoding="utf-8")
    append_audit_event("skill_created", data={"skill": payload.name})
    return {"status": "created", "name": payload.name}


@router.post("/api/skills/structured")
@router.post("/api/v1/skills/structured")
def create_structured_skill(payload: SkillStructuredCreateRequest) -> Dict[str, str]:
    from app.skills.manifest import append_manifest_entry
    from app.skills.taxonomy import TIER_MAP

    content = _compose_skill_md(payload)
    result = create_skill(SkillCreateRequest(name=payload.name, content=content))
    append_manifest_entry({
        "name": payload.name,
        "tier": TIER_MAP.get(payload.name, "Other"),
        "parallel_group": payload.parallel_group,
        "depends_on": list(payload.depends_on or payload.inputs),
        "estimated_tokens": 400,
        "kind": payload.kind,
        "weight": payload.weight,
        "runtime": payload.runtime,
        "status": "active",
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
    from app.skills.discovery import clear_discovery_index

    clear_discovery_index()
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
    if not (ROOT_DIR / "skills" / name / "SKILL.md").exists():
        raise HTTPException(status_code=404, detail="Skill not found")
    from app.skills.dispatch import invoke_skill

    ts = datetime.now(timezone.utc).isoformat()
    meta = get_skill_meta(name)
    is_declarative = bool(meta and meta.get("runtime") == "declarative")
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
        ok = isinstance(output, dict)
        return {
            "skill": name,
            "status": "pass" if ok else "fail",
            "test_run_at": ts,
            "degraded_reason": degraded,
            "output_keys": sorted(output.keys())[:12] if ok else [],
            "runtime": meta.get("runtime") if meta else "python",
            "details": (
                f"Executed on synthetic data; returned {len(output)} output field(s)."
                if ok else "Handler returned a non-dict result."
            ),
        }
    except Exception as exc:
        return {
            "skill": name,
            "status": "fail",
            "test_run_at": ts,
            "error": str(exc)[:300],
            "details": "Handler raised an exception on synthetic data.",
        }
