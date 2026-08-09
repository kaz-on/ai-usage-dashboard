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


async def test_projects_and_api_keys_follow_list_cursors():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        is_keys = request.url.path.endswith("/api_keys")
        item_prefix = "key" if is_keys else "proj"
        page = 2 if request.url.params.get("after") else 1
        body = {
            "object": "list",
            "data": [{"id": f"{item_prefix}_{page}", "name": f"Name {page}"}],
            "has_more": page == 1,
            "last_id": f"{item_prefix}_1" if page == 1 else f"{item_prefix}_2",
        }
        return httpx.Response(200, content=json.dumps(body), request=request)

    client = OpenAIUsageClient("admin-key", transport=httpx.MockTransport(handler))
    try:
        projects = await client.get_projects()
        keys = await client.get_project_api_keys("proj_1")
    finally:
        await client.aclose()

    assert [project["id"] for project in projects] == ["proj_1", "proj_2"]
    assert [key["id"] for key in keys] == ["key_1", "key_2"]
    assert requests[0].url.params["include_archived"] == "true"
    assert requests[1].url.params["after"] == "proj_1"
    assert requests[2].url.params["owner_project_access"] == "any"
    assert requests[3].url.params["after"] == "key_1"
