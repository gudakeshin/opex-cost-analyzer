"""Background analysis runs: one per session, cooperative cancel, status and resume."""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import analysis_runs


@pytest.fixture(autouse=True)
def _clean_registry():
    analysis_runs._runs.clear()
    analysis_runs._active_by_session.clear()
    yield
    analysis_runs._runs.clear()
    analysis_runs._active_by_session.clear()


def test_registry_allows_one_active_run_per_session():
    analysis_runs.start("s1", "r1")
    with pytest.raises(analysis_runs.AnalysisAlreadyRunning) as exc:
        analysis_runs.start("s1", "r2")
    assert exc.value.run_id == "r1"
    analysis_runs.start("s2", "r3")  # other sessions are independent
    analysis_runs.finish("r1", "completed")
    analysis_runs.start("s1", "r4")  # free again once finished


def test_cancel_is_cooperative_and_only_trips_at_checkpoints():
    analysis_runs.start("s1", "r1")
    analysis_runs.check_cancel("r1")  # no-op before a cancel
    run = analysis_runs.request_cancel("r1")
    assert run.status == "cancelling"
    with pytest.raises(analysis_runs.AnalysisCancelled):
        analysis_runs.check_cancel("r1")
    analysis_runs.finish("r1", "cancelled")
    assert analysis_runs.active_for_session("s1") is None
    assert analysis_runs.request_cancel("missing") is None


def _make_session(client: TestClient) -> str:
    eid = client.post(
        "/api/v1/engagements",
        json={"company_name": "Run Co", "industry": "it_ites", "annual_revenue": 1e9, "currency": "INR"},
    ).json()["engagement_id"]
    csv = b"supplier,description,amount\nAcme Cloud,cloud hosting,100000\nBeta,freight charges,50000\n"
    assert client.post(
        f"/api/v1/engagements/{eid}/documents", files={"file": ("l.csv", csv, "text/csv")}
    ).status_code == 200
    return client.post(
        "/api/v1/sessions",
        json={"company_name": "Run Co", "industry": "it_ites", "currency": "INR", "engagement_id": eid},
    ).json()["session_id"]


def _wait_for(client: TestClient, run_id: str, wanted: set[str], timeout: float = 20.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        run = client.get(f"/api/v1/analyze/runs/{run_id}").json()
        if run["status"] in wanted:
            return run
        time.sleep(0.1)
    raise AssertionError(f"run {run_id} never reached {wanted}: {run}")


def test_background_run_can_be_cancelled_between_steps(monkeypatch):
    def slow_pipeline(*args, progress_cb=None, **kwargs):
        for i in range(200):  # each progress call is a cancel checkpoint
            progress_cb("act", f"step {i}")
            time.sleep(0.05)
        raise AssertionError("cancel never took effect")

    monkeypatch.setattr("app.routers.sessions.run_core_pipeline", slow_pipeline)
    with TestClient(app) as client:
        sid = _make_session(client)
        started = client.post(f"/api/v1/analyze/{sid}", json={"background": True, "run_id": "run-cancel"})
        assert started.status_code == 200 and started.json()["status"] == "running"

        # a second start for the same session joins the run in flight instead of starting another
        again = client.post(f"/api/v1/analyze/{sid}", json={"background": True}).json()
        assert again["already_running"] is True and again["run_id"] == "run-cancel"
        # ...and the foreground form is refused
        assert client.post(f"/api/v1/analyze/{sid}", json={}).status_code == 409

        assert client.get(f"/api/v1/sessions/{sid}/analysis-run").json()["run"]["run_id"] == "run-cancel"

        assert client.post("/api/v1/analyze/runs/run-cancel/cancel").json()["status"] in {"cancelling", "cancelled"}
        final = _wait_for(client, "run-cancel", {"cancelled"})
        assert final["finished_at"]
        assert client.get(f"/api/v1/sessions/{sid}/analysis-run").json()["run"] is None
        assert client.get(f"/api/v1/chat/progress/run-cancel").json()["status"] == "failed"


def test_background_run_completes_and_result_is_readable():
    with TestClient(app) as client:
        sid = _make_session(client)
        run_id = client.post(f"/api/v1/analyze/{sid}", json={"background": True}).json()["run_id"]
        assert _wait_for(client, run_id, {"completed", "failed"})["status"] == "completed"
        assert client.get(f"/api/v1/sessions/{sid}").json()["skill_outputs"]


def test_failed_background_run_reports_the_error():
    with TestClient(app) as client:
        eid = client.post("/api/v1/engagements", json={"company_name": "Empty Co", "currency": "INR"}).json()[
            "engagement_id"
        ]
        sid = client.post("/api/v1/sessions", json={"company_name": "Empty Co", "engagement_id": eid}).json()[
            "session_id"
        ]
        run_id = client.post(f"/api/v1/analyze/{sid}", json={"background": True}).json()["run_id"]
        run = _wait_for(client, run_id, {"failed"})
        assert "No spend data" in run["error"]


def test_unknown_run_is_404():
    with TestClient(app) as client:
        assert client.get("/api/v1/analyze/runs/nope").status_code == 404
        assert client.post("/api/v1/analyze/runs/nope/cancel").status_code == 404
