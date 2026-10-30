#!/usr/bin/env python3
"""Lint skill catalog: frontmatter, references, manifest alignment."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import SKILLS_DIR
from app.skills.manifest import manifest_skill_names, validate_manifest_drift
from app.skills.registry import _parse_frontmatter, parse_skill_md

HUB_STUBS = {"savings-modeler", "root-cause-analyzer"}
MIN_DESC_LEN = 30
MIN_STUB_LINES = 10


def _cited_references(text: str) -> list[str]:
    refs: set[str] = set()
    for m in re.finditer(r"`(references/[^`]+)`", text):
        refs.add(m.group(1))
    for m in re.finditer(r"references/([\w\-./]+\.(?:json|yaml|csv|md))", text):
        refs.add(f"references/{m.group(1)}")
    return sorted(refs)


def lint_skills() -> list[str]:
    errors: list[str] = []
    manifest_names = set(manifest_skill_names(active_only=False))

    for path in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        name = path.parent.name
        text = path.read_text(encoding="utf-8")
        lines = len(text.splitlines())
        fm = _parse_frontmatter(text)
        if not fm:
            errors.append(f"{name}: missing or invalid YAML frontmatter")
            continue
        desc = str(fm.get("description") or "").strip()
        if len(desc) < MIN_DESC_LEN:
            errors.append(f"{name}: description shorter than {MIN_DESC_LEN} chars")
        for ref in _cited_references(text):
            if not (path.parent / ref).exists():
                errors.append(f"{name}: missing reference file {ref}")
        if name in HUB_STUBS and lines <= MIN_STUB_LINES:
            errors.append(f"{name}: DAG hub still a stub ({lines} lines)")
        meta = parse_skill_md(path)
        if meta.get("discoverable", True) and name not in manifest_names:
            errors.append(f"{name}: discoverable but not in manifest")

    for row in manifest_skills_yaml_deps(manifest_names):
        errors.extend(row)

    errors.extend(validate_manifest_drift())
    return errors


def manifest_skills_yaml_deps(manifest_names: set[str]) -> list[str]:
    from app.skills.manifest import manifest_skills

    known = manifest_names
    out: list[str] = []
    for row in manifest_skills():
        name = str(row.get("name") or "")
        for dep in row.get("depends_on") or []:
            if str(dep) not in known:
                out.append(f"{name}: depends_on unknown skill '{dep}'")
    return out


def main() -> int:
    errors = lint_skills()
    if errors:
        print(f"skill-lint: {len(errors)} issue(s)")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("skill-lint: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
