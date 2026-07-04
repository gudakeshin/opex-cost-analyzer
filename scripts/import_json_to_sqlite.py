#!/usr/bin/env python3
"""One-time (re-runnable/idempotent) import: copy existing JSON manifests
under data/engagements/ and data/uploads/ into the SQLite database used by
REPOSITORY_BACKEND=sqlite.

The same import runs automatically at app startup when the sqlite backend is
active and the database is empty (app/db/bootstrap.py); this CLI exists for
manual re-syncs, dry-run validation, and importing into a non-default path.

Reuses the existing corruption-salvage readers (via
app.services.engagements_store.read_engagement_manifest_from_json and
app.storage.read_json), so any manifest the JSON backend can currently serve
gets imported too — including ones with the "Extra data" concurrent-write
corruption that app/storage.py salvages around.

Safe to re-run: repository .save() is an upsert, so running this again after
more JSON writes have happened re-syncs SQLite from the current JSON state.

Usage:
    PYTHONPATH=. python3 scripts/import_json_to_sqlite.py                # import
    PYTHONPATH=. python3 scripts/import_json_to_sqlite.py --dry-run      # validate only, no writes
    PYTHONPATH=. python3 scripts/import_json_to_sqlite.py --db-path /tmp/opex.db
"""
from __future__ import annotations

import argparse
import os
import sys


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Read and validate manifests only; do not write to SQLite.",
    )
    parser.add_argument(
        "--db-path", default=None,
        help="Override SQLITE_DB_PATH for this run (default: data/opex.db).",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    if args.db_path:
        # Must be set before app.config is imported — it reads the env once.
        os.environ["SQLITE_DB_PATH"] = args.db_path

    from app.config import SQLITE_DB_PATH
    from app.db.bootstrap import import_json_manifests
    from app.repositories.sqlite_store import SqliteEngagementRepository, SqliteSessionRepository

    mode = "DRY RUN — no writes" if args.dry_run else "importing"
    print(f"Target database: {SQLITE_DB_PATH} ({mode})\n")

    counts = import_json_manifests(dry_run=args.dry_run, echo=print)
    eng_ok, eng_failed = counts["engagements_ok"], counts["engagements_skipped"]
    sess_ok, sess_failed = counts["sessions_ok"], counts["sessions_skipped"]

    print(
        f"\nSummary: engagements {eng_ok} ok / {eng_failed} skipped, "
        f"sessions {sess_ok} ok / {sess_failed} skipped"
    )

    if not args.dry_run:
        verify_engagements = len(SqliteEngagementRepository().list_all())
        verify_sessions = len(SqliteSessionRepository().list_ids())
        print(f"Verification: {verify_engagements} engagement row(s), {verify_sessions} session row(s) in {SQLITE_DB_PATH}")
        if verify_engagements < eng_ok or verify_sessions < sess_ok:
            print("WARNING: row counts after import are lower than imported counts — investigate before cutover.")
            return 1

    if eng_failed or sess_failed:
        print("\nSome manifests were skipped — review before treating SQLite as authoritative.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
