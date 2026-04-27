from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlparse


class ClickHouseAnalyticsWriter:
    def __init__(self, *, client: Any, database: str = "prediction_core") -> None:
        self.client = client
        self.database = database

    def insert_rows(self, table: str, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        columns = list(rows[0].keys())
        data = [[row.get(column) for column in columns] for row in rows]
        self.client.insert(f"{self.database}.{table}", data, column_names=columns)


def create_clickhouse_writer_from_env() -> ClickHouseAnalyticsWriter | None:
    """Create a ClickHouse writer only when analytics is explicitly configured.

    The optional clickhouse-connect dependency is imported lazily so importing this
    module and using injected clients in tests does not require the package.
    """
    url = os.environ.get("PREDICTION_CORE_CLICKHOUSE_URL")
    host = os.environ.get("PREDICTION_CORE_CLICKHOUSE_HOST")
    if not url and not host:
        return None

    try:
        import clickhouse_connect
    except ImportError as exc:
        raise RuntimeError(
            "clickhouse-connect is required when ClickHouse analytics is configured"
        ) from exc

    database = os.environ.get("PREDICTION_CORE_CLICKHOUSE_DATABASE", "prediction_core")
    port = int(os.environ.get("PREDICTION_CORE_CLICKHOUSE_PORT", "8123"))
    username = os.environ.get("PREDICTION_CORE_CLICKHOUSE_USER", "prediction")
    password = os.environ.get("PREDICTION_CORE_CLICKHOUSE_PASSWORD", "prediction")

    if url:
        parsed = urlparse(url)
        host = parsed.hostname or "localhost"
        if parsed.port is not None:
            port = parsed.port
        if parsed.username:
            username = parsed.username
        if parsed.password:
            password = parsed.password
        if parsed.path and parsed.path != "/":
            database = parsed.path.lstrip("/")
    else:
        host = host or "localhost"

    client = clickhouse_connect.get_client(
        host=host,
        port=port,
        username=username,
        password=password,
        database=database,
    )
    return ClickHouseAnalyticsWriter(client=client, database=database)
