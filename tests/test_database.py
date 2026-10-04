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


def test_initialize_migrates_cost_numbers_and_adds_quantity_unit(tmp_path):
    database = Database(tmp_path / "dashboard.db")
    database.initialize()
    with database.connect() as connection:
        connection.execute("DROP TABLE costs")
        connection.executescript(
            """
            CREATE TABLE costs (
                id INTEGER PRIMARY KEY,
                bucket_start INTEGER NOT NULL,
                bucket_end INTEGER NOT NULL,
                project_id TEXT NOT NULL DEFAULT '',
                api_key_id TEXT NOT NULL DEFAULT '',
                line_item TEXT NOT NULL DEFAULT '',
                currency TEXT NOT NULL DEFAULT '',
                amount TEXT NOT NULL DEFAULT '0',
                quantity TEXT,
                raw_json TEXT NOT NULL,
                synced_at INTEGER NOT NULL,
                UNIQUE (
                    bucket_start, bucket_end, project_id, api_key_id, line_item, currency
                )
            );
            CREATE INDEX idx_costs_bucket ON costs(bucket_start, bucket_end);
            INSERT INTO costs VALUES (
                7, 100, 200, 'project', 'key', 'input', 'usd', '0.0002585',
                '42', '{"quantity_unit":"tokens"}', 300
            );
            """
        )

    database.initialize()

    with database.connect() as connection:
        columns = {
            row[1]: row[2] for row in connection.execute("PRAGMA table_info(costs)")
        }
        cost = connection.execute(
            """SELECT id, amount, typeof(amount), quantity, typeof(quantity), quantity_unit
            FROM costs"""
        ).fetchone()
        indexes = {
            row[1] for row in connection.execute("PRAGMA index_list(costs)").fetchall()
        }

    assert columns["amount"] == "REAL"
    assert columns["quantity"] == "REAL"
    assert columns["quantity_unit"] == "TEXT"
    assert tuple(cost) == (7, 0.0002585, "real", 42.0, "real", "tokens")
    assert "idx_costs_bucket" in indexes
