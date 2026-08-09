from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.database import Database


@dataclass(frozen=True, slots=True)
class DashboardFilters:
    start_time: int
    end_time: int
    project_id: str = ""
    model: str = ""
    api_key_id: str = ""


def get_dashboard_data(database: Database, filters: DashboardFilters) -> dict[str, Any]:
    usage_where, usage_params = _where(filters, include_model=True)
    cost_where, cost_params = _where(filters, include_model=False)
    with database.connect() as connection:
        usage = dict(
            connection.execute(
                f"""SELECT
                    COALESCE(SUM(num_model_requests), 0) AS requests,
                    COALESCE(SUM(input_tokens), 0) AS input_tokens,
                    COALESCE(SUM(output_tokens), 0) AS output_tokens,
                    COALESCE(SUM(input_cached_tokens), 0) AS cached_tokens,
                    COALESCE(SUM(input_uncached_tokens), 0) AS uncached_tokens
                FROM completion_usage WHERE {usage_where}""",  # noqa: S608
                usage_params,
            ).fetchone()
        )
        costs = _rows(
            connection.execute(
                f"""SELECT currency, printf('%.8f', SUM(CAST(amount AS REAL))) AS amount
                FROM costs WHERE {cost_where}
                GROUP BY currency ORDER BY currency""",  # noqa: S608
                cost_params,
            ).fetchall()
        )
        usage_series = _rows(
            connection.execute(
                f"""SELECT bucket_start,
                    SUM(num_model_requests) AS requests,
                    SUM(input_tokens) AS input_tokens,
                    SUM(output_tokens) AS output_tokens,
                    SUM(input_cached_tokens) AS cached_tokens
                FROM completion_usage WHERE {usage_where}
                GROUP BY bucket_start ORDER BY bucket_start""",  # noqa: S608
                usage_params,
            ).fetchall()
        )
        cost_series = _rows(
            connection.execute(
                f"""SELECT bucket_start, currency,
                    printf('%.8f', SUM(CAST(amount AS REAL))) AS amount
                FROM costs WHERE {cost_where}
                GROUP BY bucket_start, currency ORDER BY bucket_start, currency""",  # noqa: S608
                cost_params,
            ).fetchall()
        )
        models = _rows(
            connection.execute(
                f"""SELECT COALESCE(NULLIF(model, ''), '未分類') AS label,
                    SUM(num_model_requests) AS requests,
                    SUM(input_tokens + output_tokens) AS tokens
                FROM completion_usage WHERE {usage_where}
                GROUP BY model ORDER BY tokens DESC LIMIT 12""",  # noqa: S608
                usage_params,
            ).fetchall()
        )
        projects = _rows(
            connection.execute(
                f"""SELECT COALESCE(NULLIF(project_id, ''), '未分類') AS label,
                    currency, printf('%.8f', SUM(CAST(amount AS REAL))) AS amount
                FROM costs WHERE {cost_where}
                GROUP BY project_id, currency ORDER BY CAST(amount AS REAL) DESC LIMIT 12""",  # noqa: S608
                cost_params,
            ).fetchall()
        )
        recent_usage = _rows(
            connection.execute(
                f"""SELECT bucket_start, project_id, model, api_key_id, batch, service_tier,
                    num_model_requests, input_tokens, output_tokens, input_cached_tokens
                FROM completion_usage WHERE {usage_where}
                ORDER BY bucket_start DESC, num_model_requests DESC LIMIT 100""",  # noqa: S608
                usage_params,
            ).fetchall()
        )
        sync_status = _rows(
            connection.execute(
                """SELECT endpoint, status, started_at, finished_at, record_count, error_message
                FROM sync_runs WHERE id IN (
                    SELECT MAX(id) FROM sync_runs GROUP BY endpoint
                ) ORDER BY endpoint"""
            ).fetchall()
        )

    requests = usage["requests"]
    usage["cache_rate"] = (
        usage["cached_tokens"] / usage["input_tokens"] if usage["input_tokens"] else 0
    )
    usage["tokens_per_request"] = (
        (usage["input_tokens"] + usage["output_tokens"]) / requests if requests else 0
    )
    return {
        "summary": {"usage": usage, "costs": costs},
        "usage_series": usage_series,
        "cost_series": cost_series,
        "model_breakdown": models,
        "project_costs": projects,
        "recent_usage": recent_usage,
        "sync_status": sync_status,
        "model_cost_unavailable": bool(filters.model),
    }


def get_filter_options(database: Database) -> dict[str, list[str]]:
    with database.connect() as connection:
        projects = connection.execute(
            """SELECT project_id FROM completion_usage WHERE project_id != ''
            UNION SELECT project_id FROM costs WHERE project_id != '' ORDER BY project_id"""
        ).fetchall()
        api_keys = connection.execute(
            """SELECT api_key_id FROM completion_usage WHERE api_key_id != ''
            UNION SELECT api_key_id FROM costs WHERE api_key_id != '' ORDER BY api_key_id"""
        ).fetchall()
        models = connection.execute(
            "SELECT DISTINCT model FROM completion_usage WHERE model != '' ORDER BY model"
        ).fetchall()
    return {
        "projects": [row[0] for row in projects],
        "api_keys": [row[0] for row in api_keys],
        "models": [row[0] for row in models],
    }


def csv_rows(
    database: Database, kind: str, filters: DashboardFilters
) -> tuple[list[str], list[dict]]:
    if kind == "completions":
        where, params = _where(filters, include_model=True)
        columns = [
            "bucket_start",
            "bucket_end",
            "project_id",
            "user_id",
            "api_key_id",
            "model",
            "batch",
            "service_tier",
            "num_model_requests",
            "input_tokens",
            "output_tokens",
            "input_cached_tokens",
            "input_uncached_tokens",
            "input_cache_write_tokens",
        ]
        table = "completion_usage"
    elif kind == "costs":
        where, params = _where(filters, include_model=False)
        columns = [
            "bucket_start",
            "bucket_end",
            "project_id",
            "api_key_id",
            "line_item",
            "currency",
            "amount",
            "quantity",
        ]
        table = "costs"
    else:
        raise ValueError(f"Unknown CSV kind: {kind}")
    with database.connect() as connection:
        rows = connection.execute(
            f"SELECT {', '.join(columns)} FROM {table} "  # noqa: S608
            f"WHERE {where} ORDER BY bucket_start DESC",
            params,
        ).fetchall()
    return columns, _rows(rows)


def _where(filters: DashboardFilters, *, include_model: bool) -> tuple[str, list[Any]]:
    clauses = ["bucket_start >= ?", "bucket_start < ?"]
    params: list[Any] = [filters.start_time, filters.end_time]
    for column, value in (("project_id", filters.project_id), ("api_key_id", filters.api_key_id)):
        if value:
            clauses.append(f"{column} = ?")
            params.append(value)
    if include_model and filters.model:
        clauses.append("model = ?")
        params.append(filters.model)
    return " AND ".join(clauses), params


def _rows(rows) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]
