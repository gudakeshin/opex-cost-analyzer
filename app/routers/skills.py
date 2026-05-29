from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

from app.config import ROOT_DIR
from app.schemas import SkillCreateRequest, SkillEditRequest
from app.services.compliance import append_audit_event
from app.skills.registry import discover_skills

router = APIRouter()


@router.get("/api/skills")
@router.get("/api/v1/skills")
def list_skills() -> List[Dict[str, Any]]:
    return [x.model_dump() for x in discover_skills()]


@router.get("/api/skills/{name}")
@router.get("/api/v1/skills/{name}")
def get_skill(name: str) -> Dict[str, Any]:
    path = ROOT_DIR / "skills" / name / "SKILL.md"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Skill not found")
    return {"name": name, "path": str(path), "content": path.read_text(encoding="utf-8")}


@router.put("/api/skills/{name}")
@router.put("/api/v1/skills/{name}")
def update_skill(name: str, payload: SkillEditRequest) -> Dict[str, str]:
    path = ROOT_DIR / "skills" / name / "SKILL.md"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Skill not found")
    path.write_text(payload.content, encoding="utf-8")
    append_audit_event(f"skill_updated skill={name}")
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
    append_audit_event(f"skill_created skill={payload.name}")
    return {"status": "created", "name": payload.name}


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
        "savings-modeler", "value-bridge-calculator",
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
    from app.skills.dispatch import invoke_skill, registered_skills

    ts = datetime.now(timezone.utc).isoformat()
    if name not in registered_skills():
        # SKILL.md exists but there is no executable dispatch handler (e.g. a
        # documentation-only or differently-dispatched skill like model-contextualizer).
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
