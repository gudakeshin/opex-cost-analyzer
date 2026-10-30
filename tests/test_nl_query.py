"""Tests for NL query routing and scenario parsing."""
from __future__ import annotations

from unittest.mock import patch

import pytest

pytest.importorskip("duckdb")
pytest.importorskip("pyarrow")

from app.models import NormalizedSpendLine
from app.opar.agent_runtime import ToolCall
from app.opar.models import ObserveContext
from app.opar.tools.catalog import dispatch_tool_call, get_tool_catalog
from app.opar.tools.context import ToolSessionContext
from app.opar.tools.nl_query import classify_nl_query_tier, run_natural_language_query
from app.opar.tools.scenario_parser import (
    parse_drivers_from_nl,
    parse_what_if_request,
    validate_custom_scenarios,
)
from app.services.spend_store import SpendStore, write_document_spend_lines


def test_query_spend_tool_mentions_fiscal_period() -> None:
    names = {t.name for t in get_tool_catalog()}
    assert "natural_language_query" in names
    assert "run_sensitivity" in names
    query_tool = next(t for t in get_tool_catalog() if t.name == "query_spend")
    assert "fiscal_period" in query_tool.description
    assert " period," not in query_tool.description


def test_classify_nl_query_tier() -> None:
    assert classify_nl_query_tier("How do we compare to peer benchmarks?") == "skill"
    assert classify_nl_query_tier("Top 10 suppliers by spend") == "aggregate"
    assert classify_nl_query_tier(
        "Vendors where spend grew > 20% QoQ", prefer="sql"
    ) == "sql"


def test_parse_drivers_from_nl() -> None:
    drivers = parse_drivers_from_nl("What if execution drops to 50%?")
    assert drivers["execution_rate_pct"] == 0.5


def test_validate_custom_scenarios_rejects_unknown_category() -> None:
    specs = [{"name": "x", "target": "category", "id": "UNKNOWN_CAT"}]
    cats = [{"category_id": "IT", "category_name": "IT & Technology"}]
    validated, errors = validate_custom_scenarios(specs, cats)
    assert not validated
    assert errors


def test_natural_language_query_aggregate_tier(tmp_path, monkeypatch) -> None:
    from app.services import spend_store as ss

    monkeypatch.setattr(ss, "ENGAGEMENTS_DIR", tmp_path)
    eid = "eng-nl"
    sid = "sess-nl"
    lines = [
        NormalizedSpendLine(
            row_id=i,
            supplier=f"V{i % 3}",
            description="svc",
            amount=100.0 * i,
            category_id="CAT1",
            category_name="Facilities",
            business_unit="BU1",
            source_record_id=f"r{i}",
            source_file_hash="h",
        )
        for i in range(1, 11)
    ]
    write_document_spend_lines(eid, "doc1", lines)

    ctx = ObserveContext(user_message="top 5 suppliers", session_id=sid, engagement_id=eid)
    session = ToolSessionContext(ctx=ctx)

    with patch("app.opar.tools.nl_query._open_agent_store") as open_store:
        store = SpendStore(eid)
        open_store.return_value = store
        out = run_natural_language_query(session, question="top 5 suppliers by spend")

    assert out["tier"] in ("aggregate", "sql")
    if out["tier"] == "aggregate":
        assert out["result"]["row_count"] >= 1


def test_run_sensitivity_tool_with_mock_bridge() -> None:
    ctx = ObserveContext(user_message="what if conservative", session_id="s-sens")
    session = ToolSessionContext(ctx=ctx)
    session.lines = [
        NormalizedSpendLine(
            row_id=1,
            supplier="A",
            description="x",
            amount=100.0,
            category_id="IT",
            category_name="IT",
        ),
    ]
    session.skill_outputs["value-bridge-calculator"] = {
        "confidence_bands": {"low": 80, "mid": 100, "high": 120},
    }
    session.skill_outputs["savings-modeler"] = {"initiatives": []}
    session.manifest = {"wacc": 0.1, "effective_tax_rate": 0.25}

    with patch.object(session, "invoke_skill") as inv:
        inv.side_effect = lambda name: session.skill_outputs.get(name, {})
        out = dispatch_tool_call(
            session,
            ToolCall(
                id="1",
                name="run_sensitivity",
                arguments={"preset": "conservative"},
            ),
        )
    assert out.get("engine") == "compute_sensitivity"
    assert "scenarios" in out
    assert "sensitivity-analyzer" in session.skill_outputs


def test_parse_what_if_request_with_profiler_categories() -> None:
    ctx = ObserveContext(user_message="delay timeline", session_id="s-wi")
    session = ToolSessionContext(ctx=ctx)
    session.skill_outputs["spend-profiler"] = {
        "category_profile": [
            {"category_id": "FAC", "category_name": "Facilities"},
        ],
    }
    out = parse_what_if_request(session, "What if Facilities is delayed?")
    assert out["scenarios"] or out["drivers"]


def test_sensitivity_analyzer_in_dep_map() -> None:
    from app.opar.plan import get_skill_dep_map

    assert "sensitivity-analyzer" in get_skill_dep_map()
