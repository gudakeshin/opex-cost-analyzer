"""Bearer-token auth + ownership scoping (app/security/auth.py).

AUTH_ENABLED is read per-request, so monkeypatching env vars is enough to
exercise the enabled paths; the rest of the suite runs with auth disabled.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def auth_env(monkeypatch) -> None:
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("API_AUTH_TOKENS", "alice:token-a,bob:token-b,bare-token")


def _client() -> TestClient:
    return TestClient(app)


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_auth_disabled_by_default_allows_requests() -> None:
    resp = _client().post("/api/v1/sessions", json={})
    assert resp.status_code == 200
    assert resp.json().get("owner") is None


def test_missing_token_rejected_when_enabled(auth_env) -> None:
    resp = _client().post("/api/v1/sessions", json={})
    assert resp.status_code == 401
    assert resp.headers.get("WWW-Authenticate") == "Bearer"


def test_wrong_token_rejected(auth_env) -> None:
    resp = _client().post("/api/v1/sessions", json={}, headers=_headers("nope"))
    assert resp.status_code == 401


def test_health_and_metrics_stay_open(auth_env) -> None:
    client = _client()
    assert client.get("/health").status_code == 200
    assert client.get("/metrics").status_code == 200


def test_enabled_without_tokens_fails_closed(auth_env, monkeypatch) -> None:
    monkeypatch.setenv("API_AUTH_TOKENS", "")
    resp = _client().post("/api/v1/sessions", json={}, headers=_headers("anything"))
    assert resp.status_code == 401


def test_valid_token_stamps_owner(auth_env) -> None:
    resp = _client().post("/api/v1/sessions", json={}, headers=_headers("token-a"))
    assert resp.status_code == 200
    assert resp.json()["owner"] == "alice"

    resp = _client().post("/api/v1/engagements", json={}, headers=_headers("bare-token"))
    assert resp.status_code == 200
    assert resp.json()["owner"] == "default"


def test_cross_principal_access_forbidden(auth_env) -> None:
    client = _client()
    eng = client.post(
        "/api/v1/engagements", json={"company_name": "Acme"}, headers=_headers("token-a")
    ).json()
    eid = eng["engagement_id"]

    # Owner can read it; the other principal gets 403; lists are filtered.
    assert client.get(f"/api/v1/engagements/{eid}", headers=_headers("token-a")).status_code == 200
    assert client.get(f"/api/v1/engagements/{eid}", headers=_headers("token-b")).status_code == 403
    ids_b = {e["engagement_id"] for e in client.get("/api/v1/engagements", headers=_headers("token-b")).json()}
    assert eid not in ids_b
    ids_a = {e["engagement_id"] for e in client.get("/api/v1/engagements", headers=_headers("token-a")).json()}
    assert eid in ids_a


def test_cross_principal_session_forbidden(auth_env) -> None:
    client = _client()
    session = client.post("/api/v1/sessions", json={}, headers=_headers("token-a")).json()
    sid = session["session_id"]

    assert client.get(f"/api/v1/sessions/{sid}/status", headers=_headers("token-a")).status_code == 200
    assert client.get(f"/api/v1/sessions/{sid}/status", headers=_headers("token-b")).status_code == 403
    # Body-based chat endpoint enforces ownership too.
    resp = client.post(
        "/api/v1/chat/plan",
        json={"message": "hi", "session_id": sid},
        headers=_headers("token-b"),
    )
    assert resp.status_code == 403


def test_legacy_unowned_resources_accessible(auth_env) -> None:
    client = _client()
    # Created while auth was off → no owner → any authenticated principal may access.
    import os

    os.environ["AUTH_ENABLED"] = "false"
    sid = client.post("/api/v1/sessions", json={}).json()["session_id"]
    os.environ["AUTH_ENABLED"] = "true"

    assert client.get(f"/api/v1/sessions/{sid}/status", headers=_headers("token-b")).status_code == 200
