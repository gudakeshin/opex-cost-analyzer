"""SQLite connection management: WAL mode, busy-timeout, migrations.

This is the concurrency fix the migration is really about. Today,
app.services.manifest_lock and app.routers._shared's session lock fall back
to in-process locks whenever REDIS_URL is unset — meaning concurrent writers
across worker processes/replicas race on the same manifest.json, which is
exactly the failure mode app.storage.read_json:41-52 salvages ("Extra data"
from an interleaved write).

SQLite fixes this without Redis: BEGIN IMMEDIATE acquires the database's
RESERVED lock up front, so a second writer blocks (and retries via
busy_timeout) instead of interleaving bytes into the same file. This holds
across processes on one host; it does not hold across hosts sharing nothing
(see the migration plan's Postgres section for that case).
"""
from __future__ import annotations

import contextlib
import sqlite3
import threading
from pathlib import Path
from typing import Iterator

from app.config import SQLITE_BUSY_TIMEOUT_MS, SQLITE_DB_PATH, logger

_MIGRATIONS_DIR = Path(__file__).parent / "migrations"

# Guards `_schema_ready`, not database access — sqlite3 connections are not
# shared across threads here (get_connection() opens a fresh one per call).
_schema_lock = threading.Lock()
_schema_ready: set[str] = set()


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(
        str(db_path),
        timeout=SQLITE_BUSY_TIMEOUT_MS / 1000,
        isolation_level=None,  # autocommit; we manage transactions explicitly (see transaction()).
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
    return conn


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """Open a connection to *db_path* (default: SQLITE_DB_PATH), applying any
    unapplied migrations first. Callers are responsible for closing it
    (repositories use `with contextlib.closing(get_connection()) as conn:`).
    """
    path = db_path or SQLITE_DB_PATH
    conn = _connect(path)
    ensure_schema(conn, str(path))
    return conn


def ensure_schema(conn: sqlite3.Connection, cache_key: str) -> None:
    """Apply any migration files not yet recorded in schema_migrations.

    `cache_key` (the resolved db path) lets repeated calls against the same
    database skip the check cheaply, while still applying independently to
    distinct databases (e.g. per-test tmp paths).
    """
    with _schema_lock:
        if cache_key in _schema_ready:
            return
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        applied = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
        for migration_path in sorted(_MIGRATIONS_DIR.glob("*.sql")):
            version = migration_path.stem
            if version in applied:
                continue
            conn.executescript(migration_path.read_text(encoding="utf-8"))
            conn.execute(
                "INSERT INTO schema_migrations (version, applied_at) VALUES (?, datetime('now'))",
                (version,),
            )
            logger.info('"sqlite_migration_applied version=%s db=%s"', version, cache_key)
        _schema_ready.add(cache_key)


def reset_schema_cache() -> None:
    """Forget which databases have had migrations applied. Test-only: lets a
    test point SQLITE_DB_PATH at a fresh tmp file and get migrations re-run.
    """
    with _schema_lock:
        _schema_ready.clear()


@contextlib.contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """BEGIN IMMEDIATE — acquire the write lock before any statements run, so
    concurrent writers serialize instead of racing. Commits on success, rolls
    back on any exception.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except Exception:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")
