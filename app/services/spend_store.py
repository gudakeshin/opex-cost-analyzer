"""Analytical spend store: per-document Parquet + a DuckDB catalog per engagement.

Layout (under ENGAGEMENTS_DIR/{engagement_id}/spend/):
    {document_id}.parquet   — normalized spend lines for one ingested document
                              (mirrors the per-document spend_lines.json cache;
                              replacing a document replaces one file)
    session_{session_id}.parquet — session-local uploads synced via ensure_synced
    adjustments.parquet     — line-level conflict/consolidation adjustments,
                              keyed by the same spend_line_key used by
                              app/services/spend_line_merge.py
    catalog.duckdb          — derived, rebuilt from the Parquet files:
                                spend_raw    table: as-ingested lines + line_key
                                adjustments  table: may be empty
                                spend        view : effective lines (reconciled
                                             amounts applied, eliminated lines
                                             excluded) — what "spend" means for
                                             ad-hoc queries

Safety model for ad-hoc SQL (shared by the query router and the agent tool):
readers open catalog.duckdb read_only with enable_external_access=false and
lock_configuration=true — native table scans work, but read_csv/ATTACH/COPY
and re-enabling external access are all PermissionExceptions. On top of that
run_sql() accepts a single SELECT/WITH statement only (checked via
duckdb.extract_statements, not regex), wraps it in an outer LIMIT, and
interrupts the connection on timeout.

DuckDB/pyarrow are hard dependencies in requirements.txt but imports stay
lazy/soft (is_available()) so environments without them degrade to the
in-memory path instead of failing at import time.
"""
from __future__ import annotations

import contextlib
import shutil
import threading
import time
import typing
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

from app.config import ENGAGEMENTS_DIR, logger
from app.models import NormalizedSpendLine
from app.services.spend_line_merge import spend_line_key

_KEY_SEP = "\x1f"

# Columns added on top of NormalizedSpendLine's own fields.
_EXTRA_COLUMNS = ("document_id", "line_key")

_ADJUSTMENT_COLUMNS = (
    "line_key",
    "consolidation_eliminated",
    "reconciled_amount",
    "conflict_flag",
    "conflict_resolution",
    "supplier_override",
)

_MAX_RESULT_ROWS = 10_000
_DEFAULT_TIMEOUT_S = 10.0


class SpendStoreUnavailable(RuntimeError):
    """duckdb/pyarrow not installed, or no data has been written yet."""


class SpendQueryError(ValueError):
    """The submitted SQL was rejected or failed to execute."""


def is_available() -> bool:
    try:
        import duckdb  # noqa: F401
        import pyarrow  # noqa: F401
        return True
    except ImportError:
        return False


def line_key_str(line: NormalizedSpendLine) -> str:
    return _KEY_SEP.join(spend_line_key(line))


def _strip_optional(annotation: Any) -> Any:
    origin = typing.get_origin(annotation)
    if origin is typing.Union or str(origin) == "types.UnionType":
        args = [a for a in typing.get_args(annotation) if a is not type(None)]
        if len(args) == 1:
            return _strip_optional(args[0])
    return annotation


def _arrow_schema():
    import pyarrow as pa

    type_map = {bool: pa.bool_(), int: pa.int64(), float: pa.float64(), str: pa.string()}
    fields = []
    for name, field in NormalizedSpendLine.model_fields.items():
        ann = _strip_optional(field.annotation)
        fields.append(pa.field(name, type_map.get(ann, pa.string())))
    for name in _EXTRA_COLUMNS:
        fields.append(pa.field(name, pa.string()))
    return pa.schema(fields)


def _lines_to_table(lines: Sequence[NormalizedSpendLine], document_id: str):
    import pyarrow as pa

    schema = _arrow_schema()
    columns: Dict[str, list] = {f.name: [] for f in schema}
    for line in lines:
        dumped = line.model_dump(mode="json")
        key = line_key_str(line)
        for f in schema:
            if f.name == "document_id":
                columns[f.name].append(document_id)
            elif f.name == "line_key":
                columns[f.name].append(key)
            else:
                value = dumped.get(f.name)
                if value is not None and f.type == pa.string() and not isinstance(value, str):
                    value = str(value)
                columns[f.name].append(value)
    return pa.table(columns, schema=schema)


