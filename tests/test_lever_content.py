"""Every sector and universal lever must include execution playbook fields."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.config import ROOT_DIR

SECTOR_DIR = ROOT_DIR / "skills" / "sector-packs"
MODEL_PARAMS = ROOT_DIR / "skills" / "savings-modeler" / "references" / "model_parameters.json"

REQUIRED_FIELDS = ("execution_playbook", "diagnostic_signals", "required_data_fields")


def _assert_lever_content(lever: dict, label: str) -> None:
    lid = lever.get("lever_id", label)
    for field in REQUIRED_FIELDS:
        assert field in lever, f"{lid} missing {field}"
        val = lever[field]
        assert isinstance(val, list) and len(val) > 0, f"{lid}.{field} must be non-empty list"
    for step in lever["execution_playbook"]:
        assert "step" in step and "owner_role" in step and "duration_weeks" in step
    for sig in lever["diagnostic_signals"]:
        assert "signal" in sig and "evidence_source" in sig and "confirms" in sig


@pytest.mark.parametrize("path", sorted(SECTOR_DIR.glob("*/sector_levers.json")))
def test_sector_lever_playbook_fields(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    for lever in data.get("sector_specific_levers", []):
        _assert_lever_content(lever, str(path))


def test_universal_lever_playbook_fields():
    params = json.loads(MODEL_PARAMS.read_text(encoding="utf-8"))
    for lid, lever in params.get("levers", {}).items():
        lever.setdefault("lever_id", lid)
        _assert_lever_content(lever, lid)
