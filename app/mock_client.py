from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

SECONDS_PER_DAY = 86_400


class MockUsageClient:
    """Generate deterministic data so the complete UI can run without an API key."""

    async def get_completions(self, start_time: int, end_time: int) -> list[dict[str, Any]]:
        buckets: list[dict[str, Any]] = []
        for day_index, bucket_start in enumerate(_days(start_time, end_time)):
            results = []
            for project_index, (project, model) in enumerate(
                (("proj_product", "gpt-5-mini"), ("proj_internal", "gpt-4.1-mini"))
            ):
                requests = 70 + (day_index * 13 + project_index * 37) % 120
                input_tokens = requests * (620 + project_index * 180)
                output_tokens = requests * (190 + project_index * 70)
                cached = input_tokens * (25 + (day_index % 4) * 5) // 100
                results.append(
                    {
                        "object": "organization.usage.completions.result",
                        "project_id": project,
                        "user_id": f"user_{project_index + 1}",
                        "api_key_id": f"key_{project_index + 1}",
                        "model": model,
                        "batch": project_index == 1 and day_index % 3 == 0,
                        "service_tier": "default",
                        "num_model_requests": requests,
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "input_cached_tokens": cached,
                        "input_uncached_tokens": input_tokens - cached,
                        "input_cache_write_tokens": 0,
                        "input_text_tokens": input_tokens - cached,
                        "input_cached_text_tokens": cached,
                        "output_text_tokens": output_tokens,
                    }
                )
            buckets.append(_bucket(bucket_start, results))
        return buckets

    async def get_costs(self, start_time: int, end_time: int) -> list[dict[str, Any]]:
        buckets: list[dict[str, Any]] = []
        for day_index, bucket_start in enumerate(_days(start_time, end_time)):
            results = []
            for project_index, project in enumerate(("proj_product", "proj_internal")):
                amount = 2.4 + ((day_index * 17 + project_index * 23) % 90) / 10
                results.append(
                    {
                        "object": "organization.costs.result",
                        "project_id": project,
                        "api_key_id": f"key_{project_index + 1}",
                        "line_item": "Completions",
                        "amount": {"currency": "usd", "value": amount},
                        "quantity": None,
                    }
                )
            buckets.append(_bucket(bucket_start, results))
        return buckets


def _days(start_time: int, end_time: int) -> list[int]:
    start = datetime.fromtimestamp(start_time, UTC).replace(hour=0, minute=0, second=0)
    end = datetime.fromtimestamp(end_time, UTC)
    days: list[int] = []
    current = start
    while current < end:
        days.append(int(current.timestamp()))
        current += timedelta(days=1)
    return days


def _bucket(start: int, results: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "object": "bucket",
        "start_time": start,
        "end_time": start + SECONDS_PER_DAY,
        "results": results,
    }
