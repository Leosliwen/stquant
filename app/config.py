from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    clickhouse_host: str = os.getenv("STQUANT_CLICKHOUSE_HOST", "127.0.0.1")
    clickhouse_port: int = int(os.getenv("STQUANT_CLICKHOUSE_PORT", "8123"))
    clickhouse_user: str = os.getenv("STQUANT_CLICKHOUSE_USER", "default")
    clickhouse_password: str = os.getenv("STQUANT_CLICKHOUSE_PASSWORD", "")
    clickhouse_database: str = os.getenv("STQUANT_CLICKHOUSE_DATABASE", "xtquant")
    qmt_agent_url: str = os.getenv("STQUANT_QMT_AGENT_URL", "http://127.0.0.1:8710")


settings = Settings()
