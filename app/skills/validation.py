"""Skill name validation and SKILL.md path resolution."""
from __future__ import annotations

import re
from pathlib import Path

from fastapi import HTTPException

from app.config import ROOT_DIR

SKILL_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")
RESERVED_SKILL_NAMES = frozenset({
    "_capability_matrix",
    "manifest",
    "references",
    "sector-packs",
})

FAIL_DEGRADED_REASONS = frozenset({
    "provider_unavailable",
    "timeout",
    "schema_parse_fail",
})

SKILLS_ROOT = (ROOT_DIR / "skills").resolve()


def _slug_error(message: str) -> None:
    raise ValueError(message)


def validate_skill_slug(name: str) -> str:
    """Return normalized slug or raise ValueError (for Pydantic) / HTTPException (via wrapper)."""
    slug = (name or "").strip()
    if not slug or not SKILL_SLUG_RE.match(slug):
        _slug_error("Skill name must match ^[a-z0-9][a-z0-9-]{1,63}$")
    if slug in RESERVED_SKILL_NAMES:
        _slug_error(f"Reserved skill name: {slug}")
    return slug


def validate_skill_slug_http(name: str) -> str:
    """Route-layer slug validation — raises HTTPException 400."""
    try:
        return validate_skill_slug(name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def resolve_skill_dir(name: str) -> Path:
    """Resolve skill directory with path-containment check."""
    slug = validate_skill_slug_http(name)
    skill_dir = (SKILLS_ROOT / slug).resolve()
    if not str(skill_dir).startswith(str(SKILLS_ROOT)):
        raise HTTPException(status_code=400, detail="Invalid skill name")
    return skill_dir


def resolve_skill_md_path(name: str) -> Path:
    return resolve_skill_dir(name) / "SKILL.md"


def known_skill_names() -> set[str]:
    from app.skills.dispatch import registered_skills
    from app.skills.manifest import manifest_skill_names
    from app.skills.registry import discover_skills

    return set(manifest_skill_names(active_only=False)) | set(registered_skills()) | {
        s.name for s in discover_skills()
    }


def validate_depends_on(names: list[str]) -> list[str]:
    """Ensure dependency names reference known skills."""
    known = known_skill_names()
    deps = list(names or [])
    unknown = sorted({n for n in deps if n not in known})
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown skill dependencies: {', '.join(unknown)}",
        )
    return deps
