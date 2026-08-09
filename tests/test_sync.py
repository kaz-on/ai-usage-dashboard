from app.database import Database
from app.mock_client import MockUsageClient
from app.sync import SyncService


async def test_sync_replaces_same_range_without_duplicates(tmp_path):
    database = Database(tmp_path / "dashboard.db")
    database.initialize()
    service = SyncService(database, MockUsageClient())

    first = await service.sync(1_735_689_600, 1_735_862_400)
    second = await service.sync(1_735_689_600, 1_735_862_400)

    assert first == second == {"completions": 4, "costs": 4}
    with database.connect() as connection:
        assert connection.execute("SELECT count(*) FROM completion_usage").fetchone()[0] == 4
        assert connection.execute("SELECT count(*) FROM costs").fetchone()[0] == 4
        statuses = connection.execute("SELECT status FROM sync_runs").fetchall()
    assert {row["status"] for row in statuses} == {"success"}
