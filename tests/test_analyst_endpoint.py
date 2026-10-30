"""Tests for the Analyst workbench mode (agent tool loop + HTTP surface)."""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.opar.agent_runtime import ScriptedTransport, make_tool_call
from app.opar.models import ObserveContext


@pytest.fixture
def client():
    return TestClient(app)


def _seed_session(sid: str, eid: str, skill_outputs: dict | None = None) -> None:
    from app.memory import MemoryStore
    from app.routers._shared import write_manifest

    # observe() resolves engagement_id via read_manifest (session registration),
    # not the "session"-scope analysis record — seed both like the real app does.
    write_manifest(sid, {"session_id": sid, "engagement_id": eid, "files": []})
    MemoryStore().put(
        "session",
        sid,
        {
            "session_id": sid,
            "engagement_id": eid,
            "manifest": {"engagement_id": eid},
            "skill_outputs": skill_outputs or {},
        },
    )


# --------------------------------------------------------------------------- #
# Controller-level: tool_audit_callback wiring + ScriptedTransport             #
# --------------------------------------------------------------------------- #

def test_run_agent_chat_controller_fires_tool_audit_callback() -> None:
    from app.opar.agent_controller import run_agent_chat_controller

    audited: list[str] = []
    transport = ScriptedTransport([
        (None, [make_tool_call("run_skill", {"name": "spend-profiler"})]),
        ("Facilities spend is concentrated in three vendors.", []),
    ])
    ctx = ObserveContext(user_message="summarize facilities spend", session_id="s-analyst")

    with patch("app.opar.agent_controller.agent_loop_available", return_value=True):
        result = run_agent_chat_controller(
            ctx,
            transport=transport,
            tool_audit_callback=lambda call: audited.append(call.name),
        )

    assert result.success
    assert audited == ["run_skill"]
    assert result.agent_summary == "Facilities spend is concentrated in three vendors."


# --------------------------------------------------------------------------- #
# Router: available=false deterministic-fallback path (no LLM key in tests)    #
# --------------------------------------------------------------------------- #

def test_analyst_run_falls_back_when_no_llm_transport(client) -> None:
    sid = str(uuid.uuid4())
    eid = str(uuid.uuid4())
    _seed_session(sid, eid)

    resp = client.post(
        f"/api/v1/analyst/{sid}/run",
        json={"run_id": str(uuid.uuid4()), "question": "what drove the Q3 overrun?"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is False
    assert body["fallback"]["reason"] in ("agent_loop_unavailable", "no_llm_transport")


def test_analyst_run_before_any_analysis_run(client) -> None:
    """No 'session'-scope analysis record yet (fresh session, only /api/v1/sessions
    registration) — engagement_id must resolve via _session_engagement_id, not crash
    ObserveContext with None."""
    sid = str(uuid.uuid4())
    eid = str(uuid.uuid4())
    from app.routers._shared import write_manifest

    write_manifest(sid, {"session_id": sid, "engagement_id": eid})

    resp = client.post(
        f"/api/v1/analyst/{sid}/run",
        json={"run_id": str(uuid.uuid4()), "question": "what are the top suppliers?"},
    )
    assert resp.status_code == 200
    assert resp.json()["available"] is False


def test_analyst_run_rejects_empty_question(client) -> None:
    sid = str(uuid.uuid4())
    eid = str(uuid.uuid4())
    _seed_session(sid, eid)

    resp = client.post(
        f"/api/v1/analyst/{sid}/run",
        json={"run_id": str(uuid.uuid4()), "question": "   "},
    )
    assert resp.status_code == 422


# --------------------------------------------------------------------------- #
# Router: available=true path, audit events, provenance, persisted history    #
# --------------------------------------------------------------------------- #

def test_analyst_run_success_path_records_provenance_and_history(client, tmp_path, monkeypatch) -> None:
    from app.opar import provenance as prov

    monkeypatch.setattr(prov, "_PROVENANCE_DIR", tmp_path / "provenance")

    sid = str(uuid.uuid4())
    eid = str(uuid.uuid4())
    _seed_session(sid, eid)

    from app.opar.agent_controller import AgentRunResult
    from app.opar.models import ActResult

    fake_result = AgentRunResult(
        success=True,
        act_result=ActResult(skill_outputs={"spend-profiler": {"top_categories": []}}),
        agent_summary="Facilities spend is concentrated in three vendors.",
        thinking_text="considering categories",
        agent_trace=[
            {"tool": "query_spend", "arguments": {"sql": "SELECT 1"}, "ok": True},
            {"tool": "run_skill", "arguments": {"name": "spend-profiler"}, "ok": True},
        ],
    )

    with patch(
        "app.opar.agent_controller.run_agent_chat_controller", return_value=fake_result
    ), patch("app.routers.analyst.append_audit_event") as audit:
        run_id = str(uuid.uuid4())
        resp = client.post(
            f"/api/v1/analyst/{sid}/run",
            json={"run_id": run_id, "question": "why did facilities overrun?"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is True
    assert body["answer"] == "Facilities spend is concentrated in three vendors."
    assert body["skills_run"] == ["spend-profiler"]
    assert body["queries_run"] == [{"sql": "SELECT 1"}]
    assert body["provenance"]["prompt_hash"]

    audit_msgs = [str(c.args[0]) for c in audit.call_args_list]
    assert any("analyst_run" in m and "available=true" in m for m in audit_msgs)

    snapshot = prov.load_snapshot(eid, run_id)
    assert snapshot, "provenance snapshot should be persisted for the turn"

    history = client.get(f"/api/v1/analyst/{sid}/history")
    assert history.status_code == 200
    turns = history.json()["turns"]
    assert len(turns) == 1
    assert turns[0]["question"] == "why did facilities overrun?"
    assert turns[0]["available"] is True
