"""Tests for semantic skill discovery."""
from __future__ import annotations

from app.skills.discovery import discover_relevant_skills
from app.skills.registry import discover_skills_rich, parse_skill_md
from app.config import SKILLS_DIR


def test_discover_skills_rich_parses_frontmatter() -> None:
    rich = discover_skills_rich()
    assert rich
    spend = next(r for r in rich if r["name"] == "spend-profiler")
    assert spend["description"]
    assert spend.get("when_to_use") or spend.get("purpose")


def test_parse_skill_md_reads_full_file() -> None:
    md = SKILLS_DIR / "spend-profiler" / "SKILL.md"
    meta = parse_skill_md(md)
    assert meta["name"] == "spend-profiler"
    assert "categor" in (meta.get("description") or "").lower() or "spend" in (meta.get("description") or "").lower()


def test_discover_relevant_skills_ranks_benchmarking() -> None:
    hits = discover_relevant_skills("compare my spend to industry peers and benchmark gaps", k=5)
    names = [h["name"] for h in hits]
    assert any("benchmark" in n for n in names)
