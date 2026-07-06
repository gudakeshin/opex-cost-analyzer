"""Tests for the HTTP NL→SQL surface (generate_sql_from_question + chart specs)."""
from __future__ import annotations

from unittest.mock import patch

import pytest

pytest.importorskip("duckdb")
pytest.importorskip("pyarrow")

from app.models import NormalizedSpendLine
from app.opar.tools.nl_query import generate_sql_from_question
from app.services.query_chart import chart_spec_for_result
from app.services.spend_store import SpendQueryError, SpendStore, write_document_spend_lines


@pytest.fixture()
def store(tmp_path, monkeypatch) -> SpendStore:
    from app.services import spend_store as ss

    monkeypatch.setattr(ss, "ENGAGEMENTS_DIR", tmp_path)
    eid = "eng-nl2sql"
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
    return SpendStore(eid)


def test_rules_path_generates_and_executes(store) -> None:
    out = generate_sql_from_question(store, "top 5 suppliers by spend", execute=True)
    assert out["source"] == "rules"
    assert "GROUP BY supplier" in out["sql"]
    assert out["result"]["row_count"] >= 1
    assert out["repair_trace"] == []


def test_llm_path_used_for_complex_question(store) -> None:
    with patch("app.opar.tools.nl_query._llm_aggregate_or_sql") as llm:
        llm.return_value = "SELECT supplier, SUM(amount) AS spend FROM spend GROUP BY supplier"
        out = generate_sql_from_question(
            store, "vendors where spend grew > 20% QoQ", execute=True
        )
    assert out["source"] == "llm"
    assert out["result"]["row_count"] >= 1


def test_unavailable_when_llm_off_and_rules_miss(store) -> None:
    # Under pytest call_llm_structured returns None, so the LLM tier is inert.
    out = generate_sql_from_question(store, "vendors where spend grew > 20% QoQ")
    assert out["source"] == "unavailable"
    assert out["sql"] is None
    assert out["result"] is None


def test_llm_dml_rejected_by_readonly_validation(store) -> None:
    with patch("app.opar.tools.nl_query._llm_aggregate_or_sql") as llm:
        llm.return_value = "DROP TABLE spend"
        with pytest.raises(SpendQueryError):
            generate_sql_from_question(store, "vendors where spend grew > 20% QoQ")


def test_repair_loop_recovers_from_bad_llm_sql(store) -> None:
    good = "SELECT supplier, SUM(amount) AS spend FROM spend GROUP BY supplier"
    with patch("app.opar.tools.nl_query._llm_aggregate_or_sql") as llm:
        llm.side_effect = [
            "SELECT no_such_column FROM spend",  # initial generation
            good,  # repair attempt
        ]
        out = generate_sql_from_question(
            store, "vendors where spend grew > 20% QoQ", execute=True
        )
    assert out["source"] == "llm"
    assert out["sql"] == good
    assert out["result"]["row_count"] >= 1
    assert len(out["repair_trace"]) == 1


def test_review_gate_returns_sql_without_executing(store) -> None:
    out = generate_sql_from_question(store, "top 3 categories by spend", execute=False)
    assert out["source"] == "rules"
    assert out["sql"]
    assert out["result"] is None


# --------------------------------------------------------------------------- #
# Chart-spec heuristics                                                        #
# --------------------------------------------------------------------------- #

def test_chart_spec_categorical_bar() -> None:
    spec = chart_spec_for_result(
        ["supplier", "spend"],
        [["V1", 100.0], ["V2", 250.0]],
        "top suppliers by spend",
    )
    assert spec is not None
    assert spec["type"] == "bar"
    assert spec["x_key"] == "supplier"
    assert spec["unit"] == "currency"
    assert spec["data"][0] == {"supplier": "V1", "spend": 100.0}


def test_chart_spec_temporal_line() -> None:
    spec = chart_spec_for_result(
        ["fiscal_period", "spend"],
        [["2025-Q1", 10.0], ["2025-Q2", 20.0]],
        "spend over time",
    )
    assert spec is not None
    assert spec["type"] == "line"


def test_chart_spec_share_question_pie() -> None:
    spec = chart_spec_for_result(
        ["category_name", "spend"],
        [["Facilities", 60.0], ["IT", 40.0]],
        "share of spend by category",
    )
    assert spec is not None
    assert spec["type"] == "pie"


def test_chart_spec_none_for_wide_or_nonchartable_results() -> None:
    # Too many rows
    many = [[f"V{i}", float(i)] for i in range(60)]
    assert chart_spec_for_result(["supplier", "spend"], many) is None
    # Two categorical columns
    assert (
        chart_spec_for_result(
            ["supplier", "category_name", "spend"], [["V1", "IT", 1.0]]
        )
        is None
    )
    # No numeric column
    assert chart_spec_for_result(["supplier"], [["V1"]]) is None
    # Empty
    assert chart_spec_for_result(["supplier", "spend"], []) is None
