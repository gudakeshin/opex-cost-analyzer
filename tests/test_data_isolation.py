"""The suite must never touch the developer's real ./data."""
from __future__ import annotations

from pathlib import Path

from app import config

REAL_DATA = (Path(__file__).resolve().parents[1] / "data").resolve()


def test_data_paths_are_redirected_away_from_real_data():
    for path in (config.DATA_DIR, config.ENGAGEMENTS_DIR, config.UPLOAD_DIR, config.SQLITE_DB_PATH):
        resolved = Path(path).resolve()
        assert resolved != REAL_DATA and REAL_DATA not in resolved.parents, resolved


def test_runtime_stores_follow_data_dir():
    from app.opar import provenance
    from app.services import audit_log, calibration, pipeline

    for path in (provenance._PROVENANCE_DIR, audit_log._LOG_PATH, calibration._CALIBRATION_ROOT, pipeline.PIPELINE_PATH):
        assert REAL_DATA not in Path(path).resolve().parents, path
