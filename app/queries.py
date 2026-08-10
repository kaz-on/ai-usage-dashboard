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
    granularity, bucket_expression = _series_bucket(filters)
    usage_where, usage_params = _where(filters, include_model=True)
    cost_where, cost_params = _where(filters, include_model=False)
    usage_join_where, usage_join_params = _where(filters, include_model=True, alias="u")
    cost_join_where, cost_join_params = _where(filters, include_model=False, alias="c")
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
                f"""SELECT {bucket_expression} AS bucket_start,
                    SUM(num_model_requests) AS requests,
                    SUM(input_tokens) AS input_tokens,
                    SUM(output_tokens) AS output_tokens,
                    SUM(input_cached_tokens) AS cached_tokens,
                    SUM(input_uncached_tokens) AS uncached_tokens
                FROM completion_usage WHERE {usage_where}
                GROUP BY 1 ORDER BY 1""",  # noqa: S608
                usage_params,
            ).fetchall()
        )
        project_request_series = _rows(
            connection.execute(
                f"""SELECT {bucket_expression.replace("bucket_start", "u.bucket_start")}
                        AS bucket_start,
                    u.project_id,
                    COALESCE(NULLIF(p.name, ''), NULLIF(u.project_id, ''), '未分類')
                        AS project_name,
                    SUM(u.num_model_requests) AS requests
                FROM completion_usage u LEFT JOIN projects p ON p.id = u.project_id
                WHERE {usage_join_where}
                GROUP BY 1, u.project_id, p.name
                ORDER BY 1, u.project_id""",  # noqa: S608
                usage_join_params,
            ).fetchall()
        )
        cost_series = _rows(
            connection.execute(
                f"""SELECT {bucket_expression} AS bucket_start, currency,
                    printf('%.8f', SUM(CAST(amount AS REAL))) AS amount
                FROM costs WHERE {cost_where}
                GROUP BY 1, currency ORDER BY 1, currency""",  # noqa: S608
                cost_params,
            ).fetchall()
        )
        project_cost_series = _rows(
            connection.execute(
                f"""SELECT {bucket_expression.replace("bucket_start", "c.bucket_start")}
                        AS bucket_start,
                    c.project_id,
                    COALESCE(NULLIF(p.name, ''), NULLIF(c.project_id, ''), '未分類')
                        AS project_name,
                    c.currency,
                    printf('%.8f', SUM(CAST(c.amount AS REAL))) AS amount
                FROM costs c LEFT JOIN projects p ON p.id = c.project_id
                WHERE {cost_join_where}
                GROUP BY 1, c.project_id, p.name, c.currency
                ORDER BY 1, c.currency, c.project_id""",  # noqa: S608
                cost_join_params,
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
                f"""SELECT
                    COALESCE(NULLIF(p.name, ''), NULLIF(c.project_id, ''), '未分類') AS label,
                    c.project_id, c.currency,
                    printf('%.8f', SUM(CAST(c.amount AS REAL))) AS amount
                FROM costs c LEFT JOIN projects p ON p.id = c.project_id
                WHERE {cost_join_where}
                GROUP BY c.project_id, p.name, c.currency
                ORDER BY CAST(amount AS REAL) DESC""",  # noqa: S608
                cost_join_params,
            ).fetchall()
        )
        recent_usage = _rows(
            connection.execute(
                f"""SELECT u.bucket_start, u.project_id,
                    COALESCE(NULLIF(p.name, ''), NULLIF(u.project_id, ''), '未分類') project_name,
                    u.model, u.api_key_id,
                    COALESCE(NULLIF(k.name, ''), NULLIF(u.api_key_id, ''), '未分類') api_key_name,
                    u.batch, u.service_tier, u.num_model_requests,
                    u.input_tokens, u.output_tokens, u.input_cached_tokens
                FROM completion_usage u
                LEFT JOIN projects p ON p.id = u.project_id
                LEFT JOIN project_api_keys k ON k.id = u.api_key_id
                WHERE {usage_join_where}
                ORDER BY u.bucket_start DESC, u.num_model_requests DESC LIMIT 100""",  # noqa: S608
                usage_join_params,
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
        "project_request_series": project_request_series,
        "cost_series": cost_series,
        "project_cost_series": project_cost_series,
        "series_granularity": granularity,
        "model_breakdown": models,
        "project_costs": projects,
        "recent_usage": recent_usage,
        "sync_status": sync_status,
        "model_cost_unavailable": bool(filters.model),
    }


def get_filter_options(database: Database) -> dict[str, list[Any]]:
    with database.connect() as connection:
        projects = connection.execute(
            """WITH ids(id) AS (
                SELECT project_id FROM completion_usage WHERE project_id != ''
                UNION SELECT project_id FROM costs WHERE project_id != ''
            )
            SELECT ids.id AS value, COALESCE(NULLIF(p.name, ''), ids.id) AS label
            FROM ids LEFT JOIN projects p ON p.id = ids.id
            ORDER BY label, value"""
        ).fetchall()
        api_keys = connection.execute(
            """WITH ids(id) AS (
                SELECT api_key_id FROM completion_usage WHERE api_key_id != ''
                UNION SELECT api_key_id FROM costs WHERE api_key_id != ''
            )
            SELECT ids.id AS value,
                CASE
                    WHEN k.name IS NULL OR k.name = '' THEN ids.id
                    WHEN p.name IS NOT NULL AND p.name != '' THEN k.name || ' — ' || p.name
                    ELSE k.name
                END AS label
            FROM ids
            LEFT JOIN project_api_keys k ON k.id = ids.id
            LEFT JOIN projects p ON p.id = k.project_id
            ORDER BY label, value"""
        ).fetchall()
        models = connection.execute(
            "SELECT DISTINCT model FROM completion_usage WHERE model != '' ORDER BY model"
        ).fetchall()
    return {
        "projects": _rows(projects),
        "api_keys": _rows(api_keys),
        "models": [row[0] for row in models],
    }


def csv_rows(
    database: Database, kind: str, filters: DashboardFilters
) -> tuple[list[str], list[dict]]:
    if kind == "completions":
        where, params = _where(filters, include_model=True, alias="u")
        columns = [
            "bucket_start",
            "bucket_end",
            "project_id",
            "project_name",
            "user_id",
            "api_key_id",
            "api_key_name",
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
        select = """u.bucket_start, u.bucket_end, u.project_id,
            COALESCE(NULLIF(p.name, ''), u.project_id) AS project_name,
            u.user_id, u.api_key_id,
            COALESCE(NULLIF(k.name, ''), u.api_key_id) AS api_key_name,
            u.model, u.batch, u.service_tier, u.num_model_requests,
            u.input_tokens, u.output_tokens, u.input_cached_tokens,
            u.input_uncached_tokens, u.input_cache_write_tokens"""
        source = """completion_usage u
            LEFT JOIN projects p ON p.id = u.project_id
            LEFT JOIN project_api_keys k ON k.id = u.api_key_id"""
        order_column = "u.bucket_start"
    elif kind == "costs":
        where, params = _where(filters, include_model=False, alias="c")
        columns = [
            "bucket_start",
            "bucket_end",
            "project_id",
            "project_name",
            "api_key_id",
            "api_key_name",
            "line_item",
            "currency",
            "amount",
            "quantity",
        ]
        select = """c.bucket_start, c.bucket_end, c.project_id,
            COALESCE(NULLIF(p.name, ''), c.project_id) AS project_name,
            c.api_key_id, COALESCE(NULLIF(k.name, ''), c.api_key_id) AS api_key_name,
            c.line_item, c.currency, c.amount, c.quantity"""
        source = """costs c
            LEFT JOIN projects p ON p.id = c.project_id
            LEFT JOIN project_api_keys k ON k.id = c.api_key_id"""
        order_column = "c.bucket_start"
    else:
        raise ValueError(f"Unknown CSV kind: {kind}")
    with database.connect() as connection:
        rows = connection.execute(
            f"SELECT {select} FROM {source} "  # noqa: S608
            f"WHERE {where} ORDER BY {order_column} DESC",
            params,
        ).fetchall()
    return columns, _rows(rows)


def _where(
    filters: DashboardFilters, *, include_model: bool, alias: str = ""
) -> tuple[str, list[Any]]:
    prefix = f"{alias}." if alias else ""
    clauses = [f"{prefix}bucket_start >= ?", f"{prefix}bucket_start < ?"]
    params: list[Any] = [filters.start_time, filters.end_time]
    for column, value in (("project_id", filters.project_id), ("api_key_id", filters.api_key_id)):
        if value:
            clauses.append(f"{prefix}{column} = ?")
            params.append(value)
    if include_model and filters.model:
        clauses.append(f"{prefix}model = ?")
        params.append(filters.model)
    return " AND ".join(clauses), params


def _series_bucket(filters: DashboardFilters) -> tuple[str, str]:
    days = max(1, (filters.end_time - filters.start_time) // 86_400)
    if days <= 45:
        return "day", "(bucket_start / 86400) * 86400"
    if days <= 180:
        # Unix epoch started on a Thursday; offset four days to make Monday the boundary.
        return "week", "((bucket_start - 345600) / 604800) * 604800 + 345600"
    return (
        "month",
        "CAST(strftime('%s', strftime('%Y-%m-01', bucket_start, 'unixepoch')) AS INTEGER)",
    )


def _rows(rows) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]
