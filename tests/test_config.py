from pathlib import Path

from app.config import Settings


def test_settings_defaults(monkeypatch):
    for name in (
        "OPENAI_ADMIN_KEY",
        "DASHBOARD_SUBTITLE",
        "DATABASE_PATH",
        "SYNC_INTERVAL_MINUTES",
        "INITIAL_HISTORY_DAYS",
        "SYNC_LOOKBACK_DAYS",
        "TZ",
        "MOCK_MODE",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = Settings.from_env()

    assert settings.database_path == Path("./data/dashboard.db")
    assert settings.dashboard_subtitle is None
    assert settings.sync_interval_minutes == 60
    assert settings.initial_history_days == 90
    assert settings.sync_enabled is False


def test_settings_reads_dashboard_subtitle(monkeypatch):
    monkeypatch.setenv("DASHBOARD_SUBTITLE", "Example Organization")

    settings = Settings.from_env()

    assert settings.dashboard_subtitle == "Example Organization"
