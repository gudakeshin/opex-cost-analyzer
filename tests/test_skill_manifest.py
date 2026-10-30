from __future__ import annotations

from app.skills.manifest import validate_manifest_drift


def test_manifest_has_no_drift():
    errors = validate_manifest_drift()
    assert errors == [], f"manifest drift: {errors}"
