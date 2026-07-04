"""One-time JSON → SQLite bootstrap for the sqlite repository backend.

At startup (app/main.py), when REPOSITORY_BACKEND resolves to sqlite and the
database holds no manifests but legacy JSON data exists on disk, the legacy
manifests are imported once so switching backends is seamless. The JSON files
are left untouched as a rollback backup; subsequent startups see a non-empty
database and skip the import.

The import readers deliberately bypass the backend dispatch in
app.routers._shared / app.services.engagements_store (which would read from
the empty SQLite database): sessions via read_json on the manifest path,
engagements via read_engagement_manifest_from_json.
"""
from __future__ import annotations

import contextlib
from typing import Any, Callable, Dict

from app.config import ENGAGEMENTS_DIR, UPLOAD_DIR, logger


def import_json_manifests(
    *, dry_run: bool = False, echo: Callable[[str], None] | None = None
) -> Dict[str, int]:
    """Copy every readable legacy JSON manifest into SQLite.

    Idempotent: repository .save() is an upsert, so re-running after more JSON
    writes re-syncs SQLite from the current JSON state. Returns counts.
    """
    from app.repositories.sqlite_store import (
        SqliteEngagementRepository,
        SqliteSessionRepository,
    )
    from app.services.engagements_store import (
        ManifestReadError,
        read_engagement_manifest_from_json,
    )
    from app.storage import read_json

    say = echo or (lambda _msg: None)
    engagement_repo = SqliteEngagementRepository()
    session_repo = SqliteSessionRepository()
    counts = {"engagements_ok": 0, "engagements_skipped": 0, "sessions_ok": 0, "sessions_skipped": 0}

    engagement_ids = sorted(
        p.name for p in ENGAGEMENTS_DIR.iterdir() if p.is_dir()
    ) if ENGAGEMENTS_DIR.exists() else []
    say(f"Engagements ({len(engagement_ids)} found under {ENGAGEMENTS_DIR}):")
    for eid in engagement_ids:
        try:
            manifest = read_engagement_manifest_from_json(eid)
        except ManifestReadError as exc:
            say(f"  SKIP {eid}: unreadable manifest ({exc.reason})")
            counts["engagements_skipped"] += 1
            continue
        except Exception as exc:  # noqa: BLE001 — surface any manifest as a skip, not a crash
            say(f"  SKIP {eid}: {exc}")
            counts["engagements_skipped"] += 1
            continue
        if not manifest.get("engagement_id"):
            say(f"  SKIP {eid}: no engagement_id in manifest")
            counts["engagements_skipped"] += 1
            continue
        if not dry_run:
            engagement_repo.save(eid, manifest)
        say(f"  {eid}: {len(manifest.get('documents') or [])} document(s)")
        counts["engagements_ok"] += 1

    session_ids = sorted(
        p.name for p in UPLOAD_DIR.iterdir() if p.is_dir() and (p / "manifest.json").is_file()
    ) if UPLOAD_DIR.exists() else []
    say(f"Sessions ({len(session_ids)} found under {UPLOAD_DIR}):")
    for sid in session_ids:
        manifest = read_json(UPLOAD_DIR / sid / "manifest.json", {})
        if not isinstance(manifest, dict) or not manifest:
            say(f"  SKIP {sid}: empty/unreadable manifest")
            counts["sessions_skipped"] += 1
            continue
        manifest.setdefault("session_id", sid)
        if not dry_run:
            try:
                session_repo.save(sid, manifest)
            except Exception as exc:  # noqa: BLE001 — e.g. non-UUID legacy dir names
                say(f"  SKIP {sid}: {exc}")
                counts["sessions_skipped"] += 1
                continue
        counts["sessions_ok"] += 1
    say(f"  {counts['sessions_ok']} session manifest(s) processed, {counts['sessions_skipped']} skipped")
    return counts


def _db_has_manifests() -> bool:
    from app.db import get_connection

    with contextlib.closing(get_connection()) as conn:
        row = conn.execute(
            "SELECT (SELECT COUNT(*) FROM sessions) + (SELECT COUNT(*) FROM engagements)"
        ).fetchone()
    return bool(row[0])


def _json_data_exists() -> bool:
    if ENGAGEMENTS_DIR.exists() and any(
        (p / "manifest.json").is_file() for p in ENGAGEMENTS_DIR.iterdir() if p.is_dir()
    ):
        return True
    return UPLOAD_DIR.exists() and any(
        (p / "manifest.json").is_file() for p in UPLOAD_DIR.iterdir() if p.is_dir()
    )


def import_json_if_needed() -> Dict[str, int] | None:
    """Startup hook: run the one-time import when on the sqlite backend, the
    database has no manifests yet, and legacy JSON data exists. Returns the
    import counts, or None when no import was needed.
    """
    import os

    from app.repositories import active_backend

    if os.getenv("SQLITE_BOOTSTRAP_ENABLED", "true").lower() in ("0", "false", "no"):
        return None
    if active_backend() != "sqlite":
        return None
    try:
        if _db_has_manifests() or not _json_data_exists():
            return None
        counts: Dict[str, Any] = import_json_manifests(
            echo=lambda msg: logger.info('"sqlite_bootstrap %s"', msg)
        )
        logger.info(
            '"sqlite_bootstrap_complete engagements=%d/%d sessions=%d/%d (ok/skipped)"',
            counts["engagements_ok"], counts["engagements_skipped"],
            counts["sessions_ok"], counts["sessions_skipped"],
        )
        return counts
    except Exception:
        # Never block startup on a bootstrap failure — the app still works,
        # just without the legacy data; the CLI script can be run manually.
        logger.exception('"sqlite_bootstrap_failed — run scripts/import_json_to_sqlite.py manually"')
        return None
