from __future__ import annotations

from pathlib import Path
from typing import List

from app.config import SKILLS_DIR
from app.models import SkillMetadata


def parse_skill_description(skill_md: Path) -> str:
    first_heading = ""
    for line in skill_md.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            first_heading = line.removeprefix("# ").strip()
            break
    return first_heading


def discover_skills() -> List[SkillMetadata]:
    if not SKILLS_DIR.exists():
        return []
    out: List[SkillMetadata] = []
    for file_path in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        skill_name = file_path.parent.name
        out.append(
            SkillMetadata(
                name=skill_name,
                path=str(file_path),
                description=parse_skill_description(file_path),
            )
        )
    return out

