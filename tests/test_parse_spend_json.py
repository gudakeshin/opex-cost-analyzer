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
