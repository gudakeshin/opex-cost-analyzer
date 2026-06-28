"""Full SKILL.md parsing and skill catalog metadata."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import SKILLS_DIR
from app.models import SkillMetadata
from app.skills.taxonomy import TIER_MAP, classify_kind, classify_weight

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


def _parse_bool(val: str | None, default: bool) -> bool:
    if val is None:
        return default
    return val.lower() in ("true", "yes", "1")


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


def _extract_inputs(text: str) -> List[str]:
    body = _extract_section(text, "Inputs")
    if not body:
        return []
    inputs: List[str] = []
    for line in body.splitlines():
        line = line.strip().lstrip("-").strip().strip("`")
        if line and not line.startswith("#"):
            inputs.append(line.split()[0].strip("`"))
    return inputs


def _enrich_metadata(meta: Dict[str, Any], fm: Dict[str, str]) -> Dict[str, Any]:
    name = str(meta.get("name") or "")
    kind = fm.get("kind") or classify_kind(name)
    runtime = fm.get("runtime") or "python"
    discoverable = _parse_bool(fm.get("discoverable"), True)
    weight = fm.get("weight") or classify_weight(name, kind=kind)  # type: ignore[arg-type]
    meta["kind"] = kind
    meta["runtime"] = runtime
    meta["discoverable"] = discoverable
    meta["weight"] = weight
    meta["tier"] = TIER_MAP.get(name, "Other")
    meta["inputs"] = _extract_inputs(meta.get("_raw_text", "")) if meta.get("_raw_text") else []
    return meta


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

    meta: Dict[str, Any] = {
        "name": fm.get("name") or skill_md.parent.name,
        "description": fm.get("description") or first_heading,
        "purpose": purpose,
        "when_to_use": when_to_use,
        "methodology_summary": methodology,
        "version": fm.get("version") or "0.1.0",
        "status": fm.get("status") or "active",
        "_raw_text": text,
    }
    enriched = _enrich_metadata(meta, fm)
    enriched.pop("_raw_text", None)
    return enriched


def parse_skill_description(skill_md: Path) -> str:
    meta = parse_skill_md(skill_md)
    return str(meta.get("description") or meta.get("name") or "")


def get_skill_meta(name: str) -> Optional[Dict[str, Any]]:
    path = SKILLS_DIR / name / "SKILL.md"
    if not path.exists():
        return None
    return parse_skill_md(path)


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
                kind=meta.get("kind") or "analysis",
                runtime=meta.get("runtime") or "python",
                discoverable=bool(meta.get("discoverable", True)),
                weight=meta.get("weight") or "light",
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
        if not meta.get("discoverable", True):
            continue
        rows.append(meta)
    return rows
