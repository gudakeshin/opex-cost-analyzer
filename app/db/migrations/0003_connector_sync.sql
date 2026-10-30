-- Per-engagement connector watermarks for delta sync.
CREATE TABLE IF NOT EXISTS connector_watermarks (
    engagement_id TEXT NOT NULL,
    connector_type TEXT NOT NULL,
    last_sync_at TEXT,
    cursor_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL,
    PRIMARY KEY (engagement_id, connector_type)
);

-- Job result payload (handlers write JSON on completion).
ALTER TABLE jobs ADD COLUMN result TEXT;
