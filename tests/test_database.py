from app.database import Database


def test_initialize_creates_tables(tmp_path):
    database = Database(tmp_path / "dashboard.db")
    database.initialize()

    with database.connect() as connection:
        names = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }

    assert {
        "completion_usage",
        "costs",
        "projects",
        "project_api_keys",
        "sync_runs",
    } <= names
