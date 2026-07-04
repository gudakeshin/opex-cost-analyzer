#!/usr/bin/env python3
"""One-time (re-runnable/idempotent) import: copy existing JSON manifests
under data/engagements/ and data/uploads/ into the SQLite database used by
REPOSITORY_BACKEND=sqlite.

Reuses the existing corruption-salvage readers (app.services.engagements_store
.read_engagement_manifest, app.storage.read_json) rather than re-parsing JSON
directly, so any manifest the JSON backend can currently serve gets imported
too — including ones with the "Extra data" concurrent-write corruption that
app/storage.py:41-52 salvages around.

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
        help="Read and validate manifests only; do not write to SQLite or repair JSON files.",
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

    from app.config import ENGAGEMENTS_DIR, SQLITE_DB_PATH, UPLOAD_DIR
    from app.repositories.sqlite_store import SqliteEngagementRepository, SqliteSessionRepository
    from app.services.engagements_store import ManifestReadError, read_engagement_manifest
    from app.storage import read_json

    mode = "DRY RUN — no writes" if args.dry_run else "importing"
    print(f"Target database: {SQLITE_DB_PATH} ({mode})\n")

    engagement_repo = SqliteEngagementRepository()
    session_repo = SqliteSessionRepository()

    engagement_ids = sorted(
        p.name for p in ENGAGEMENTS_DIR.iterdir() if p.is_dir()
    ) if ENGAGEMENTS_DIR.exists() else []

    print(f"Engagements ({len(engagement_ids)} found under {ENGAGEMENTS_DIR}):")
    eng_ok = eng_failed = 0
    for eid in engagement_ids:
        try:
            manifest = read_engagement_manifest(eid, auto_repair=not args.dry_run)
        except ManifestReadError as exc:
            print(f"  SKIP {eid}: unreadable manifest ({exc.reason})")
            eng_failed += 1
            continue
        except Exception as exc:  # noqa: BLE001 — surface any manifest as a skip, not a crash
            print(f"  SKIP {eid}: {exc}")
            eng_failed += 1
            continue
        if not manifest.get("engagement_id"):
            print(f"  SKIP {eid}: no engagement_id in manifest")
            eng_failed += 1
            continue
        doc_count = len(manifest.get("documents") or [])
        if not args.dry_run:
            engagement_repo.save(eid, manifest)
        print(f"  {eid}: {doc_count} document(s)")
        eng_ok += 1

    session_ids = sorted(
        p.name for p in UPLOAD_DIR.iterdir() if p.is_dir() and (p / "manifest.json").is_file()
    ) if UPLOAD_DIR.exists() else []

    print(f"\nSessions ({len(session_ids)} found under {UPLOAD_DIR}):")
    sess_ok = sess_failed = 0
    for sid in session_ids:
        manifest = read_json(UPLOAD_DIR / sid / "manifest.json", {})
        if not isinstance(manifest, dict) or not manifest:
            print(f"  SKIP {sid}: empty/unreadable manifest")
            sess_failed += 1
            continue
        manifest.setdefault("session_id", sid)
        if not args.dry_run:
            session_repo.save(sid, manifest)
        sess_ok += 1
    print(f"  {sess_ok} session manifest(s) processed, {sess_failed} skipped")

    print(
        f"\nSummary: engagements {eng_ok} ok / {eng_failed} skipped, "
        f"sessions {sess_ok} ok / {sess_failed} skipped"
    )

    if not args.dry_run:
        verify_engagements = len(engagement_repo.list_all())
        verify_sessions = len(session_repo.list_ids())
        print(f"Verification: {verify_engagements} engagement row(s), {verify_sessions} session row(s) in {SQLITE_DB_PATH}")
        if verify_engagements != eng_ok or verify_sessions != sess_ok:
            print("WARNING: row counts after import do not match imported counts — investigate before cutover.")
            return 1

    if eng_failed or sess_failed:
        print("\nSome manifests were skipped — review before treating SQLite as authoritative.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
