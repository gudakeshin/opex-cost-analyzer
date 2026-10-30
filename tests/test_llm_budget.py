"""Per-engagement LLM spend tracking and the optional hard cap."""
from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app
from app.metrics import record_llm_usage
from app.opar import claude_client
from app.opar.llm_errors import LLMBudgetExceeded, ProviderPermanentError
from app.services import llm_budget
from app.services.llm_selection import submit_with_context


def _scope() -> str:
    return f"eng-{uuid.uuid4()}"


def test_spend_is_attributed_to_the_scope_and_persisted():
    scope = _scope()
    with llm_budget.budget_scope(scope):
        record_llm_usage("anthropic", "claude-sonnet-4-6", 1_000_000, 0)  # $3.00 at list price
    s = llm_budget.status(scope)
    assert s["spent_usd"] == pytest.approx(3.0) and s["calls"] == 1 and s["cap_usd"] is None
    # no scope in context: nothing is attributed
    record_llm_usage("anthropic", "claude-sonnet-4-6", 1_000_000, 0)
    assert llm_budget.status(scope)["spent_usd"] == pytest.approx(3.0)


def test_cap_blocks_further_calls_and_looks_like_a_skip(monkeypatch):
    scope = _scope()
    monkeypatch.setattr(config, "LLM_MAX_COST_USD_PER_ENGAGEMENT", 5.0)
    with llm_budget.budget_scope(scope):
        llm_budget.check_budget()  # under the cap
        llm_budget.add_spend(5.5)
        with pytest.raises(LLMBudgetExceeded) as exc:
            llm_budget.check_budget()
        assert isinstance(exc.value, ProviderPermanentError)  # existing callers treat this as "skip synthesis"
        assert exc.value.skip_reason == "llm_budget_exceeded"
        # the real call path refuses before any network call
        with pytest.raises(LLMBudgetExceeded):
            claude_client._call_anthropic_native("sys", "user", model="m")
    assert llm_budget.status(scope)["exceeded"] is True
    # other engagements are unaffected, and no cap means no blocking
    with llm_budget.budget_scope(_scope()):
        llm_budget.check_budget()
    monkeypatch.setattr(config, "LLM_MAX_COST_USD_PER_ENGAGEMENT", None)
    with llm_budget.budget_scope(scope):
        llm_budget.check_budget()


def test_scope_follows_work_handed_to_a_worker_thread():
    scope = _scope()
    with llm_budget.budget_scope(scope), ThreadPoolExecutor(max_workers=1) as pool:
        submit_with_context(pool, record_llm_usage, "anthropic", "claude-sonnet-4-6", 1_000_000, 0).result()
    assert llm_budget.status(scope)["spent_usd"] == pytest.approx(3.0)


def test_usage_endpoint():
    with TestClient(app) as client:
        eid = client.post("/api/v1/engagements", json={"company_name": "Cost Co", "currency": "INR"}).json()[
            "engagement_id"
        ]
        llm_budget.add_spend(1.25, scope=eid)
        body = client.get(f"/api/v1/engagements/{eid}/llm-usage").json()
        assert body["spent_usd"] == pytest.approx(1.25) and body["calls"] == 1
