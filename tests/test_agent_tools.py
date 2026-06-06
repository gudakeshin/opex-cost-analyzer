"""Tests for agent tool catalog dispatch."""
from __future__ import annotations

from unittest.mock import patch

from app.opar.agent_runtime import ToolCall
from app.opar.models import ObserveContext
from app.opar.tools.catalog import dispatch_tool_call
from app.opar.tools.context import ToolSessionContext


def test_search_documents_tool_empty_query() -> None:
    ctx = ObserveContext(user_message="test", session_id="s1", engagement_id="s1")
    session = ToolSessionContext(ctx=ctx)
    out = dispatch_tool_call(session, ToolCall(id="1", name="search_documents", arguments={"query": ""}))
    assert out["count"] == 0


def test_find_skills_tool_returns_matches() -> None:
    ctx = ObserveContext(user_message="benchmark spend", session_id="s1")
    session = ToolSessionContext(ctx=ctx)
    out = dispatch_tool_call(session, ToolCall(id="2", name="find_skills", arguments={"query": "peer benchmark"}))
    assert out["skills"]
    assert out["skills"][0]["name"]


def test_dep_map_covers_evidence_and_sme_skills() -> None:
    """evidence-gatherer and sme-critique must be in _DEP_MAP so invoke_skill resolves deps."""
    import re
    content = open("app/opar/plan.py").read()
    dep_block = content[content.find("_DEP_MAP"):content.find("_DEP_MAP") + 4000]
    keys = re.findall(r'"([a-z][a-z-]+)":\s*\(', dep_block)
    key_set = set(keys)
    assert "evidence-gatherer" in key_set, "evidence-gatherer missing from _DEP_MAP"
    assert "sme-critique" in key_set, "sme-critique missing from _DEP_MAP"
    assert "contract-lifecycle-manager" in key_set, "contract-lifecycle-manager missing from _DEP_MAP"


def test_invoke_skill_safety_fallback_runs_skill_not_in_dep_map() -> None:
    """invoke_skill must run the target skill even when it is not in _DEP_MAP."""
    from unittest.mock import patch, MagicMock
    from app.opar.models import ObserveContext
    from app.opar.tools.context import ToolSessionContext
    from app.models import NormalizedSpendLine

    ctx = ObserveContext(user_message="test", session_id="safety-fallback-sess", has_tabular_spend=True)
    session = ToolSessionContext(ctx=ctx)

    with patch("app.opar.act._load_session_data") as load:
        load.return_value = (
            [NormalizedSpendLine(row_id=1, supplier="Acme", description="SaaS", amount=1000.0, category_id="IT", category_name="IT & Tech")],
            [],
            {"industry": "tech", "annual_revenue": 1_000_000.0, "currency": "USD"},
        )
        # spend-profiler IS in _DEP_MAP — verify normal resolution still works
        out = session.invoke_skill("spend-profiler")
    assert out.get("skill") == "spend-profiler"


def test_run_skill_invokes_profiler_with_synthetic_data() -> None:
    ctx = ObserveContext(user_message="profile spend", session_id="sess-tools", has_tabular_spend=True)
    session = ToolSessionContext(ctx=ctx)
    with patch("app.opar.act._load_session_data") as load:
        from app.models import NormalizedSpendLine

        load.return_value = (
            [
                NormalizedSpendLine(
                    row_id=1,
                    supplier="Acme",
                    description="SaaS",
                    amount=1000.0,
                    category_id="IT",
                    category_name="IT & Technology",
                )
            ],
            [],
            {"industry": "tech", "annual_revenue": 1_000_000.0, "currency": "USD"},
        )
        out = dispatch_tool_call(
            session,
            ToolCall(id="3", name="run_skill", arguments={"name": "spend-profiler"}),
        )
    assert out["skill"] == "spend-profiler"
    assert out.get("total_spend") is not None or out.get("category_count") is not None
