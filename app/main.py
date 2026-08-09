from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import Settings, get_settings
from app.database import Database
from app.mock_client import MockUsageClient
from app.openai_client import OpenAIUsageClient
from app.routes import router
from app.sync import SyncService, default_sync_range

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    database = Database(app_settings.database_path)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        database.initialize()
        client = None
        scheduler = None
        initial_task = None
        if app_settings.mock_mode:
            client = MockUsageClient()
        elif app_settings.openai_admin_key:
            client = OpenAIUsageClient(app_settings.openai_admin_key)

        app.state.sync_service = SyncService(database, client) if client else None

        async def run_scheduled_sync() -> None:
            start, end = default_sync_range(
                database,
                app_settings.initial_history_days,
                app_settings.sync_lookback_days,
            )
            try:
                await app.state.sync_service.sync(start, end)
            except RuntimeError as exc:
                logger.info("Scheduled synchronization skipped: %s", exc)
            except Exception:
                logger.exception("Scheduled synchronization failed")

        if app.state.sync_service:
            scheduler = AsyncIOScheduler(timezone=app_settings.timezone)
            scheduler.add_job(
                run_scheduled_sync,
                "interval",
                minutes=app_settings.sync_interval_minutes,
                max_instances=1,
                coalesce=True,
            )
            scheduler.start()
            initial_task = asyncio.create_task(run_scheduled_sync())
            app.state.sync_task = initial_task
        try:
            yield
        finally:
            if scheduler:
                scheduler.shutdown(wait=False)
            if initial_task and not initial_task.done():
                initial_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await initial_task
            active_task = app.state.sync_task
            if active_task and active_task is not initial_task and not active_task.done():
                active_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await active_task
            if isinstance(client, OpenAIUsageClient):
                await client.aclose()

    app = FastAPI(title="OpenAI Usage Dashboard", lifespan=lifespan)
    app.state.settings = app_settings
    app.state.database = database
    app.state.sync_service = None
    app.state.sync_task = None
    app.mount("/static", StaticFiles(directory="app/static"), name="static")
    app.include_router(router)

    @app.get("/healthz")
    async def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
