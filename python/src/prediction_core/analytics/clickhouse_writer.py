from __future__ import annotations

import fcntl
import json
import os
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse


class ClickHouseAnalyticsWriter:
    def __init__(
        self,
        *,
        client: Any,
        database: str = "prediction_core",
        retry_attempts: int = 1,
        spool_path: str | Path | None = None,
        backoff_seconds: float = 0.0,
        clock: Callable[[], Any] | None = None,
    ) -> None:
        self.client = client
        self.database = database
        self.retry_attempts = max(1, retry_attempts)
        self.spool_path = Path(spool_path) if spool_path is not None else None
        self.backoff_seconds = backoff_seconds
        self.clock = clock or time.time

    def insert_rows(self, table: str, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        columns = list(rows[0].keys())
        data = [[row.get(column) for column in columns] for row in rows]
        first_failure_at = None
        last_failure_at = None
        for attempt_count in range(1, self.retry_attempts + 1):
            try:
                self.client.insert(f"{self.database}.{table}", data, column_names=columns)
                return
            except Exception as exc:
                now = self.clock()
                first_failure_at = now if first_failure_at is None else first_failure_at
                last_failure_at = now
                if attempt_count < self.retry_attempts:
                    if self.backoff_seconds > 0:
                        time.sleep(self.backoff_seconds)
                    continue
                if self.spool_path is not None:
                    self._spool_rows(
                        table=table,
                        rows=rows,
                        attempt_count=attempt_count,
                        error=exc,
                        first_failure_at=first_failure_at,
                        last_failure_at=last_failure_at,
                    )
                    return
                raise

    def _spool_rows(
        self,
        *,
        table: str,
        rows: list[dict[str, Any]],
        attempt_count: int,
        error: Exception,
        first_failure_at: Any,
        last_failure_at: Any,
    ) -> None:
        if self.spool_path is None:
            return
        self.spool_path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "attempt_count": attempt_count,
            "error": str(error),
            "error_type": type(error).__name__,
            "first_failure_at": first_failure_at,
            "last_failure_at": last_failure_at,
            "live_order_allowed": False,
            "paper_only": True,
            "rows": rows,
            "table": table,
        }
        fd = os.open(self.spool_path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
        os.chmod(self.spool_path, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as file:
            fcntl.flock(file.fileno(), fcntl.LOCK_EX)
            file.write(json.dumps(record, sort_keys=True, default=str))
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())


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

    retry_attempts = int(os.environ.get("PREDICTION_CORE_CLICKHOUSE_RETRY_ATTEMPTS", "1"))
    spool_path = os.environ.get("PREDICTION_CORE_CLICKHOUSE_SPOOL_PATH")
    backoff_seconds = float(
        os.environ.get("PREDICTION_CORE_CLICKHOUSE_BACKOFF_SECONDS", "0.0")
    )

    client = clickhouse_connect.get_client(
        host=host,
        port=port,
        username=username,
        password=password,
        database=database,
    )
    return ClickHouseAnalyticsWriter(
        client=client,
        database=database,
        retry_attempts=retry_attempts,
        spool_path=spool_path,
        backoff_seconds=backoff_seconds,
    )
