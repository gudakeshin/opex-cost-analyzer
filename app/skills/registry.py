"""Full SKILL.md parsing and skill catalog metadata."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List

from app.config import SKILLS_DIR
from app.models import SkillMetadata


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _parse_frontmatter(text: str) -> Dict[str, str]:
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}
    out: Dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        out[key.strip()] = val.strip().strip('"').strip("'")
    return out


def _extract_section(text: str, heading: str) -> str:
    pattern = re.compile(rf"^#{{1,3}}\s*{re.escape(heading)}\s*$", re.MULTILINE | re.IGNORECASE)
    m = pattern.search(text)
    if not m:
        return ""
    start = m.end()
    next_h = re.search(r"^#{1,3}\s+", text[start:], re.MULTILINE)
    end = start + next_h.start() if next_h else len(text)
    body = text[start:end].strip()
    return body[:1200] if len(body) > 1200 else body


def parse_skill_md(skill_md: Path) -> Dict[str, Any]:
    """Parse full SKILL.md: frontmatter, purpose, when-to-use, methodology summary."""
    text = skill_md.read_text(encoding="utf-8")
    fm = _parse_frontmatter(text)
    first_heading = ""
    for line in text.splitlines():
        if line.startswith("# "):
            first_heading = line.removeprefix("# ").strip()
            break

    purpose = _extract_section(text, "What You Do") or _extract_section(text, "Purpose")
    when_to_use = fm.get("description") or purpose[:400]
    methodology = _extract_section(text, "Step-by-Step Workflow") or _extract_section(text, "Methodology")

    return {
        "name": fm.get("name") or skill_md.parent.name,
        "description": fm.get("description") or first_heading,
        "purpose": purpose,
        "when_to_use": when_to_use,
        "methodology_summary": methodology,
        "version": fm.get("version") or "0.1.0",
        "status": fm.get("status") or "active",
    }


def parse_skill_description(skill_md: Path) -> str:
    meta = parse_skill_md(skill_md)
    return str(meta.get("description") or meta.get("name") or "")


def discover_skills() -> List[SkillMetadata]:
    if not SKILLS_DIR.exists():
        return []
    out: List[SkillMetadata] = []
    for file_path in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        meta = parse_skill_md(file_path)
        out.append(
            SkillMetadata(
                name=meta["name"],
                path=str(file_path),
                description=meta["description"],
                version=meta.get("version") or "0.1.0",
                status=meta.get("status") or "active",
            )
        )
    return out


def discover_skills_rich() -> List[Dict[str, Any]]:
    """Return full metadata dicts for semantic skill discovery indexing."""
    if not SKILLS_DIR.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for file_path in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        meta = parse_skill_md(file_path)
        meta["path"] = str(file_path)
        rows.append(meta)
    return rows
