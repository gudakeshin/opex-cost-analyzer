"""Skill-catalog integrity + real skill-test endpoint.

Guards against the catalog drifting from the dispatch registry (every executable
skill must ship a SKILL.md so it appears in GET /api/skills) and verifies that
POST /api/skills/{name}/test actually smoke-runs the handler rather than
returning a hard-coded "pass".
"""
from __future__ import annotations

import os

from app.config import ROOT_DIR
from app.skills.dispatch import registered_skills
from app.skills.registry import discover_skills


def _skill_md_names() -> set[str]:
    skills_dir = ROOT_DIR / "skills"
    return {
        d
        for d in os.listdir(skills_dir)
        if (skills_dir / d / "SKILL.md").exists()
    }


def test_every_registered_skill_has_a_skill_md() -> None:
    """Catalog-drift guard: each dispatchable skill must have a SKILL.md so it is
    discoverable via the skills catalog / API."""
    missing = sorted(set(registered_skills()) - _skill_md_names())
    assert not missing, f"Registered skills missing a SKILL.md (invisible to /api/skills): {missing}"


def test_catalog_lists_all_executable_skills() -> None:
    discovered = {s.name for s in discover_skills()}
    assert set(registered_skills()).issubset(discovered)


def test_test_skill_endpoint_smoke_runs_every_skill(client) -> None:
    """The real test endpoint must execute each skill on synthetic data and never
    report a 'fail' (a fail means a broken handler, as it caught export-formatter)."""
    failures = []
    for meta in client.get("/api/v1/skills").json():
        name = meta["name"]
        resp = client.post(f"/api/v1/skills/{name}/test")
        assert resp.status_code == 200, name
        body = resp.json()
        assert body["status"] in {"pass", "skipped"}, (name, body)
        if body["status"] == "fail":
            failures.append((name, body.get("error")))
    assert not failures, f"Skills failing smoke-test: {failures}"


def test_test_skill_unknown_returns_404(client) -> None:
    resp = client.post("/api/v1/skills/does-not-exist/test")
    assert resp.status_code == 404
