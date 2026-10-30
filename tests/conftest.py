from __future__ import annotations

import atexit
import os
import shutil
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any, Callable

# Ensure project root is on sys.path so that `eval.*` and `app.*` are both importable
# regardless of which directory pytest was invoked from.
_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import pytest
from fastapi.testclient import TestClient

# TestClient sends every request from one IP, so per-IP limits would trip
# across the suite. Must be set before app.main (→ app.ratelimit) is imported.
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
# Keep tests hermetic: never import the developer's real data/engagements
# JSON into the per-test SQLite database at app startup.
os.environ.setdefault("SQLITE_BOOTSTRAP_ENABLED", "false")

# Hermetic data directory. Tests create and delete engagements, sessions and the
# sqlite DB freely, so they must NEVER touch the developer's real ./data. Everything
# is redirected to a throwaway directory seeded only with the committed fixtures.
_REAL_DATA_DIR = (_PROJECT_ROOT / "data").resolve()
_TEST_DATA_DIR = Path(tempfile.mkdtemp(prefix="opex-test-data-")).resolve()
os.environ["OPEX_DATA_DIR"] = str(_TEST_DATA_DIR)
os.environ.pop("SQLITE_DB_PATH", None)  # the DB lives under the test data dir
for _fixture in ("risk_register.md", "sector_pack_overrides.json"):
    if (_REAL_DATA_DIR / _fixture).is_file():
        shutil.copy2(_REAL_DATA_DIR / _fixture, _TEST_DATA_DIR / _fixture)
atexit.register(shutil.rmtree, _TEST_DATA_DIR, ignore_errors=True)

from app.main import app  # noqa: E402
from app.models import NormalizedSpendLine, SessionAnalysisState
from app.storage import ensure_dirs


@pytest.fixture
def seed_session_upload():
    from tests.session_test_utils import seed_session_upload as _seed

@pytest.fixture(autouse=True)
def clean_data_dirs() -> None:
    from app.config import DATA_DIR

    data_dir = Path(DATA_DIR).resolve()
    if data_dir == _REAL_DATA_DIR or _REAL_DATA_DIR in data_dir.parents:
        # Last line of defence: refuse to delete the developer's real data.
        pytest.exit(f"Refusing to run: tests resolved DATA_DIR to the real data dir ({data_dir}).", returncode=2)
    from app.config import SQLITE_DB_PATH

    db_path = Path(SQLITE_DB_PATH).resolve()
    if _REAL_DATA_DIR in db_path.parents:
        pytest.exit(f"Refusing to run: SQLITE_DB_PATH points into the real data dir ({db_path}).", returncode=2)
    for name in ("uploads", "outputs", "memory", "pipeline", "benchmarks"):
        target = data_dir / name
        if target.exists():
            shutil.rmtree(target)
    # Same reset for the sqlite backend: session/engagement rows live in the
    # DB file, not under data/uploads.
    from app.db.connection import reset_schema_cache

    for suffix in ("", "-wal", "-shm"):
        db_file = Path(f"{SQLITE_DB_PATH}{suffix}")
        if db_file.exists():
            db_file.unlink()
    reset_schema_cache()
    ensure_dirs()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def spend_line_factory() -> Callable[..., NormalizedSpendLine]:
    def _make(**kwargs: Any) -> NormalizedSpendLine:
        defaults: dict[str, Any] = {
            "row_id": 1,
            "supplier": "Test Supplier Ltd",
            "description": "Test spend line",
            "amount": 100_000.0,
            "category_id": "IT_SOFTWARE",
            "category_name": "IT Software & Licenses",
        }
        defaults.update(kwargs)
        return NormalizedSpendLine(**defaults)
    return _make


@pytest.fixture
def session_factory() -> Callable[..., SessionAnalysisState]:
    def _make(**kwargs: Any) -> SessionAnalysisState:
        defaults: dict[str, Any] = {
            "session_id": str(uuid.uuid4()),
            "industry": "tech",
            "annual_revenue": 50_000_000.0,
            "reporting_currency": "INR",
        }
        defaults.update(kwargs)
        return SessionAnalysisState(**defaults)
    return _make

