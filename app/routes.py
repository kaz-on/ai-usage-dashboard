from __future__ import annotations

import asyncio
import csv
import io
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates

from app.queries import DashboardFilters, csv_rows, get_dashboard_data, get_filter_options
from app.sync import default_sync_range

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    today = datetime.now(UTC).date()
    previous_month_end = today.replace(day=1) - timedelta(days=1)
    default_from = previous_month_end.replace(day=min(today.day, previous_month_end.day))
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "default_from": default_from.isoformat(),
            "default_to": today.isoformat(),
            "sync_enabled": request.app.state.sync_service is not None,
            "mock_mode": request.app.state.settings.mock_mode,
            "dashboard_subtitle": request.app.state.settings.dashboard_subtitle,
        },
    )


@router.get("/api/dashboard")
async def dashboard_api(
    request: Request,
    date_from: str = Query(alias="from"),
    date_to: str = Query(alias="to"),
    project_id: str = "",
    model: str = "",
    api_key_id: str = "",
):
    filters = _filters(date_from, date_to, project_id, model, api_key_id)
    data = get_dashboard_data(request.app.state.database, filters)
    data["filters"] = get_filter_options(request.app.state.database)
    data["sync_running"] = bool(
        request.app.state.sync_service and request.app.state.sync_service.is_running
    )
    return data


@router.get("/api/export/{kind}.csv")
async def export_csv(
    kind: str,
    request: Request,
    date_from: str = Query(alias="from"),
    date_to: str = Query(alias="to"),
    project_id: str = "",
    model: str = "",
    api_key_id: str = "",
):
    if kind not in {"completions", "costs"}:
        raise HTTPException(status_code=404, detail="Unknown export type")
    filters = _filters(date_from, date_to, project_id, model, api_key_id)
    columns, rows = csv_rows(request.app.state.database, kind, filters)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=columns)
    writer.writeheader()
    writer.writerows(rows)
    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{kind}.csv"'},
    )


@router.post("/api/sync", status_code=status.HTTP_202_ACCEPTED)
async def start_sync(request: Request):
    service = request.app.state.sync_service
    if service is None:
        raise HTTPException(
            status_code=409,
            detail="OPENAI_ADMIN_KEYが設定されていません。",
        )
    if service.is_running:
        return JSONResponse({"status": "already_running"}, status_code=202)
    settings = request.app.state.settings
    start_time, end_time = default_sync_range(
        request.app.state.database,
        settings.initial_history_days,
        settings.sync_lookback_days,
    )
    request.app.state.sync_task = asyncio.create_task(service.sync(start_time, end_time))
    request.app.state.sync_task.add_done_callback(_consume_task_error)
    return {"status": "started"}


def _filters(
    date_from: str, date_to: str, project_id: str, model: str, api_key_id: str
) -> DashboardFilters:
    try:
        start_date = date.fromisoformat(date_from)
        end_date = date.fromisoformat(date_to)
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail="日付はYYYY-MM-DD形式で指定してください。"
        ) from exc
    if start_date > end_date:
        raise HTTPException(status_code=422, detail="開始日は終了日以前にしてください。")
    if (end_date - start_date).days > 366:
        raise HTTPException(status_code=422, detail="表示期間は最大367日です。")
    start_time = int(datetime.combine(start_date, datetime.min.time(), UTC).timestamp())
    exclusive_end = int(
        datetime.combine(end_date + timedelta(days=1), datetime.min.time(), UTC).timestamp()
    )
    return DashboardFilters(start_time, exclusive_end, project_id, model, api_key_id)


def _consume_task_error(task: asyncio.Task) -> None:
    if not task.cancelled():
        task.exception()
