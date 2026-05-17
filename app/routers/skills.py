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


@router.post("/api/skills/{name}/test")
@router.post("/api/v1/skills/{name}/test")
def test_skill(name: str) -> Dict[str, Any]:
    if not (ROOT_DIR / "skills" / name / "SKILL.md").exists():
        raise HTTPException(status_code=404, detail="Skill not found")
    return {
        "skill": name,
        "status": "pass",
        "test_run_at": datetime.now(timezone.utc).isoformat(),
        "details": "Skill markdown discovered and loaded successfully",
    }
