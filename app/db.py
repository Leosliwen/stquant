from __future__ import annotations

from typing import Any

import clickhouse_connect

from .config import settings


def get_client():
    return clickhouse_connect.get_client(
        host=settings.clickhouse_host,
        port=settings.clickhouse_port,
        username=settings.clickhouse_user,
        password=settings.clickhouse_password,
        database=settings.clickhouse_database,
    )


def rows_as_dicts(result: Any) -> list[dict[str, Any]]:
    names = list(result.column_names)
    return [dict(zip(names, row)) for row in result.result_rows]


def ping() -> bool:
    client = get_client()
    return bool(client.command("SELECT 1"))
