import json
import os
import stat
import sys
import types

import pytest

from prediction_core.analytics.clickhouse_writer import (
    ClickHouseAnalyticsWriter,
    create_clickhouse_writer_from_env,
)


class FakeClient:
    def __init__(self):
        self.calls = []

    def insert(self, table, data, column_names=None):
        self.calls.append((table, data, column_names))


class FlakyClient:
    def __init__(self, failures):
        self.calls = []
        self.failures = failures

    def insert(self, table, data, column_names=None):
        self.calls.append((table, data, column_names))
        if len(self.calls) <= self.failures:
            raise RuntimeError("clickhouse unavailable")


def test_writer_inserts_rows_with_column_names() -> None:
    client = FakeClient()
    writer = ClickHouseAnalyticsWriter(client=client, database="prediction_core")

    writer.insert_rows("profile_decisions", [{"run_id": "r1", "market_id": "m1"}])

    assert client.calls == [
        (
            "prediction_core.profile_decisions",
            [["r1", "m1"]],
            ["run_id", "market_id"],
        )
    ]


def test_writer_retries_transient_failure_then_succeeds() -> None:
    client = FlakyClient(failures=1)
    writer = ClickHouseAnalyticsWriter(
        client=client,
        database="prediction_core",
        retry_attempts=2,
        backoff_seconds=0,
    )

    writer.insert_rows("profile_decisions", [{"run_id": "r1", "market_id": "m1"}])

    assert client.calls == [
        (
            "prediction_core.profile_decisions",
            [["r1", "m1"]],
            ["run_id", "market_id"],
        ),
        (
            "prediction_core.profile_decisions",
            [["r1", "m1"]],
            ["run_id", "market_id"],
        ),
    ]


def test_writer_spools_permanent_failure(tmp_path) -> None:
    client = FlakyClient(failures=2)
    spool_path = tmp_path / "clickhouse.jsonl"
    times = iter(["2026-04-28T00:00:00Z", "2026-04-28T00:00:01Z"])
    writer = ClickHouseAnalyticsWriter(
        client=client,
        database="prediction_core",
        retry_attempts=2,
        spool_path=spool_path,
        backoff_seconds=0,
        clock=lambda: next(times),
    )

    writer.insert_rows("profile_decisions", [{"run_id": "r1", "market_id": "m1"}])

    lines = spool_path.read_text().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == {
        "attempt_count": 2,
        "error": "clickhouse unavailable",
        "error_type": "RuntimeError",
        "first_failure_at": "2026-04-28T00:00:00Z",
        "last_failure_at": "2026-04-28T00:00:01Z",
        "live_order_allowed": False,
        "paper_only": True,
        "rows": [{"run_id": "r1", "market_id": "m1"}],
        "table": "profile_decisions",
    }
    assert stat.S_IMODE(os.stat(spool_path).st_mode) == 0o600


def test_writer_raises_permanent_failure_without_spool_path() -> None:
    client = FlakyClient(failures=1)
    writer = ClickHouseAnalyticsWriter(
        client=client,
        database="prediction_core",
        retry_attempts=1,
        backoff_seconds=0,
    )

    with pytest.raises(RuntimeError, match="clickhouse unavailable"):
        writer.insert_rows("profile_decisions", [{"run_id": "r1", "market_id": "m1"}])


def test_writer_noops_empty_rows(tmp_path) -> None:
    client = FakeClient()
    spool_path = tmp_path / "clickhouse.jsonl"
    writer = ClickHouseAnalyticsWriter(
        client=client,
        database="prediction_core",
        spool_path=spool_path,
    )

    writer.insert_rows("profile_decisions", [])

    assert client.calls == []
    assert not spool_path.exists()


def test_env_factory_returns_none_unless_configured(monkeypatch) -> None:
    monkeypatch.delenv("PREDICTION_CORE_CLICKHOUSE_URL", raising=False)
    monkeypatch.delenv("PREDICTION_CORE_CLICKHOUSE_HOST", raising=False)
    monkeypatch.setitem(sys.modules, "clickhouse_connect", None)

    assert create_clickhouse_writer_from_env() is None


def test_env_factory_uses_lazy_clickhouse_connect_import(monkeypatch) -> None:
    created = {}

    def fake_get_client(**kwargs):
        created.update(kwargs)
        return FakeClient()

    fake_module = types.SimpleNamespace(get_client=fake_get_client)
    monkeypatch.setitem(sys.modules, "clickhouse_connect", fake_module)
    monkeypatch.setenv(
        "PREDICTION_CORE_CLICKHOUSE_URL",
        "http://user:pass@clickhouse.local:8124/analytics_db",
    )
    monkeypatch.setenv("PREDICTION_CORE_CLICKHOUSE_RETRY_ATTEMPTS", "3")
    monkeypatch.setenv("PREDICTION_CORE_CLICKHOUSE_SPOOL_PATH", "/tmp/clickhouse.jsonl")
    monkeypatch.setenv("PREDICTION_CORE_CLICKHOUSE_BACKOFF_SECONDS", "0.5")

    writer = create_clickhouse_writer_from_env()

    assert isinstance(writer, ClickHouseAnalyticsWriter)
    assert writer.database == "analytics_db"
    assert writer.retry_attempts == 3
    assert str(writer.spool_path) == "/tmp/clickhouse.jsonl"
    assert writer.backoff_seconds == 0.5
    assert created == {
        "host": "clickhouse.local",
        "port": 8124,
        "username": "user",
        "password": "pass",
        "database": "analytics_db",
    }
