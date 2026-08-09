from app.database import Database
from app.mock_client import MockUsageClient
from app.queries import DashboardFilters, csv_rows, get_dashboard_data, get_filter_options
from app.sync import SyncService


async def test_dashboard_aggregates_mock_data(tmp_path):
    database = Database(tmp_path / "dashboard.db")
    database.initialize()
    start, end = 1_735_689_600, 1_735_862_400
    await SyncService(database, MockUsageClient()).sync(start, end)

    data = get_dashboard_data(database, DashboardFilters(start, end))
    options = get_filter_options(database)
    columns, exported = csv_rows(database, "completions", DashboardFilters(start, end))

    assert data["summary"]["usage"]["requests"] > 0
    assert data["summary"]["costs"][0]["currency"] == "usd"
    assert len(data["usage_series"]) == 2
    assert {row["label"] for row in data["project_costs"]} == {
        "Customer Product",
        "Internal Tools",
    }
    assert {row["project_name"] for row in data["recent_usage"]} == {
        "Customer Product",
        "Internal Tools",
    }
    assert options["projects"] == [
        {"value": "proj_product", "label": "Customer Product"},
        {"value": "proj_internal", "label": "Internal Tools"},
    ]
    assert {option["label"] for option in options["api_keys"]} == {
        "Production — Customer Product",
        "Department Batch — Internal Tools",
    }
    assert "project_name" in columns
    assert "api_key_name" in columns
    assert {row["project_name"] for row in exported} == {
        "Customer Product",
        "Internal Tools",
    }
