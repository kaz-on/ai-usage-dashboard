from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS completion_usage (
    id INTEGER PRIMARY KEY,
    bucket_start INTEGER NOT NULL,
    bucket_end INTEGER NOT NULL,
    project_id TEXT NOT NULL DEFAULT '',
    user_id TEXT NOT NULL DEFAULT '',
    api_key_id TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    batch INTEGER NOT NULL DEFAULT -1,
    service_tier TEXT NOT NULL DEFAULT '',
    num_model_requests INTEGER NOT NULL DEFAULT 0,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    input_cached_tokens INTEGER NOT NULL DEFAULT 0,
    input_uncached_tokens INTEGER NOT NULL DEFAULT 0,
    input_cache_write_tokens INTEGER NOT NULL DEFAULT 0,
    input_text_tokens INTEGER NOT NULL DEFAULT 0,
    input_audio_tokens INTEGER NOT NULL DEFAULT 0,
    input_image_tokens INTEGER NOT NULL DEFAULT 0,
    input_cached_text_tokens INTEGER NOT NULL DEFAULT 0,
    input_cached_audio_tokens INTEGER NOT NULL DEFAULT 0,
    input_cached_image_tokens INTEGER NOT NULL DEFAULT 0,
    output_text_tokens INTEGER NOT NULL DEFAULT 0,
    output_audio_tokens INTEGER NOT NULL DEFAULT 0,
    output_image_tokens INTEGER NOT NULL DEFAULT 0,
    raw_json TEXT NOT NULL,
    synced_at INTEGER NOT NULL,
    UNIQUE (
        bucket_start, bucket_end, project_id, user_id, api_key_id,
        model, batch, service_tier
    )
);

CREATE INDEX IF NOT EXISTS idx_completion_usage_bucket
ON completion_usage(bucket_start, bucket_end);

CREATE TABLE IF NOT EXISTS costs (
    id INTEGER PRIMARY KEY,
    bucket_start INTEGER NOT NULL,
    bucket_end INTEGER NOT NULL,
    project_id TEXT NOT NULL DEFAULT '',
    api_key_id TEXT NOT NULL DEFAULT '',
    line_item TEXT NOT NULL DEFAULT '',
    currency TEXT NOT NULL DEFAULT '',
    amount TEXT NOT NULL DEFAULT '0',
    quantity TEXT,
    raw_json TEXT NOT NULL,
    synced_at INTEGER NOT NULL,
    UNIQUE (
        bucket_start, bucket_end, project_id, api_key_id, line_item, currency
    )
);

CREATE INDEX IF NOT EXISTS idx_costs_bucket ON costs(bucket_start, bucket_end);

CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT '',
    archived_at INTEGER,
    raw_json TEXT NOT NULL,
    synced_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS project_api_keys (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    name TEXT NOT NULL,
    owner_type TEXT NOT NULL DEFAULT '',
    owner_name TEXT NOT NULL DEFAULT '',
    redacted_value TEXT NOT NULL DEFAULT '',
    raw_json TEXT NOT NULL,
    synced_at INTEGER NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_project_api_keys_project
ON project_api_keys(project_id);

CREATE TABLE IF NOT EXISTS sync_runs (
    id INTEGER PRIMARY KEY,
    endpoint TEXT NOT NULL,
    started_at INTEGER NOT NULL,
    finished_at INTEGER,
    status TEXT NOT NULL CHECK (status IN ('running', 'success', 'failed')),
    range_start INTEGER NOT NULL,
    range_end INTEGER NOT NULL,
    record_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT
);
"""


class Database:
    def __init__(self, path: Path | str):
        self.path = Path(path)

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
