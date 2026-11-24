import time
from datetime import UTC, datetime

import pytest

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
        quantity = connection.execute(
            "SELECT quantity, typeof(quantity), quantity_unit FROM costs LIMIT 1"
        ).fetchone()
        assert connection.execute("SELECT count(*) FROM projects").fetchone()[0] == 2
        assert connection.execute("SELECT count(*) FROM project_api_keys").fetchone()[0] == 2
        statuses = connection.execute("SELECT status FROM sync_runs").fetchall()
    assert {row["status"] for row in statuses} == {"success"}
    assert tuple(quantity) == (1000.0, "real", "tokens")


@pytest.mark.parametrize("archive_fields", [{"status": "archived"}, {"archived_at": 1_735_776_000}])
async def test_sync_keeps_archived_project_keys_and_imports_usage(tmp_path, archive_fields):
    database = Database(tmp_path / "dashboard.db")
    database.initialize()
    second_day = 1_735_776_000
    await SyncService(database, MockUsageClient()).sync(1_735_689_600, second_day)

    class ArchivedProjectClient(MockUsageClient):
        async def get_projects(self):
            projects = await super().get_projects()
            projects[0].update(archive_fields)
            return projects

        async def get_project_api_keys(self, project_id):
            assert project_id == "proj_internal"
            return []

    result = await SyncService(database, ArchivedProjectClient()).sync(second_day, 1_735_862_400)

    assert result == {"metadata": 2, "completions": 2, "costs": 2}
    with database.connect() as connection:
        project = connection.execute(
            "SELECT name, status, archived_at FROM projects WHERE id = 'proj_product'"
        ).fetchone()
        keys = connection.execute("SELECT id, name FROM project_api_keys").fetchall()
        completions = connection.execute(
            "SELECT api_key_id FROM completion_usage "
            "WHERE project_id = 'proj_product' AND bucket_start = ?",
            (second_day,),
        ).fetchone()
        costs = connection.execute(
            "SELECT api_key_id FROM costs "
            "WHERE project_id = 'proj_product' AND bucket_start = ?",
            (second_day,),
        ).fetchone()
    assert tuple(project) == (
        "Customer Product",
        archive_fields.get("status", "active"),
        archive_fields.get("archived_at"),
    )
    assert [tuple(key) for key in keys] == [("key_1", "Production")]
    assert completions["api_key_id"] == costs["api_key_id"] == "key_1"


async def test_default_range_shortens_only_after_both_endpoints_succeed(tmp_path):
    database = Database(tmp_path / "dashboard.db")
    database.initialize()

    initial_start, _ = default_sync_range(database, history_days=90, lookback_days=3)
    assert 89 * 86_400 < time.time() - initial_start < 91 * 86_400

    await SyncService(database, MockUsageClient()).sync(1_735_689_600, 1_735_776_000)
    incremental_start, _ = default_sync_range(database, history_days=90, lookback_days=3)
    assert 2 * 86_400 < time.time() - incremental_start < 4 * 86_400