@dataclass
class QueryResult:
    columns: List[str]
    rows: List[List[Any]]
    row_count: int
    truncated: bool
    elapsed_ms: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "columns": self.columns,
            "rows": self.rows,
            "row_count": self.row_count,
            "truncated": self.truncated,
            "elapsed_ms": round(self.elapsed_ms, 1),
        }


def validate_readonly_sql(sql: str) -> str:
    """Accept exactly one SELECT (or WITH … SELECT) statement; raise otherwise.

    Uses duckdb's own parser via extract_statements — comments, string
    literals, and casing are all handled by the real grammar, not a regex.
    """
    import duckdb

    text = (sql or "").strip().rstrip(";").strip()
    if not text:
        raise SpendQueryError("Empty SQL")
    try:
        statements = duckdb.extract_statements(text)
    except Exception as exc:
        raise SpendQueryError(f"SQL parse error: {exc}") from exc
    if len(statements) != 1:
        raise SpendQueryError("Exactly one statement is allowed")
    if statements[0].type != duckdb.StatementType.SELECT:
        raise SpendQueryError(
            f"Only SELECT queries are allowed (got {statements[0].type.name})"
        )
    return text


class SpendStore:
    """Per-engagement analytical store. Cheap to construct; all I/O is lazy."""

    def __init__(self, engagement_id: str):
        self.engagement_id = engagement_id
        self.spend_dir = ENGAGEMENTS_DIR / engagement_id / "spend"
        self.catalog_path = self.spend_dir / "catalog.duckdb"

    # -- write path ---------------------------------------------------------

    def _document_path(self, document_id: str) -> Path:
        safe = "".join(c if (c.isalnum() or c in "-_") else "_" for c in document_id)
        return self.spend_dir / f"{safe}.parquet"

    def write_document_lines(
        self, document_id: str, lines: Sequence[NormalizedSpendLine]
    ) -> int:
        """Write (replace) one document's lines. Returns the row count."""
        return self.write_document_batches(document_id, [lines])

    def write_document_batches(
        self,
        document_id: str,
        batches: Iterable[Sequence[NormalizedSpendLine]],
    ) -> int:
        """Stream batches of lines into one Parquet file (chunked ingestion)."""
        import pyarrow.parquet as pq

        self.spend_dir.mkdir(parents=True, exist_ok=True)
        path = self._document_path(document_id)
        tmp = path.with_suffix(".parquet.tmp")
        total = 0
        writer: Optional[pq.ParquetWriter] = None
        try:
            for batch in batches:
                if not batch:
                    continue
                table = _lines_to_table(batch, document_id)
                if writer is None:
                    writer = pq.ParquetWriter(tmp, table.schema)
                writer.write_table(table)
                total += len(batch)
        finally:
            if writer is not None:
                writer.close()
        if total:
            tmp.replace(path)
        else:
            tmp.unlink(missing_ok=True)
            path.unlink(missing_ok=True)
        self._refresh_catalog()
        return total

    def delete_document(self, document_id: str) -> None:
        path = self._document_path(document_id)
        if path.exists():
            path.unlink()
            self._refresh_catalog()

    def write_adjustments(self, adjustments: Sequence[Dict[str, Any]]) -> int:
        """Persist line-level adjustments (see _ADJUSTMENT_COLUMNS).

        Each record must carry line_key; missing fields default to NULL.
        Replaces the whole adjustments set (they are derived from session
        state, which is itself authoritative for user actions).
        """
        import pyarrow as pa
        import pyarrow.parquet as pq

        self.spend_dir.mkdir(parents=True, exist_ok=True)
        path = self.spend_dir / "adjustments.parquet"
        if not adjustments:
            path.unlink(missing_ok=True)
            self._refresh_catalog()
            return 0
        schema = pa.schema(
            [
                pa.field("line_key", pa.string()),
                pa.field("consolidation_eliminated", pa.bool_()),
                pa.field("reconciled_amount", pa.float64()),
                pa.field("conflict_flag", pa.string()),
                pa.field("conflict_resolution", pa.string()),
                pa.field("supplier_override", pa.string()),
            ]
        )
        columns: Dict[str, list] = {f.name: [] for f in schema}
        for rec in adjustments:
            for f in schema:
                columns[f.name].append(rec.get(f.name))
        pq.write_table(pa.table(columns, schema=schema), path)
        self._refresh_catalog()
        return len(adjustments)

    def adjustments_from_lines(
        self, lines: Iterable[NormalizedSpendLine]
    ) -> List[Dict[str, Any]]:
        """Extract adjustment records from adjusted lines (session state shape)."""
        out: List[Dict[str, Any]] = []
        for line in lines:
            has_any = (
                line.consolidation_eliminated
                or line.reconciled_amount is not None
                or bool(line.conflict_resolution)
            )
            if not has_any:
                continue
            out.append(
                {
                    "line_key": line_key_str(line),
                    "consolidation_eliminated": bool(line.consolidation_eliminated),
                    "reconciled_amount": line.reconciled_amount,
                    "conflict_flag": getattr(line, "conflict_flag", None),
                    "conflict_resolution": line.conflict_resolution or None,
                    "supplier_override": (
                        line.supplier if line.conflict_resolution == "gstin_dedup" else None
                    ),
                }
            )
        return out

    def _refresh_catalog(self) -> None:
        """Rebuild catalog.duckdb from the Parquet files (derived data)."""
        import duckdb

        parquets = sorted(
            p for p in self.spend_dir.glob("*.parquet") if p.name != "adjustments.parquet"
        )
        if not parquets:
            # No data left: drop the derived catalog entirely.
            self.catalog_path.unlink(missing_ok=True)
            for suffix in (".wal",):
                Path(f"{self.catalog_path}{suffix}").unlink(missing_ok=True)
            return
        tmp_path = self.catalog_path.with_suffix(".duckdb.rebuild")
        tmp_path.unlink(missing_ok=True)
        con = duckdb.connect(str(tmp_path))
        try:
            con.execute(
                "CREATE OR REPLACE TABLE spend_raw AS "
                "SELECT * FROM read_parquet(?, union_by_name=true)",
                [[str(p) for p in parquets]],
            )
            adj_path = self.spend_dir / "adjustments.parquet"
            if adj_path.exists():
                con.execute(
                    "CREATE OR REPLACE TABLE adjustments AS SELECT * FROM read_parquet(?)",
                    [str(adj_path)],
                )
            else:
                cols = ", ".join(
                    f"{name} " + ("BOOLEAN" if name == "consolidation_eliminated"
                                  else "DOUBLE" if name == "reconciled_amount"
                                  else "VARCHAR")
                    for name in _ADJUSTMENT_COLUMNS
                )
                con.execute(f"CREATE OR REPLACE TABLE adjustments ({cols})")
            # Effective spend for ad-hoc analysis: reconciled amounts applied,
            # consolidation-eliminated lines removed, gstin-dedup supplier
            # renames applied. spend_raw remains available for full detail.
            con.execute(
                """
                CREATE OR REPLACE VIEW spend AS
                SELECT s.* REPLACE (
                    COALESCE(a.reconciled_amount, s.amount) AS amount,
                    COALESCE(a.supplier_override, s.supplier) AS supplier
                )
                FROM spend_raw s
                LEFT JOIN adjustments a USING (line_key)
                WHERE NOT COALESCE(a.consolidation_eliminated, FALSE)
                """
            )
        finally:
            con.close()
        # Atomic-ish swap; readers open by path so a brief window is fine.
        tmp_path.replace(self.catalog_path)

    # -- read path ----------------------------------------------------------

    def has_data(self) -> bool:
        return self.catalog_path.exists()

    @contextlib.contextmanager
    def connect_readonly(self) -> Iterator[Any]:
        """Locked-down read-only connection: external access disabled."""
        import duckdb

        if not self.catalog_path.exists():
            raise SpendStoreUnavailable(
                f"No spend data indexed for engagement {self.engagement_id}"
            )
        con = duckdb.connect(str(self.catalog_path), read_only=True)
        try:
            con.execute("SET enable_external_access=false")
            con.execute("SET lock_configuration=true")
            yield con
        finally:
            con.close()

    def run_sql(
        self,
        sql: str,
        *,
        limit: int = _MAX_RESULT_ROWS,
        timeout_s: float = _DEFAULT_TIMEOUT_S,
    ) -> QueryResult:
        """Execute one validated SELECT with row cap and interrupt timeout."""
        limit = max(1, min(int(limit or _MAX_RESULT_ROWS), _MAX_RESULT_ROWS))
        text = validate_readonly_sql(sql)
        started = time.monotonic()
        with self.connect_readonly() as con:
            timer = threading.Timer(timeout_s, con.interrupt)
            timer.start()
            try:
                cursor = con.execute(
                    f"SELECT * FROM ({text}) __q LIMIT {limit + 1}"
                )
                rows = cursor.fetchall()
                columns = [d[0] for d in cursor.description]
            except SpendQueryError:
                raise
            except Exception as exc:
                message = str(exc)
                if "INTERRUPT" in message.upper():
                    raise SpendQueryError(
                        f"Query exceeded the {timeout_s:.0f}s time limit"
                    ) from exc
                raise SpendQueryError(message) from exc
            finally:
                timer.cancel()
        truncated = len(rows) > limit
        rows = rows[:limit]
        return QueryResult(
            columns=columns,
            rows=[list(r) for r in rows],
            row_count=len(rows),
            truncated=truncated,
            elapsed_ms=(time.monotonic() - started) * 1000.0,
        )

    def line_count(self, *, effective: bool = True) -> int:
        table = "spend" if effective else "spend_raw"
        with self.connect_readonly() as con:
            return int(con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

    def aggregate(
        self,
        *,
        group_by: Sequence[str],
        metrics: Optional[Dict[str, str]] = None,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 1000,
        order_by: Optional[str] = None,
    ) -> QueryResult:
        """Structured pushdown for skills: identifiers are validated against the
        actual schema, values always bind as parameters."""
        metrics = metrics or {"total_amount": "SUM(amount)", "line_count": "COUNT(*)"}
        with self.connect_readonly() as con:
            valid_cols = {
                r[0] for r in con.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_name='spend_raw'"
                ).fetchall()
            }
        for col in list(group_by) + list((filters or {}).keys()):
            if col not in valid_cols:
                raise SpendQueryError(f"Unknown column: {col}")
        select_parts = list(group_by) + [f"{expr} AS {name}" for name, expr in metrics.items()]
        sql = f"SELECT {', '.join(select_parts)} FROM spend"
        params: List[Any] = []
        if filters:
            clauses = []
            for col, value in filters.items():
                if isinstance(value, (list, tuple)):
                    clauses.append(f"{col} IN ({', '.join('?' for _ in value)})")
                    params.extend(value)
                else:
                    clauses.append(f"{col} = ?")
                    params.append(value)
            sql += " WHERE " + " AND ".join(clauses)
        if group_by:
            sql += f" GROUP BY {', '.join(group_by)}"
        order = order_by or (list(metrics.keys())[0] + " DESC" if metrics else None)
        if order:
            sql += f" ORDER BY {order}"
        sql += f" LIMIT {max(1, min(int(limit), _MAX_RESULT_ROWS))}"

        started = time.monotonic()
        with self.connect_readonly() as con:
            cursor = con.execute(sql, params)
            rows = cursor.fetchall()
            columns = [d[0] for d in cursor.description]
        return QueryResult(
            columns=columns,
            rows=[list(r) for r in rows],
            row_count=len(rows),
            truncated=False,
            elapsed_ms=(time.monotonic() - started) * 1000.0,
        )

    def to_normalized_lines(
        self,
        *,
        where_sql: Optional[str] = None,
        limit: Optional[int] = None,
        effective: bool = True,
    ) -> List[NormalizedSpendLine]:
        """Bounded materialization back into model objects for legacy skills.

        With effective=True, reconciled amounts / supplier renames are already
        applied and eliminated lines are dropped — matching what
        merge_persisted_line_adjustments produces minus eliminated rows;
        effective=False returns the raw ingested lines.
        """
        table = "spend" if effective else "spend_raw"
        sql = f"SELECT * FROM {table}"
        if where_sql:
            sql += f" WHERE {where_sql}"
        if limit:
            sql += f" LIMIT {int(limit)}"
        field_names = set(NormalizedSpendLine.model_fields)
        out: List[NormalizedSpendLine] = []
        with self.connect_readonly() as con:
            cursor = con.execute(sql)
            columns = [d[0] for d in cursor.description]
            for row in cursor.fetchall():
                record = {
                    col: val for col, val in zip(columns, row)
                    if col in field_names and val is not None
                }
                out.append(NormalizedSpendLine(**record))
        return out

    def document_lines(self, document_id: str) -> List[NormalizedSpendLine]:
        """Raw lines for one document (spend_lines.json fallback path)."""
        path = self._document_path(document_id)
        if not path.exists():
            return []
        import duckdb

        field_names = set(NormalizedSpendLine.model_fields)
        con = duckdb.connect()
        try:
            cursor = con.execute("SELECT * FROM read_parquet(?)", [str(path)])
            columns = [d[0] for d in cursor.description]
            return [
                NormalizedSpendLine(**{
                    col: val for col, val in zip(columns, row)
                    if col in field_names and val is not None
                })
                for row in cursor.fetchall()
            ]
        finally:
            con.close()

    def export_sql(
        self,
        sql: str,
        path: Path,
        *,
        fmt: str = "csv",
        limit: int = 1_000_000,
    ) -> int:
        """Materialize a validated SELECT to disk (csv or parquet). Returns row count."""
        import csv

        limit = max(1, min(int(limit), 1_000_000))
        result = self.run_sql(sql, limit=limit)
        path.parent.mkdir(parents=True, exist_ok=True)
        if fmt == "parquet":
            import pyarrow as pa
            import pyarrow.parquet as pq

            columns = {name: [] for name in result.columns}
            for row in result.rows:
                for i, name in enumerate(result.columns):
                    columns[name].append(row[i])
            pq.write_table(pa.table(columns), path)
        else:
            with path.open("w", newline="", encoding="utf-8") as fh:
                writer = csv.writer(fh)
                writer.writerow(result.columns)
                writer.writerows(result.rows)
        return result.row_count

    def destroy(self) -> None:
        """Remove all analytical data for this engagement."""
        if self.spend_dir.exists():
            shutil.rmtree(self.spend_dir, ignore_errors=True)


# -- module-level helpers (soft-fail wrappers used by the pipeline) -----------

def write_document_spend_lines(
    engagement_id: str, document_id: str, lines: Sequence[NormalizedSpendLine]
) -> bool:
    """Best-effort Parquet write from the document pipeline; never raises."""
    if not is_available():
        return False
    try:
        SpendStore(engagement_id).write_document_lines(document_id, lines)
        return True
    except Exception:
        logger.warning(
            '"spend_store_write_failed engagement_id=%s document_id=%s"',
            engagement_id, document_id, exc_info=True,
        )
        return False


def delete_document_spend_lines(engagement_id: str, document_id: str) -> None:
    if not is_available():
        return
    try:
        SpendStore(engagement_id).delete_document(document_id)
    except Exception:
        logger.warning(
            '"spend_store_delete_failed engagement_id=%s document_id=%s"',
            engagement_id, document_id, exc_info=True,
        )
