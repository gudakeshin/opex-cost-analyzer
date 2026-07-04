"""Analytical spend store (app/services/spend_store.py): Parquet + DuckDB catalog."""
from __future__ import annotations

import uuid

import pytest

pytest.importorskip("duckdb")
pytest.importorskip("pyarrow")

from app.models import NormalizedSpendLine
from app.services.spend_line_merge import merge_persisted_line_adjustments
from app.services.spend_store import (
    SpendQueryError,
    SpendStore,
    SpendStoreUnavailable,
    line_key_str,
    validate_readonly_sql,
)


def _line(row_id: int, **kwargs) -> NormalizedSpendLine:
    defaults = {
        "row_id": row_id,
        "supplier": f"Supplier {row_id % 7}",
        "description": f"Line {row_id}",
        "amount": 1000.0 + row_id,
        "category_id": f"CAT_{row_id % 3}",
        "category_name": f"Category {row_id % 3}",
        "source_record_id": f"rec-{row_id}",
        "source_file_hash": "hash-abc",
    }
    defaults.update(kwargs)
    return NormalizedSpendLine(**defaults)


@pytest.fixture
def store(tmp_path, monkeypatch) -> SpendStore:
    monkeypatch.setattr("app.services.spend_store.ENGAGEMENTS_DIR", tmp_path)
    return SpendStore(str(uuid.uuid4()))


def test_write_and_count_roundtrip(store):
    lines = [_line(i) for i in range(1, 51)]
    assert store.write_document_lines("doc-1", lines) == 50
    assert store.has_data()
    assert store.line_count() == 50


def test_document_replace_and_delete(store):
    store.write_document_lines("doc-1", [_line(i) for i in range(1, 11)])
    store.write_document_lines("doc-2", [_line(i) for i in range(11, 16)])
    assert store.line_count() == 15
    # Replace doc-1 with fewer lines.
    store.write_document_lines("doc-1", [_line(i) for i in range(1, 4)])
    assert store.line_count() == 8
    store.delete_document("doc-2")
    assert store.line_count() == 3


def test_sql_query_and_row_cap(store):
    store.write_document_lines("doc-1", [_line(i) for i in range(1, 101)])
    result = store.run_sql("SELECT supplier, SUM(amount) AS total FROM spend GROUP BY supplier")
    assert result.row_count == 7
    assert set(result.columns) == {"supplier", "total"}
    capped = store.run_sql("SELECT * FROM spend", limit=10)
    assert capped.row_count == 10
    assert capped.truncated is True


def test_to_normalized_lines_roundtrip(store):
    original = [_line(i, gl_code=f"GL{i}", business_unit="BU-A") for i in range(1, 21)]
    store.write_document_lines("doc-1", original)
    loaded = store.to_normalized_lines()
    assert len(loaded) == 20
    by_record = {ln.source_record_id: ln for ln in loaded}
    for line in original:
        match = by_record[line.source_record_id]
        assert match.amount == line.amount
        assert match.gl_code == line.gl_code
        assert match.business_unit == "BU-A"


def test_adjustment_overlay_matches_merge_semantics(store):
    """The effective `spend` view must reproduce merge_persisted_line_adjustments
    (minus eliminated rows) exactly — totals drift breaks assert_spend_base_consistent."""
    fresh = [_line(i) for i in range(1, 31)]
    # Prior session: line 5 reconciled to a different amount, line 9 eliminated,
    # line 12 supplier-deduped via gstin.
    prior = [
        fresh[4].model_copy(update={"reconciled_amount": 500.0, "conflict_resolution": "reconciled"}),
        fresh[8].model_copy(update={"consolidation_eliminated": True}),
        fresh[11].model_copy(update={"conflict_resolution": "gstin_dedup", "supplier": "Canonical Supplier Ltd"}),
    ]
    merged = merge_persisted_line_adjustments(fresh, prior)

    store.write_document_lines("doc-1", fresh)
    store.write_adjustments(store.adjustments_from_lines(merged))

    effective = store.to_normalized_lines()
    expected_kept = [ln for ln in merged if not ln.consolidation_eliminated]
    assert len(effective) == len(expected_kept) == 29

    expected_total = sum(
        (ln.reconciled_amount if ln.reconciled_amount is not None else ln.amount)
        for ln in expected_kept
    )
    result = store.run_sql("SELECT SUM(amount) FROM spend")
    assert result.rows[0][0] == pytest.approx(expected_total)

    by_key = {line_key_str(ln): ln for ln in effective}
    assert by_key[line_key_str(fresh[4])].amount == pytest.approx(500.0)
    assert by_key[line_key_str(fresh[11])].supplier == "Canonical Supplier Ltd"
    # Raw view still holds all 30 original lines.
    assert store.line_count(effective=False) == 30


def test_aggregate_pushdown_matches_in_memory(store):
    lines = [_line(i) for i in range(1, 201)]
    store.write_document_lines("doc-1", lines)
    result = store.aggregate(group_by=["category_id"], filters={"supplier": "Supplier 1"})
    expected: dict[str, float] = {}
    for ln in lines:
        if ln.supplier == "Supplier 1":
            expected[ln.category_id] = expected.get(ln.category_id, 0.0) + ln.amount
    got = {row[0]: row[1] for row in result.rows}
    assert got == pytest.approx(expected)


