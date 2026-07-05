"""Load and validate the canonical skills manifest (skills/manifest.yaml)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import yaml

from app.config import ROOT_DIR

MANIFEST_PATH = ROOT_DIR / "skills" / "manifest.yaml"


def load_manifest() -> Dict[str, Any]:
    if not MANIFEST_PATH.exists():
        return {"skills": []}
    data = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {"skills": []}


def manifest_skills() -> List[Dict[str, Any]]:
    return list(load_manifest().get("skills") or [])


def manifest_skill_names(*, active_only: bool = True) -> List[str]:
    names: List[str] = []
    for row in manifest_skills():
        if active_only and str(row.get("status") or "active") != "active":
            continue
        name = row.get("name")
        if name:
            names.append(str(name))
    return names


def append_manifest_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Upsert a skill row into manifest.yaml (used for declarative skill registration)."""
    data = load_manifest()
    skills: List[Dict[str, Any]] = list(data.get("skills") or [])
    name = str(entry.get("name") or "")
    skills = [s for s in skills if s.get("name") != name]
    skills.append(entry)
    skills.sort(key=lambda s: (s.get("parallel_group", 99), s.get("name", "")))
    data["skills"] = skills
    MANIFEST_PATH.write_text(
        yaml.dump(data, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    return entry


def update_manifest_skill(name: str, **fields: Any) -> Dict[str, Any] | None:
    """Patch fields on an existing manifest row."""
    data = load_manifest()
    skills: List[Dict[str, Any]] = list(data.get("skills") or [])
    updated: Dict[str, Any] | None = None
    for row in skills:
        if str(row.get("name") or "") == name:
            row.update(fields)
            updated = row
            break
    if updated is None:
        return None
    data["skills"] = skills
    MANIFEST_PATH.write_text(
        yaml.dump(data, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    return updated


def validate_manifest_drift() -> List[str]:
    """Return human-readable drift messages (empty list = OK)."""
    from app.opar.plan import get_skill_dep_map
    from app.skills.dispatch import registered_skills
    from app.skills.registry import discover_skills

    errors: List[str] = []
    dep_map = get_skill_dep_map()
    manifest_names = {str(s.get("name")) for s in manifest_skills() if s.get("name")}
    registered = set(registered_skills())

    for name in sorted(dep_map.keys()):
        if name not in manifest_names:
            errors.append(f"manifest missing _DEP_MAP skill: {name}")

    for name in sorted(registered):
        if name not in manifest_names and name in dep_map:
            errors.append(f"manifest missing registered handler: {name}")

    for name in sorted(manifest_names):
        path = ROOT_DIR / "skills" / name / "SKILL.md"
        if not path.exists():
            errors.append(f"manifest entry missing SKILL.md: {name}")

    doc_names = {m.name for m in discover_skills()}
    for name in sorted(manifest_names):
        if name not in doc_names and name in dep_map:
            errors.append(f"manifest skill not in discover_skills(): {name}")

    for row in manifest_skills():
        name = str(row.get("name") or "")
        if name in dep_map:
            pg, deps, tokens = dep_map[name]
            if row.get("parallel_group") != pg:
                errors.append(f"{name}: parallel_group drift (manifest {row.get('parallel_group')} vs _DEP_MAP {pg})")
            if list(row.get("depends_on") or []) != list(deps):
                errors.append(f"{name}: depends_on drift")

    from app.config import SKILLS_DIR
    from app.skills.registry import parse_skill_md

    for path in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        skill_name = path.parent.name
        meta = parse_skill_md(path)
        if meta.get("discoverable", True) and skill_name not in manifest_names:
            errors.append(f"discoverable skill not in manifest: {skill_name}")

    return errors
