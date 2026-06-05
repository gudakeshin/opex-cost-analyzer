"""JSON spend ingestion tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.analysis import load_taxonomy
from app.services.ingestion import parse_spend_json


def test_parse_spend_json_array(tmp_path):
    records = [
        {
            "supplier": "Vendor A",
            "description": "SaaS subscription",
            "amount": 25000,
            "category": "IT & Cloud",
            "spend_date": "2024-03-01",
        },
        {
            "supplier": "Vendor B",
            "description": "Consulting",
            "amount": 15000,
            "gl_code": "5100",
        },
    ]
    path = tmp_path / "spend.json"
    path.write_text(json.dumps(records), encoding="utf-8")
    taxonomy = load_taxonomy()
    lines = parse_spend_json(path, taxonomy, reporting_currency="INR")
    assert len(lines) == 2
    assert lines[0].supplier == "Vendor A"
    assert lines[0].amount == 25000
    assert lines[1].supplier == "Vendor B"
    assert lines[1].amount == 15000


def test_parse_spend_json_wrapped_data(tmp_path):
    path = tmp_path / "wrapped.json"
    path.write_text(
        json.dumps({"data": [{"supplier": "X", "amount": 100, "description": "item"}]}),
        encoding="utf-8",
    )
    lines = parse_spend_json(path, load_taxonomy())
    assert len(lines) == 1
    assert lines[0].amount == 100


# ---------------------------------------------------------------------------
# Quality report enrichment (P0-4 fix) — JSON path must now produce quality flags
# ---------------------------------------------------------------------------

def test_parse_spend_json_report_has_quality_flags(tmp_path):
    """parse_spend_json_with_report must include quality.rows_with_amount and zero_spend_warning."""
    from app.services.ingestion import parse_spend_json_with_report

    records = [{"supplier": "A", "amount": 500, "description": "item"}]
    path = tmp_path / "spend.json"
    path.write_text(json.dumps(records), encoding="utf-8")
    _, report = parse_spend_json_with_report(path, load_taxonomy())
    assert "quality" in report
    assert "rows_with_amount" in report["quality"]
    assert "zero_spend_warning" in report["quality"]
    assert report["quality"]["zero_spend_warning"] is False


def test_parse_spend_json_zero_spend_warning_triggered(tmp_path):
    """All-zero amounts must trigger zero_spend_warning in the quality report."""
    from app.services.ingestion import parse_spend_json_with_report

    records = [
        {"supplier": "A", "amount": 0, "description": "item"},
        {"supplier": "B", "amount": 0.0, "description": "item2"},
    ]
    path = tmp_path / "zeros.json"
    path.write_text(json.dumps(records), encoding="utf-8")
    lines, report = parse_spend_json_with_report(path, load_taxonomy())
    assert lines == []
    assert report["quality"]["zero_spend_warning"] is True


# ---------------------------------------------------------------------------
# Error path tests (P2-17)
# ---------------------------------------------------------------------------

def test_parse_spend_json_malformed_json_raises(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(Exception):
        parse_spend_json(path, load_taxonomy())


def test_parse_spend_json_empty_array_raises(tmp_path):
    path = tmp_path / "empty.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="no spend records"):
        parse_spend_json(path, load_taxonomy())


def test_parse_spend_json_unknown_structure_raises(tmp_path):
    path = tmp_path / "unknown.json"
    path.write_text(json.dumps("just a string"), encoding="utf-8")
    with pytest.raises(ValueError):
        parse_spend_json(path, load_taxonomy())


def test_parse_spend_json_missing_amount_defaults_to_zero(tmp_path):
    """Records without an amount column parse with amount=0 and are filtered."""
    records = [{"supplier": "A", "description": "no amount here"}]
    path = tmp_path / "noamt.json"
    path.write_text(json.dumps(records), encoding="utf-8")
    lines = parse_spend_json(path, load_taxonomy())
    assert lines == []


def test_parse_spend_json_negative_amount(tmp_path):
    """Negative amounts are not zero-filtered and should be ingested."""
    records = [{"supplier": "A", "amount": -100, "description": "credit note"}]
    path = tmp_path / "neg.json"
    path.write_text(json.dumps(records), encoding="utf-8")
    lines = parse_spend_json(path, load_taxonomy())
    assert len(lines) == 1
    assert lines[0].amount == -100
