import sys
import types

from prediction_core.analytics.clickhouse_writer import (
    ClickHouseAnalyticsWriter,
    create_clickhouse_writer_from_env,
)


class FakeClient:
    def __init__(self):
        self.calls = []

    def insert(self, table, data, column_names=None):
        self.calls.append((table, data, column_names))


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


def test_writer_noops_empty_rows() -> None:
    client = FakeClient()
    writer = ClickHouseAnalyticsWriter(client=client, database="prediction_core")

    writer.insert_rows("profile_decisions", [])

    assert client.calls == []


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
    monkeypatch.setenv("PREDICTION_CORE_CLICKHOUSE_URL", "http://user:pass@clickhouse.local:8124/analytics_db")

    writer = create_clickhouse_writer_from_env()

    assert isinstance(writer, ClickHouseAnalyticsWriter)
    assert writer.database == "analytics_db"
    assert created == {
        "host": "clickhouse.local",
        "port": 8124,
        "username": "user",
        "password": "pass",
        "database": "analytics_db",
    }
