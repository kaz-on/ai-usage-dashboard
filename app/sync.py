from __future__ import annotations

import asyncio
import json
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from app.database import Database
from app.openai_client import UsageClient

COMPLETION_FIELDS = (
    "num_model_requests",
    "input_tokens",
    "output_tokens",
    "input_cached_tokens",
    "input_uncached_tokens",
    "input_cache_write_tokens",
    "input_text_tokens",
    "input_audio_tokens",
    "input_image_tokens",
    "input_cached_text_tokens",
    "input_cached_audio_tokens",
    "input_cached_image_tokens",
    "output_text_tokens",
    "output_audio_tokens",
    "output_image_tokens",
)


class SyncService:
    def __init__(self, database: Database, client: UsageClient):
        self.database = database
        self.client = client
        self._lock = asyncio.Lock()

    @property
    def is_running(self) -> bool:
        return self._lock.locked()

    async def sync(self, start_time: int, end_time: int) -> dict[str, int]:
        if self._lock.locked():
            raise RuntimeError("A synchronization is already running")
        async with self._lock:
            completion_count = await self._sync_endpoint(
                "completions", start_time, end_time, self.client.get_completions
            )
            cost_count = await self._sync_endpoint(
                "costs", start_time, end_time, self.client.get_costs
            )
            return {"completions": completion_count, "costs": cost_count}

    async def _sync_endpoint(self, endpoint, start_time, end_time, fetcher) -> int:
        run_id = self._start_run(endpoint, start_time, end_time)
        try:
            buckets = await fetcher(start_time, end_time)
            record_count = self._replace(endpoint, start_time, end_time, buckets)
            self._finish_run(run_id, "success", record_count)
            return record_count
        except Exception as exc:
            self._finish_run(run_id, "failed", 0, str(exc)[:1000])
            raise

    def _replace(
        self, endpoint: str, start_time: int, end_time: int, buckets: list[dict[str, Any]]
    ) -> int:
        now = int(time.time())
        rows = [(bucket, result) for bucket in buckets for result in bucket.get("results", [])]
        with self.database.connect() as connection:
            table = "completion_usage" if endpoint == "completions" else "costs"
            connection.execute(
                f"DELETE FROM {table} WHERE bucket_end > ? AND bucket_start < ?",  # noqa: S608
                (start_time, end_time),
            )
            if endpoint == "completions":
                values = [_completion_row(*row, now) for row in rows]
                connection.executemany(COMPLETION_INSERT, values)
            else:
                connection.executemany(COST_INSERT, [_cost_row(*row, now) for row in rows])
        return len(rows)

    def _start_run(self, endpoint: str, start_time: int, end_time: int) -> int:
        with self.database.connect() as connection:
            cursor = connection.execute(
                """INSERT INTO sync_runs
                   (endpoint, started_at, status, range_start, range_end)
                   VALUES (?, ?, 'running', ?, ?)""",
                (endpoint, int(time.time()), start_time, end_time),
            )
            return int(cursor.lastrowid)

    def _finish_run(
        self, run_id: int, status: str, count: int, error_message: str | None = None
    ) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """UPDATE sync_runs
                   SET finished_at = ?, status = ?, record_count = ?, error_message = ?
                   WHERE id = ?""",
                (int(time.time()), status, count, error_message, run_id),
            )


def default_sync_range(
    database: Database, history_days: int, lookback_days: int
) -> tuple[int, int]:
    now = datetime.now(UTC)
    end = int(now.timestamp())
    with database.connect() as connection:
        has_data = connection.execute("SELECT EXISTS(SELECT 1 FROM completion_usage)").fetchone()[0]
    days = lookback_days if has_data else history_days
    start = int((now - timedelta(days=days)).timestamp())
    return start, end


def _text(result: dict[str, Any], name: str) -> str:
    return str(result.get(name) or "")


def _completion_row(bucket, result, synced_at) -> tuple[Any, ...]:
    dimensions = (
        _text(result, "project_id"),
        _text(result, "user_id"),
        _text(result, "api_key_id"),
        _text(result, "model"),
        -1 if result.get("batch") is None else int(result["batch"]),
        _text(result, "service_tier"),
    )
    metrics = tuple(int(result.get(field) or 0) for field in COMPLETION_FIELDS)
    return (
        int(bucket["start_time"]),
        int(bucket["end_time"]),
        *dimensions,
        *metrics,
        json.dumps(result, separators=(",", ":")),
        synced_at,
    )


def _cost_row(bucket, result, synced_at) -> tuple[Any, ...]:
    amount = result.get("amount") or {}
    quantity = result.get("quantity")
    return (
        int(bucket["start_time"]),
        int(bucket["end_time"]),
        _text(result, "project_id"),
        _text(result, "api_key_id"),
        _text(result, "line_item"),
        _text(amount, "currency"),
        str(amount.get("value") or 0),
        None if quantity is None else str(quantity),
        json.dumps(result, separators=(",", ":")),
        synced_at,
    )


COMPLETION_INSERT = f"""
INSERT INTO completion_usage (
    bucket_start, bucket_end, project_id, user_id, api_key_id, model, batch, service_tier,
    {", ".join(COMPLETION_FIELDS)}, raw_json, synced_at
) VALUES ({", ".join("?" for _ in range(8 + len(COMPLETION_FIELDS) + 2))})
"""

COST_INSERT = """
INSERT INTO costs (
    bucket_start, bucket_end, project_id, api_key_id, line_item,
    currency, amount, quantity, raw_json, synced_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""
