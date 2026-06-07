from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Any, Callable

import pytest
from fastapi.testclient import TestClient

from app.main import app
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

