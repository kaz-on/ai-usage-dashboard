import httpx

from app.config import Settings
from app.main import create_app


def settings(tmp_path):
    return Settings(
        openai_admin_key=None,
        dashboard_subtitle="Example Organization",
        database_path=tmp_path / "dashboard.db",
        sync_interval_minutes=60,
        initial_history_days=90,
        sync_lookback_days=3,
        timezone="Asia/Tokyo",
        mock_mode=False,
    )


def client_for(tmp_path):
    app = create_app(settings(tmp_path))
    app.state.database.initialize()
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_dashboard_and_empty_api(tmp_path):
    async with client_for(tmp_path) as client:
        dashboard = await client.get("/")
        assert dashboard.status_code == 200
        assert "/static/chart.umd.min.js" in dashboard.text
        assert 'id="cost-currency"' in dashboard.text
        assert 'id="input-token-chart"' in dashboard.text
        assert 'id="output-token-chart"' in dashboard.text
        assert "Example Organization" in dashboard.text
        response = await client.get("/api/dashboard?from=2025-01-01&to=2025-01-31")

    assert response.status_code == 200
    assert response.json()["summary"]["usage"]["requests"] == 0


async def test_sync_requires_key(tmp_path):
    async with client_for(tmp_path) as client:
        response = await client.post("/api/sync")

    assert response.status_code == 409


async def test_invalid_date_range(tmp_path):
    async with client_for(tmp_path) as client:
        response = await client.get("/api/dashboard?from=2025-02-01&to=2025-01-01")

    assert response.status_code == 422


async def test_csv_export(tmp_path):
    async with client_for(tmp_path) as client:
        response = await client.get("/api/export/completions.csv?from=2025-01-01&to=2025-01-31")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.text.startswith("bucket_start,bucket_end,project_id")
