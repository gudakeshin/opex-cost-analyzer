from __future__ import annotations

import os
import shutil
import sys
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

from app.main import app  # noqa: E402
from app.models import NormalizedSpendLine, SessionAnalysisState
from app.storage import ensure_dirs


@pytest.fixture
def seed_session_upload():
    from tests.session_test_utils import seed_session_upload as _seed

@pytest.fixture(autouse=True)
def clean_data_dirs() -> None:
    root = Path(__file__).resolve().parents[1]
    data_dir = root / "data"
    for name in ("uploads", "outputs", "memory", "pipeline", "benchmarks"):
        target = data_dir / name
        if target.exists():
            shutil.rmtree(target)
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

