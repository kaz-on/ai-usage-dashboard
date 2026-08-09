import json

import httpx

from app.openai_client import COMPLETION_GROUP_BY, OpenAIUsageClient


async def test_completions_follows_cursor_and_sends_group_by():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        page = request.url.params.get("page")
        body = {
            "object": "page",
            "data": [{"start_time": 1 if page is None else 2, "results": []}],
            "has_more": page is None,
            "next_page": "cursor-2" if page is None else None,
        }
        return httpx.Response(200, content=json.dumps(body), request=request)

    client = OpenAIUsageClient("admin-key", transport=httpx.MockTransport(handler))
    try:
        buckets = await client.get_completions(1, 3)
    finally:
        await client.aclose()

    assert len(buckets) == 2
    assert requests[0].url.params.get_list("group_by") == COMPLETION_GROUP_BY
    assert requests[1].url.params["page"] == "cursor-2"
    assert requests[0].headers["Authorization"] == "Bearer admin-key"
