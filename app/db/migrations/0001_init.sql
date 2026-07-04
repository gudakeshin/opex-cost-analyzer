-- 0001_init.sql — sessions, engagements, documents.
--
-- Design: hybrid relational + JSON. Columns that are filtered, sorted, or
-- joined on are modeled as real columns; everything else (nested/volatile
-- manifest fields such as diagnostic_result, detection_signals, files[])
-- stays in the `data` JSON column so the repository layer does not have to
-- track every field the app layer ever adds to a manifest dict (both
-- manifest schemas use pydantic `extra="allow"`).
--
-- `documents` is the one exception: it is normalized into its own table
-- because it is a genuine one-to-many collection that is mutated far more
-- often, and independently, than the rest of the engagement manifest (every
-- upload, every parse-status update). Giving it its own rows — rather than
-- rewriting the whole engagement JSON blob on every document status change —
-- is what removes the concurrent-write race that today produces the
-- "Extra data" JSON corruption app/storage.py:41-52 salvages around.

CREATE TABLE IF NOT EXISTS engagements (
    engagement_id   TEXT PRIMARY KEY,
    owner           TEXT,
    company_name    TEXT NOT NULL DEFAULT 'New engagement',
    industry        TEXT NOT NULL DEFAULT '',
    annual_revenue  REAL NOT NULL DEFAULT 0,
    currency        TEXT NOT NULL DEFAULT 'INR',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    -- Full engagement manifest minus `documents` (see documents table below).
    data            TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_engagements_owner ON engagements(owner);
CREATE INDEX IF NOT EXISTS idx_engagements_updated_at ON engagements(updated_at DESC);

CREATE TABLE IF NOT EXISTS documents (
    document_id     TEXT PRIMARY KEY,
    engagement_id   TEXT NOT NULL REFERENCES engagements(engagement_id) ON DELETE CASCADE,
    filename        TEXT NOT NULL,
    content_type    TEXT NOT NULL DEFAULT 'application/octet-stream',
    size_bytes      INTEGER NOT NULL DEFAULT 0,
    raw_path        TEXT NOT NULL DEFAULT '',
    role            TEXT NOT NULL DEFAULT 'context_doc',
    status          TEXT NOT NULL DEFAULT 'pending',
    parse_backend   TEXT,
    error           TEXT,
    uploaded_at     TEXT,
    processed_at    TEXT,
    text_preview    TEXT,
    line_count      INTEGER NOT NULL DEFAULT 0,
    sort_order      INTEGER NOT NULL DEFAULT 0,
    -- Any document fields beyond EngagementDocumentRecord's known set
    -- (e.g. chunk_count, parent_count, indexed, index_backend, warnings —
    -- added by app/services/document_pipeline.py after chunking/indexing).
    extra           TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_documents_engagement_id ON documents(engagement_id, sort_order);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);

CREATE TABLE IF NOT EXISTS sessions (
    session_id      TEXT PRIMARY KEY,
    engagement_id   TEXT REFERENCES engagements(engagement_id) ON DELETE SET NULL,
    owner           TEXT,
    company_name    TEXT NOT NULL DEFAULT 'New engagement',
    industry        TEXT NOT NULL DEFAULT '',
    annual_revenue  REAL NOT NULL DEFAULT 0,
    currency        TEXT NOT NULL DEFAULT 'INR',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    -- Full session manifest, unmodified (files[], diagnostic_result,
    -- deep_research_*, conflict_state, wacc, audience, ...).
    data            TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_sessions_engagement_id ON sessions(engagement_id);
CREATE INDEX IF NOT EXISTS idx_sessions_owner ON sessions(owner);
