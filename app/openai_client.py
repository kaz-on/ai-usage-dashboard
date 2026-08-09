from __future__ import annotations

import asyncio
from typing import Any, Protocol

import httpx

COMPLETION_GROUP_BY = [
    "project_id",
    "user_id",
    "api_key_id",
    "model",
    "batch",
    "service_tier",
]
COST_GROUP_BY = ["project_id", "line_item", "api_key_id"]


class UsageClient(Protocol):
    async def get_completions(self, start_time: int, end_time: int) -> list[dict[str, Any]]:
        """Return all completion usage buckets in the requested interval."""

    async def get_costs(self, start_time: int, end_time: int) -> list[dict[str, Any]]:
        """Return all cost buckets in the requested interval."""


class OpenAIUsageClient:
    def __init__(
        self,
        admin_key: str,
        *,
        base_url: str = "https://api.openai.com/v1",
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {admin_key}"},
            timeout=30,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get_completions(self, start_time: int, end_time: int) -> list[dict[str, Any]]:
        return await self._get_all(
            "/organization/usage/completions",
            {
                "start_time": start_time,
                "end_time": end_time,
                "bucket_width": "1d",
                "limit": 31,
                "group_by": COMPLETION_GROUP_BY,
            },
        )

    async def get_costs(self, start_time: int, end_time: int) -> list[dict[str, Any]]:
        return await self._get_all(
            "/organization/costs",
            {
                "start_time": start_time,
                "end_time": end_time,
                "bucket_width": "1d",
                "limit": 180,
                "group_by": COST_GROUP_BY,
            },
        )

    async def _get_all(self, path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        buckets: list[dict[str, Any]] = []
        page: str | None = None
        while True:
            page_params = dict(params)
            if page:
                page_params["page"] = page
            response = await self._request(path, page_params)
            buckets.extend(response.get("data", []))
            if not response.get("has_more"):
                return buckets
            page = response.get("next_page")
            if not page:
                raise RuntimeError("OpenAI API returned has_more without next_page")

    async def _request(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        for attempt in range(3):
            response = await self._client.get(path, params=params)
            if response.status_code not in {429, 500, 502, 503, 504}:
                response.raise_for_status()
                return response.json()
            if attempt < 2:
                await asyncio.sleep(2**attempt)
        response.raise_for_status()
        raise AssertionError("unreachable")
