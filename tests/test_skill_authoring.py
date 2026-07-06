"""Tests for skill authoring path (P0 improvements)."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.config import ROOT_DIR
from app.schemas import SkillCreateRequest, SkillStructuredCreateRequest
from app.skills.registry import _parse_frontmatter, compose_frontmatter, validate_declarative_output
from app.skills.validation import validate_skill_slug
from app.routers.skills import _compose_skill_md, _evaluate_smoke_result


def test_skill_slug_rejects_traversal() -> None:
    with pytest.raises(ValueError):
        validate_skill_slug("../escape")


def test_skill_slug_rejects_invalid_chars() -> None:
    with pytest.raises(ValueError):
        validate_skill_slug("My Skill!")


def test_skill_slug_accepts_valid() -> None:
    assert validate_skill_slug("my-custom-analyzer") == "my-custom-analyzer"


def test_create_skill_rejects_invalid_slug(client) -> None:
    resp = client.post(
        "/api/v1/skills",
        json={"name": "../x", "content": "---\nname: x\n---\n# X\n"},
    )
    assert resp.status_code == 422 or resp.status_code == 400


def test_structured_skill_starts_as_draft(client) -> None:
    name = "test-draft-skill-z9"
    skill_path = ROOT_DIR / "skills" / name / "SKILL.md"
    if skill_path.exists():
        skill_path.unlink()
        skill_path.parent.rmdir()
    payload = {
        "name": name,
        "description": "Draft skill for unit test — validates draft lifecycle on structured create path.",
        "instruction_prompt": "Return a summary.",
        "output_fields": ["summary"],
        "runtime": "declarative",
        "depends_on": [],
    }
    resp = client.post("/api/v1/skills/structured", json=payload)
    assert resp.status_code == 200, resp.text
    from app.skills.registry import parse_skill_md

    meta = parse_skill_md(skill_path)
    assert meta["status"] == "draft"
    # cleanup
    skill_path.unlink()
    skill_path.parent.rmdir()
    from app.skills.manifest import load_manifest

    data = load_manifest()
    data["skills"] = [s for s in data.get("skills", []) if s.get("name") != name]
    (ROOT_DIR / "skills" / "manifest.yaml").write_text(
        __import__("yaml").dump(data, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )


def test_evaluate_smoke_result_fails_empty_dict() -> None:
    status, _ = _evaluate_smoke_result({}, None, is_declarative=False)
    assert status == "fail"


def test_evaluate_smoke_result_fails_provider_unavailable() -> None:
    status, _ = _evaluate_smoke_result({}, "provider_unavailable", is_declarative=True)
    assert status == "fail"


def test_evaluate_smoke_result_skips_provider_disabled() -> None:
    status, _ = _evaluate_smoke_result({}, "provider_disabled", is_declarative=True)
    assert status == "skipped"


def test_yaml_frontmatter_multiline_description() -> None:
    desc = (
        "Synthesizes outputs from upstream OpEx Intelligence skills into a CFO-grade narrative. "
        "Trigger when consolidating multi-skill outputs."
    )
    md = compose_frontmatter({"name": "t", "description": desc, "status": "active"}) + "\n# T\n"
    fm = _parse_frontmatter(md)
    assert fm.get("description") == desc


def test_compose_skill_md_roundtrip_quotes() -> None:
    payload = SkillStructuredCreateRequest(
        name="quote-test-skill",
        description='Analyze "high-value" vendors and say: "done"',
        instruction_prompt="Do the thing.",
        output_fields=["result"],
    )
    md = _compose_skill_md(payload)
    fm = _parse_frontmatter(md)
    assert fm.get("description") == payload.description


def test_declarative_output_schema_validation() -> None:
    assert validate_declarative_output({"a": 1}, ["a", "b"]) == "schema_parse_fail"
    assert validate_declarative_output({"a": 1, "b": 2}, ["a", "b"]) is None


def test_analysis_synthesizer_description_parses() -> None:
    from app.config import SKILLS_DIR

    fm = _parse_frontmatter((SKILLS_DIR / "analysis-synthesizer" / "SKILL.md").read_text(encoding="utf-8"))
    desc = str(fm.get("description") or "")
    assert len(desc) > 80
    assert desc != ">"


def test_list_skills_includes_status(client) -> None:
    resp = client.get("/api/v1/skills")
    assert resp.status_code == 200
    rows = resp.json()
    assert rows
    assert "status" in rows[0]


def test_archive_skill_blocked_when_depended_on(client) -> None:
    from app.skills.manifest import append_manifest_entry, load_manifest

    blocker = "test-archive-blocker"
    dependent = "test-archive-dependent"
    append_manifest_entry({
        "name": dependent,
        "tier": "Other",
        "parallel_group": 9,
        "depends_on": [blocker],
        "estimated_tokens": 100,
        "kind": "analysis",
        "weight": "light",
        "runtime": "declarative",
        "status": "active",
    })
    skill_dir = ROOT_DIR / "skills" / blocker
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: test-archive-blocker\nstatus: active\nruntime: declarative\n---\n# Blocker\n",
        encoding="utf-8",
    )
    resp = client.post(f"/api/v1/skills/{blocker}/archive")
    assert resp.status_code == 409
    data = load_manifest()
    data["skills"] = [s for s in data.get("skills", []) if s.get("name") not in {blocker, dependent}]
    (ROOT_DIR / "skills" / "manifest.yaml").write_text(
        __import__("yaml").dump(data, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    if skill_dir.exists():
        (skill_dir / "SKILL.md").unlink(missing_ok=True)
        skill_dir.rmdir()


def test_archived_skill_excluded_from_active_manifest_names() -> None:
    from app.skills.manifest import manifest_skill_names

    names = manifest_skill_names(active_only=True)
    assert "test-archive-blocker" not in names
