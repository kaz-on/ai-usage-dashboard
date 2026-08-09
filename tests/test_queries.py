from app.database import Database
from app.mock_client import MockUsageClient
from app.queries import DashboardFilters, get_dashboard_data, get_filter_options
from app.sync import SyncService


async def test_dashboard_aggregates_mock_data(tmp_path):
    database = Database(tmp_path / "dashboard.db")
    database.initialize()
    start, end = 1_735_689_600, 1_735_862_400
    await SyncService(database, MockUsageClient()).sync(start, end)

    data = get_dashboard_data(database, DashboardFilters(start, end))
    options = get_filter_options(database)

    assert data["summary"]["usage"]["requests"] > 0
    assert data["summary"]["costs"][0]["currency"] == "usd"
    assert len(data["usage_series"]) == 2
    assert options["projects"] == ["proj_internal", "proj_product"]
