"""Tests for Phase 3 — agent chat routing, agentic SQL, LLM-primary scenario parsing."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.opar.chat_routing import (
    is_simple_contextual_qa,
    needs_agent_investigation,
    should_use_agent_chat_path,
    should_use_cached_qa_fastpath,
)
from app.opar.models import ObserveContext
from app.opar.tools.scenario_parser import parse_what_if_request, validate_custom_scenarios
from app.opar.tools.context import ToolSessionContext


def test_needs_agent_investigation_for_sql_questions() -> None:
    assert needs_agent_investigation("Vendors where spend grew > 20% QoQ")
    assert needs_agent_investigation("What if execution drops to 50%?")


def test_simple_contextual_qa_allows_fastpath() -> None:
    ctx = ObserveContext(
        user_message="What is total spend by category?",
        intent_class="general_qa",
        has_tabular_spend=True,
    )
    assert is_simple_contextual_qa(ctx, ctx.user_message)
    assert should_use_cached_qa_fastpath(ctx, ctx.user_message)


def test_agent_chat_path_for_analytical_followups() -> None:
    ctx = ObserveContext(
        user_message="What if supplier prices rise 5%?",
        intent_class="general_qa",
        has_tabular_spend=True,
        spend_profile_ready=True,
    )
    with patch("app.opar.agent_runtime.agent_loop_available", return_value=True):
        assert should_use_agent_chat_path(ctx, ctx.user_message)


def test_sql_repair_loop_retries_until_success(tmp_path, monkeypatch) -> None:
    pytest.importorskip("duckdb")
    pytest.importorskip("pyarrow")

    from app.models import NormalizedSpendLine
    from app.services import spend_store as ss
    from app.services.spend_store import SpendStore, write_document_spend_lines
    from app.opar.tools import nl_query

    monkeypatch.setattr(ss, "ENGAGEMENTS_DIR", tmp_path)
    eid = "eng-sql-repair"
    sid = "sess-sql-repair"
    lines = [
        NormalizedSpendLine(
            row_id=1,
            supplier="A",
            description="svc",
            amount=100.0,
            category_id="CAT1",
            category_name="Facilities",
            source_record_id="r1",
            source_file_hash="h",
        )
    ]
    write_document_spend_lines(eid, "doc1", lines)
    store = SpendStore(eid)
    schema = {"columns": [{"name": "supplier"}, {"name": "amount"}], "sample_values": {}}

    calls = {"n": 0}

    def fake_llm(question, schema, *, tier, max_tokens=None, model=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return "SELECT bad_col FROM spend"
        return "SELECT supplier, SUM(amount) AS spend FROM spend GROUP BY supplier"

    with patch.object(nl_query, "_llm_aggregate_or_sql", side_effect=fake_llm):
        out = nl_query._execute_sql_with_repair_loop(
            store,
            "top suppliers",
            schema,
        )

    assert out.get("result") is not None
    assert out.get("sql_attempts", 0) >= 2
    assert len(out.get("repair_trace") or []) >= 1


def test_parse_what_if_llm_primary_with_regex_fallback() -> None:
    ctx = ObserveContext(user_message="delay timeline", session_id="s-wi")
    session = ToolSessionContext(ctx=ctx)
    session.skill_outputs["spend-profiler"] = {
        "category_profile": [{"category_id": "FAC", "category_name": "Facilities"}],
    }

    llm_payload = {
        "scenarios": [{
            "name": "supplier_shock",
            "target": "portfolio",
            "savings_pct_delta": 0.0,
            "spend_pool_delta_pct": 0.05,
            "timeline_factor": 1.0,
        }],
        "drivers": {"execution_rate_pct": 0.5},
    }
    with patch("app.opar.tools.scenario_parser._llm_parse_what_if", return_value=llm_payload):
        out = parse_what_if_request(session, "What if supplier prices rise 5% and execution is 50%?")

    assert out["parse_source"] == "llm"
    assert out["drivers"]["execution_rate_pct"] == 0.5
    assert out["scenarios"][0]["spend_pool_delta_pct"] == 0.05


def test_validate_custom_scenario_extended_fields() -> None:
    specs = [{
        "name": "shock",
        "target": "portfolio",
        "savings_pct_delta": -0.1,
        "timeline_factor": 1.2,
        "spend_pool_delta_pct": 0.05,
        "bounce_back_override": "high",
        "cost_driver_deltas": {"supplier_price_inflation_pct": 0.05},
    }]
    validated, errors = validate_custom_scenarios(specs, [])
    assert not errors
    assert validated[0].spend_pool_delta_pct == 0.05
    assert validated[0].bounce_back_override == "high"


def test_compute_sensitivity_custom_spend_pool_delta() -> None:
    from app.services.sensitivity import compute_sensitivity

    bridge = {"confidence_bands": {"low": 80, "mid": 100, "high": 120}}
    out = compute_sensitivity(
        bridge,
        custom_scenarios=[{
            "name": "supplier_shock",
            "target": "portfolio",
            "savings_pct_delta": 0.0,
            "spend_pool_delta_pct": 0.10,
            "timeline_factor": 1.0,
            "execution_rate": 0.8,
        }],
    )
    custom = [s for s in out["scenarios"] if s.get("custom")]
    assert custom
    assert custom[0]["spend_pool_delta_pct"] == 0.10
    assert custom[0]["savings_3yr"] > 100 * 0.8 * 0.9
