from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path


BASE_URL = os.getenv("OPEX_BASE_URL", "http://127.0.0.1:8000")
# Keep a small multipart headroom under server-side 50MB limit.
TARGET_MB = int(os.getenv("OPEX_PERF_TARGET_MB", "49"))
UPLOAD_BUDGET_SECS = float(os.getenv("OPEX_UPLOAD_BUDGET_SECS", "30"))
ANALYZE_BUDGET_SECS = float(os.getenv("OPEX_ANALYZE_BUDGET_SECS", "60"))


def run_curl(args: list[str]) -> dict:
    completed = subprocess.run(args, capture_output=True, text=True, check=True)
    return json.loads(completed.stdout)


def create_session() -> str:
    payload = json.dumps(
        {"company_name": "Perf50MB Co", "industry": "technology", "annual_revenue": 1_000_000_000}
    )
    data = run_curl(
        [
            "curl",
            "-s",
            "-X",
            "POST",
            f"{BASE_URL}/api/sessions",
            "-H",
            "Content-Type: application/json",
            "-d",
            payload,
        ]
    )
    return data["session_id"]


def build_target_csv(path: Path, target_mb: int) -> None:
    header = "supplier,description,amount,business unit,country\n"
    row = "AWS,cloud hosting services,100,Engineering,US\n"
    target_bytes = target_mb * 1024 * 1024
    with path.open("w", encoding="utf-8") as handle:
        handle.write(header)
        size = len(header.encode("utf-8"))
        while size < target_bytes:
            handle.write(row)
            size += len(row.encode("utf-8"))


def upload_file(session_id: str, path: Path) -> dict:
    return run_curl(
        [
            "curl",
            "-s",
            "-X",
            "POST",
            f"{BASE_URL}/api/upload/{session_id}",
            "-F",
            f"file=@{path}",
        ]
    )


def analyze(session_id: str) -> dict:
    payload = json.dumps(
        {"company_name": "Perf50MB Co", "industry": "technology", "annual_revenue": 1_000_000_000}
    )
    return run_curl(
        [
            "curl",
            "-s",
            "-X",
            "POST",
            f"{BASE_URL}/api/analyze/{session_id}",
            "-H",
            "Content-Type: application/json",
            "-d",
            payload,
        ]
    )


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        csv_path = Path(tmp) / "perf_50mb.csv"
        build_target_csv(csv_path, TARGET_MB)
        actual_mb = csv_path.stat().st_size / (1024 * 1024)
        print(f"Generated CSV: {csv_path} ({actual_mb:.2f} MB)")

        session_id = create_session()
        print(f"Session: {session_id}")

        start_upload = time.perf_counter()
        upload_res = upload_file(session_id, csv_path)
        upload_secs = time.perf_counter() - start_upload
        print(f"Upload response: {upload_res}")
        print(f"Upload duration: {upload_secs:.2f}s (budget {UPLOAD_BUDGET_SECS:.2f}s)")
        upload_ok = "uploaded" in upload_res

        start_analyze = time.perf_counter()
        analysis_res = analyze(session_id)
        analyze_secs = time.perf_counter() - start_analyze
        mid = (
            analysis_res.get("skill_outputs", {})
            .get("value-bridge-calculator", {})
            .get("confidence_bands", {})
            .get("mid", 0.0)
        )
        print(f"Analyze duration: {analyze_secs:.2f}s")
        print(f"Mid-case value identified: {mid:,.2f}")

        if upload_ok and upload_secs <= UPLOAD_BUDGET_SECS:
            print("PASS: Upload met performance budget.")
        else:
            print("FAIL: Upload exceeded performance budget.")

        if analyze_secs <= ANALYZE_BUDGET_SECS:
            print("PASS: Analyze met performance budget.")
        else:
            print("WARN: Analyze exceeded performance budget.")


if __name__ == "__main__":
    main()

