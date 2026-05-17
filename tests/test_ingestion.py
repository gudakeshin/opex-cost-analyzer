from __future__ import annotations

from pathlib import Path

from app.services.analysis import load_taxonomy
from app.services.ingestion import infer_tabular_schema, parse_document, parse_spend_file


def test_parse_spend_file_classifies_rows(tmp_path: Path) -> None:
    csv_path = tmp_path / "spend.csv"
    csv_path.write_text(
        "supplier,description,amount,business unit\n"
        "Amazon,aws cloud invoice,10000,Engineering\n"
        "Deloitte,consulting engagement,5000,Finance\n",
        encoding="utf-8",
    )
    rows = parse_spend_file(csv_path, load_taxonomy())
    assert len(rows) == 2
    assert rows[0].category_id == "IT"
    assert rows[1].category_id == "PROF_SVCS"


def test_parse_document_txt(tmp_path: Path) -> None:
    txt = tmp_path / "context.txt"
    txt.write_text("policy and compliance requirements", encoding="utf-8")
    extracted = parse_document(txt)
    assert "compliance" in extracted


def test_infer_tabular_schema_detects_semantic_roles(tmp_path: Path) -> None:
    csv_path = tmp_path / "schema.csv"
    csv_path.write_text(
        "supplier,description,amount,business unit,country,date\n"
        "Amazon,aws invoice,1200,Engineering,US,2025-01-01\n",
        encoding="utf-8",
    )
    schema = infer_tabular_schema(csv_path)
    semantic_map = schema["semantic_map"]
    assert semantic_map["supplier"] == "supplier"
    assert semantic_map["amount"] == "amount"
    assert semantic_map["business_unit"] == "business unit"
    assert semantic_map["geo"] == "country"
    assert semantic_map["date"] == "date"