def test_aggregate_rejects_unknown_column(store):
    store.write_document_lines("doc-1", [_line(1)])
    with pytest.raises(SpendQueryError, match="Unknown column"):
        store.aggregate(group_by=["nonexistent_col"])


def test_query_timeout_interrupts(store):
    store.write_document_lines("doc-1", [_line(i) for i in range(1, 2001)])
    # Heavy cross join with an expensive predicate: ~8e9 comparisons, far past 0.05 s.
    with pytest.raises(SpendQueryError, match="time limit"):
        store.run_sql(
            "SELECT COUNT(*) FROM spend a, spend b, spend c "
            "WHERE a.description || b.description LIKE '%' || c.description",
            timeout_s=0.05,
        )


def test_unavailable_before_any_write(store):
    with pytest.raises(SpendStoreUnavailable):
        store.run_sql("SELECT 1")


# ---------------------------------------------------------------------------
# SQL safety
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE spend",
        "DELETE FROM spend",
        "UPDATE spend SET amount = 0",
        "INSERT INTO spend_raw SELECT * FROM spend_raw",
        "CREATE TABLE x AS SELECT 1",
        "SELECT 1; SELECT 2",
        # Config-mutating pragmas parse as SET statements and are rejected;
        # read-only ones (PRAGMA database_list) parse as SELECT and are harmless.
        "PRAGMA memory_limit='100GB'",
        "PRAGMA enable_external_access=true",
        "SET enable_external_access=true",
        "ATTACH '/tmp/evil.db' AS evil",
        "COPY spend TO '/tmp/exfil.csv'",
        "",
    ],
)
def test_validate_rejects_non_select(sql):
    with pytest.raises(SpendQueryError):
        validate_readonly_sql(sql)


def test_validate_accepts_select_and_cte():
    validate_readonly_sql("SELECT * FROM spend LIMIT 5")
    validate_readonly_sql("WITH t AS (SELECT supplier FROM spend) SELECT * FROM t")


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM read_csv('/etc/passwd')",
        "SELECT * FROM read_parquet('/etc/passwd')",
        "SELECT * FROM glob('/*')",
        "SELECT read_text('/etc/passwd')",
    ],
)
def test_filesystem_functions_blocked_at_execution(store, sql):
    store.write_document_lines("doc-1", [_line(1)])
    with pytest.raises(SpendQueryError):
        store.run_sql(sql)


def test_streamed_csv_ingestion_end_to_end(tmp_path, monkeypatch):
    """CSV above the in-memory limit streams into the Parquet store in chunks,
    writes no spend_lines.json, and load_cached_spend_lines reads it back."""
    monkeypatch.setattr("app.services.spend_store.ENGAGEMENTS_DIR", tmp_path)
    # Force the streaming path on a small file.
    monkeypatch.setattr("app.services.ingestion._ROW_MAX", 50)
    monkeypatch.setattr("app.services.ingestion._STREAM_CHUNK_ROWS", 40)

    csv_path = tmp_path / "big.csv"
    rows = ["supplier,description,amount,business unit"]
    rows += [f"Vendor {i % 5},Service line {i},{100 + i},BU-{i % 2}" for i in range(200)]
    csv_path.write_text("\n".join(rows), encoding="utf-8")

    from app.services.document_pipeline import _should_stream_csv, _stream_csv_document

    assert _should_stream_csv(csv_path) is True

    eid, did = str(uuid.uuid4()), str(uuid.uuid4())
    taxonomy: dict = {"categories": []}
    total, report = _stream_csv_document(
        eid, did, csv_path, taxonomy=taxonomy, reporting_currency="INR"
    )
    assert total == 200
    assert report["streamed"] is True

    store = SpendStore(eid)
    assert store.line_count() == 200
    # Chunked ingestion must produce the same totals as one-shot parsing
    # (restore the real limit so the comparison takes the in-memory path).
    monkeypatch.setattr("app.services.ingestion._ROW_MAX", 500_000)
    from app.services.ingestion import parse_spend_file

    one_shot = parse_spend_file(csv_path, taxonomy, reporting_currency="INR")
    assert len(one_shot) == 200
    expected_total = sum(ln.amount for ln in one_shot)
    assert store.run_sql("SELECT SUM(amount) FROM spend").rows[0][0] == pytest.approx(expected_total)
    # Row ids are contiguous across chunks.
    ids = store.run_sql("SELECT MIN(row_id), MAX(row_id), COUNT(DISTINCT row_id) FROM spend").rows[0]
    assert ids == [1, 200, 200]


def test_json_fallback_when_parquet_missing(tmp_path, monkeypatch):
    """load_cached_spend_lines falls back to Parquet when spend_lines.json is absent."""
    monkeypatch.setattr("app.services.spend_store.ENGAGEMENTS_DIR", tmp_path)
    from app.services import document_pipeline

    monkeypatch.setattr(
        "app.services.engagements_store.ENGAGEMENTS_DIR", tmp_path, raising=False
    )
    eid, did = str(uuid.uuid4()), str(uuid.uuid4())
    SpendStore(eid).write_document_lines(did, [_line(i) for i in range(1, 6)])
    loaded = document_pipeline.load_cached_spend_lines(eid, did)
    assert len(loaded) == 5
