"""Large-cap SLO harness — 1M synthetic rows against local API."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

BASE_URL = os.getenv("OPEX_BASE_URL", "http://127.0.0.1:8000")
TARGET_ROWS = int(os.getenv("OPEX_PERF_TARGET_ROWS", "1_000_000").replace("_", ""))
INGEST_BUDGET_SECS = float(os.getenv("OPEX_1M_INGEST_BUDGET_SECS", "30"))
QUERY_BUDGET_SECS = float(os.getenv("OPEX_1M_QUERY_BUDGET_SECS", "0.2"))


def run_curl(args: list[str]) -> dict:
    completed = subprocess.run(args, capture_output=True, text=True, check=True)
    return json.loads(completed.stdout)


def create_session() -> str:
    payload = json.dumps(
        {"company_name": "Perf1M Co", "industry": "technology", "annual_revenue": 5_000_000_000}
    )
    data = run_curl(
        [
            "curl", "-s", "-X", "POST", f"{BASE_URL}/api/sessions",
            "-H", "Content-Type: application/json", "-d", payload,
        ]
    )
    return data["session_id"]


def build_csv(path: Path, rows: int) -> None:
    with path.open("w", encoding="utf-8") as fh:
        fh.write("supplier,description,amount,category,business unit\n")
        for i in range(rows):
            fh.write(f"Vendor{i % 500},line {i},100,CAT_{i % 20},BU_{i % 10}\n")


def main() -> None:
    sid = create_session()
    with tempfile.TemporaryDirectory() as tmp:
        csv_path = Path(tmp) / "spend_1m.csv"
        print(f"Building {TARGET_ROWS:,} row CSV…")
        build_csv(csv_path, TARGET_ROWS)
        t0 = time.monotonic()
        run_curl(
            [
                "curl", "-s", "-X", "POST", f"{BASE_URL}/api/sessions/{sid}/upload",
                "-F", f"file=@{csv_path}",
            ]
        )
        ingest_s = time.monotonic() - t0
        print(f"Ingest: {ingest_s:.1f}s (budget {INGEST_BUDGET_SECS}s)")
        assert ingest_s < INGEST_BUDGET_SECS, f"Ingest SLO missed: {ingest_s:.1f}s"

        sql = json.dumps({
            "sql": "SELECT category, SUM(amount) AS spend FROM spend GROUP BY category ORDER BY spend DESC",
            "limit": 50,
        })
        t1 = time.monotonic()
        result = run_curl(
            [
                "curl", "-s", "-X", "POST", f"{BASE_URL}/api/v1/query/{sid}",
                "-H", "Content-Type: application/json", "-d", sql,
            ]
        )
        query_s = time.monotonic() - t1
        print(f"Warm aggregate: {query_s * 1000:.0f}ms (budget {QUERY_BUDGET_SECS * 1000:.0f}ms)")
        assert query_s < QUERY_BUDGET_SECS, f"Query SLO missed: {query_s:.3f}s"
        print(f"OK — {result.get('row_count')} groups returned")


if __name__ == "__main__":
    main()
