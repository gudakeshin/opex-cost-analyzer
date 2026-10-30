"""Ingestion trust fixes: quality scoring, amount parsing, classifier, Indian FY."""
from __future__ import annotations

import pytest

from app.services.analysis import load_taxonomy
from app.services.ingestion import (
    _classify,
    _compute_line_quality_score,
    _derive_fiscal_period,
    _parse_amount_text,
    parse_spend_file_with_report,
)


def test_other_category_earns_no_category_credit():
    full = _compute_line_quality_score("S", "d", "IT", None, None, None)
    other = _compute_line_quality_score("S", "d", "OTHER", None, None, None)
    assert full - other == pytest.approx(0.25)


def test_amount_formats():
    assert _parse_amount_text("₹1,23,456") == (123456.0, False)
    assert _parse_amount_text("(1,234.00)") == (-1234.0, False)
    assert _parse_amount_text("1,234-") == (-1234.0, False)
    assert _parse_amount_text("1.2 crore") == (12_000_000.0, False)
    assert _parse_amount_text("12.5 lakh") == (1_250_000.0, False)
    assert _parse_amount_text("") == (None, True)


def test_ambiguous_cr_suffix_is_not_guessed():
    value, blank = _parse_amount_text("1,234 Cr")
    assert value is None and blank is False


def test_dropped_rows_are_reported(tmp_path):
    csv = tmp_path / "ledger.csv"
    csv.write_text(
        "supplier,description,amount\n"
        "A,cloud hosting,\"₹1,00,000\"\n"
        "B,cloud hosting,\"(500.00)\"\n"
        "C,cloud hosting,12 Cr\n"
        "D,cloud hosting,\n"
    )
    lines, report = parse_spend_file_with_report(csv, load_taxonomy())
    assert [l.amount for l in lines] == [100000.0, -500.0]
    q = report["quality"]
    assert q["rows_input"] == 4
    assert q["rows_dropped_unparseable_amount"] == 1
    assert q["rows_dropped_blank_amount"] == 1
    assert any("could not be read" in w for w in report.get("warnings", []))


def test_classifier_matches_whole_words_only():
    tax = load_taxonomy()
    assert _classify("syntax review", "", tax)[0] == "OTHER"
    assert _classify("elaborate plan", "", tax)[0] == "OTHER"
    assert _classify("AWS cloud hosting", "", tax)[0] == "IT"


def test_indian_fiscal_year():
    assert _derive_fiscal_period("2025-01-15") == (2025, "2025-01")
    assert _derive_fiscal_period("2025-04-01") == (2026, "2025-04")
    assert _derive_fiscal_period("September 2025") == (2026, "2025-09")


def test_semicolon_and_cp1252_csv_is_read(tmp_path):
    csv = tmp_path / "tally.csv"
    csv.write_bytes(
        "supplier;description;amount\nCafé Services;cloud hosting;1000\nAcme;cloud hosting;2000\n".encode("cp1252")
    )
    lines, report = parse_spend_file_with_report(csv, load_taxonomy())
    assert [l.amount for l in lines] == [1000.0, 2000.0]
    assert lines[0].supplier == "Café Services"


def test_foreign_currency_without_fx_rate_is_flagged(tmp_path):
    csv = tmp_path / "fx.csv"
    csv.write_text("supplier,description,amount,currency\nA,cloud hosting,100,USD\nB,cloud hosting,200,INR\n")
    lines, report = parse_spend_file_with_report(csv, load_taxonomy())
    assert report["quality"]["rows_fx_defaulted"] == 1
    assert any("FX rate" in w for w in report["warnings"])
