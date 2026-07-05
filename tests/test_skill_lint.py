"""Skill catalog lint checks."""
from __future__ import annotations

from scripts.lint_skills import lint_skills


def test_skill_lint_passes() -> None:
    errors = lint_skills()
    assert errors == [], f"skill-lint failures: {errors}"
