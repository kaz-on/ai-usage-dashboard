from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


def _positive_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < 1:
        raise ValueError(f"{name} must be at least 1")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    openai_admin_key: str | None
    dashboard_subtitle: str | None
    database_path: Path
    sync_interval_minutes: int
    initial_history_days: int
    sync_lookback_days: int
    timezone: str
    mock_mode: bool

    @classmethod
    def from_env(cls) -> Settings:
        key = os.getenv("OPENAI_ADMIN_KEY") or None
        subtitle = os.getenv("DASHBOARD_SUBTITLE", "").strip() or None
        mock_mode = os.getenv("MOCK_MODE", "false").lower() in {"1", "true", "yes"}
        return cls(
            openai_admin_key=key,
            dashboard_subtitle=subtitle,
            database_path=Path(os.getenv("DATABASE_PATH", "./data/dashboard.db")),
            sync_interval_minutes=_positive_int("SYNC_INTERVAL_MINUTES", 60),
            initial_history_days=_positive_int("INITIAL_HISTORY_DAYS", 90),
            sync_lookback_days=_positive_int("SYNC_LOOKBACK_DAYS", 3),
            timezone=os.getenv("TZ", "Asia/Tokyo"),
            mock_mode=mock_mode,
        )

    @property
    def sync_enabled(self) -> bool:
        return self.mock_mode or bool(self.openai_admin_key)


@lru_cache
def get_settings() -> Settings:
    return Settings.from_env()
