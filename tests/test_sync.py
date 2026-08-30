import time
from datetime import UTC, datetime

from app.database import Database
from app.mock_client import MockUsageClient
from app.sync import SyncService, default_sync_range


def test_default_range_aligns_to_utc_day_boundaries(tmp_path, monkeypatch):
    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 8, 10, 12, 34, 56, tzinfo=tz)

    monkeypatch.setattr("app.sync.datetime", FixedDatetime)
    database = Database(tmp_path / "dashboard.db")
    database.initialize()

    start, end = default_sync_range(database, history_days=90, lookback_days=3)

    assert start == int(datetime(2026, 5, 12, tzinfo=UTC).timestamp())
    assert end == int(datetime(2026, 8, 11, tzinfo=UTC).timestamp())


async def test_sync_replaces_same_range_without_duplicates(tmp_path):
    database = Database(tmp_path / "dashboard.db")
    database.initialize()
    service = SyncService(database, MockUsageClient())

    first = await service.sync(1_735_689_600, 1_735_862_400)
    second = await service.sync(1_735_689_600, 1_735_862_400)

    assert first == second == {"metadata": 4, "completions": 4, "costs": 4}
    with database.connect() as connection:
        assert connection.execute("SELECT count(*) FROM completion_usage").fetchone()[0] == 4
        assert connection.execute("SELECT count(*) FROM costs").fetchone()[0] == 4
        assert connection.execute("SELECT count(*) FROM projects").fetchone()[0] == 2
        assert connection.execute("SELECT count(*) FROM project_api_keys").fetchone()[0] == 2
        statuses = connection.execute("SELECT status FROM sync_runs").fetchall()
    assert {row["status"] for row in statuses} == {"success"}


async def test_default_range_shortens_only_after_both_endpoints_succeed(tmp_path):
    database = Database(tmp_path / "dashboard.db")
    database.initialize()

    initial_start, _ = default_sync_range(database, history_days=90, lookback_days=3)
    assert 89 * 86_400 < time.time() - initial_start < 91 * 86_400

    await SyncService(database, MockUsageClient()).sync(1_735_689_600, 1_735_776_000)
    incremental_start, _ = default_sync_range(database, history_days=90, lookback_days=3)
    assert 2 * 86_400 < time.time() - incremental_start < 4 * 86_400
