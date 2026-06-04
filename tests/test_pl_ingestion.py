from __future__ import annotations

from pathlib import Path

import pytest

from app.services.analysis import load_taxonomy
from app.services.ingestion import (
    _best_amount_column_match,
    _column_amount_score,
    parse_spend_file_with_report,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "spend"
SAMPLES = Path(__file__).resolve().parents[1] / "data" / "samples"


def test_unnamed_numeric_column_beats_cost_label_column() -> None:
    import pandas as pd

    frame = pd.DataFrame(
        {
            "Operating Expenses": ["", "Operating Expenses", ""],
            "I. Cost of Goods Sold (COGS)": [
                "Raw Materials Consumed",
                "Salaries, Wages & Bonus",
                "COGS Subtotal",
            ],
            "Unnamed: 2": [68500.5, 3105.0, None],
        }
    )
    cols = [str(c) for c in frame.columns]
    assert _column_amount_score("Unnamed: 2", frame["Unnamed: 2"]) > _column_amount_score(
        "I. Cost of Goods Sold (COGS)", frame["I. Cost of Goods Sold (COGS)"]
    )
    assert _best_amount_column_match(cols, frame) == "Unnamed: 2"


def test_parse_pnl_expense_summary_csv(tmp_path: Path) -> None:
    src = SAMPLES / "pnl_expense_summary_sample.csv"
    target = tmp_path / src.name
    target.write_bytes(src.read_bytes())
    lines, report = parse_spend_file_with_report(target, load_taxonomy())
    assert len(lines) >= 5
    assert sum(line.amount for line in lines) > 0
    assert report.get("layout") == "hierarchical_expense"
    assert report.get("quality", {}).get("zero_spend_warning") is False
    assert report["quality"]["rows_with_amount"] == len(lines)
    assert any("Power" in (line.description or "") for line in lines)


def test_parse_spend_ledger_sample_csv(tmp_path: Path) -> None:
    src = SAMPLES / "spend_ledger_sample.csv"
    target = tmp_path / src.name
    target.write_bytes(src.read_bytes())
    lines, report = parse_spend_file_with_report(target, load_taxonomy())
    assert len(lines) == 10
    assert lines[0].supplier == "Infosys Ltd"
    assert report.get("quality", {}).get("zero_spend_warning") is False


def test_parse_hul_india_spend_ledger_fy25(tmp_path: Path) -> None:
    src = SAMPLES / "hul_india_spend_ledger_fy25.csv"
    target = tmp_path / src.name
    target.write_bytes(src.read_bytes())
    lines, report = parse_spend_file_with_report(target, load_taxonomy())
    assert len(lines) >= 30
    assert sum(line.amount for line in lines) > 0
    assert report.get("quality", {}).get("zero_spend_warning") is False
    suppliers = {line.supplier for line in lines}
    assert "GroupM India" in suppliers
    assert any(
        "Trade Promotion" in (line.supplier or "") or "Trade Promotion" in (line.description or "")
        for line in lines
    )


def test_parse_hul_india_pnl_expense_fy25(tmp_path: Path) -> None:
    src = SAMPLES / "hul_india_pnl_expense_fy25.csv"
    target = tmp_path / src.name
    target.write_bytes(src.read_bytes())
    lines, report = parse_spend_file_with_report(target, load_taxonomy())
    assert len(lines) >= 8
    assert sum(line.amount for line in lines) > 0
    assert report.get("layout") == "hierarchical_expense"
    assert any("Advertising" in (line.description or "") for line in lines)


def test_zero_spend_warning_when_amount_column_is_text_only(tmp_path: Path) -> None:
    csv_path = tmp_path / "bad_mapping.csv"
    csv_path.write_text(
        "Line Item,Cost Column\n"
        "Raw Materials,Not A Number\n"
        "Power & Fuel,Also Text\n",
        encoding="utf-8",
    )
    lines, report = parse_spend_file_with_report(csv_path, load_taxonomy())
    assert len(lines) == 0
    assert report.get("quality", {}).get("zero_spend_warning") is True


@pytest.mark.skipif(
    not (FIXTURES / "pnl_belrise_style.xlsx").is_file(),
    reason="Belrise-style fixture not present",
)
def test_parse_belrise_style_workbook_fixture() -> None:
    path = FIXTURES / "pnl_belrise_style.xlsx"
    lines, report = parse_spend_file_with_report(path, load_taxonomy())
    assert len(lines) >= 10
    assert sum(line.amount for line in lines) > 1000
    assert report.get("layout") == "hierarchical_expense"
