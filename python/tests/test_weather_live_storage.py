from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from weather_pm.live_storage import (
    ClickHouseObserverSink,
    PostgresObserverSink,
    assert_not_unmounted_truenas_path,
    build_clickhouse_rows,
    build_postgres_rows,
    create_live_observer_storage_sink,
    write_live_observer_payload_to_storage,
)

ROOT = Path(__file__).resolve().parents[2]


def _observer_payload() -> dict:
    return {
        "run_id": "observer-run-1",
        "generated_at": "2026-04-29T09:00:00+00:00",
        "summary": {"execution_snapshot_refreshed": 1, "execution_snapshot_errors": 0},
        "shortlist": [
            {
                "rank": 1,
                "market_id": "denver-high-65",
                "token_id": "yes-token-1",
                "strategy_id": "weather_bookmaker_v1",
                "strategy_profile_id": "surface_grid_trader",
                "decision_status": "trade_small",
                "question": "Will Denver high temperature be 65F or above?",
                "yes_price": 0.44,
                "best_bid": 0.42,
                "best_ask": 0.46,
                "volume": 123.4,
                "liquidity": 456.7,
                "paper_only": True,
                "live_order_allowed": False,
                "execution_snapshot": {
                    "best_bid_yes": 0.42,
                    "best_ask_yes": 0.46,
                    "yes_bid_depth_usd": 120.0,
                    "yes_ask_depth_usd": 80.0,
                    "bids": [{"price": 0.42, "size": 10}],
                    "asks": [{"price": 0.46, "size": 11}],
                    "fetched_at": "2026-04-29T09:00:01+00:00",
                },
            }
        ],
    }


class _Writer:
    def __init__(self) -> None:
        self.inserted: list[tuple[str, list[dict[str, object]]]] = []

    def insert_rows(self, table: str, rows: list[dict[str, object]]) -> None:
        self.inserted.append((table, rows))


class _Connection:
    def __init__(self) -> None:
        self.executed: list[tuple[object, dict[str, object]]] = []

    def execute(self, statement: object, row: dict[str, object]) -> None:
        self.executed.append((statement, row))


class _Begin:
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection

    def __enter__(self) -> _Connection:
        return self.connection

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class _Engine:
    def __init__(self) -> None:
        self.connection = _Connection()

    def begin(self) -> _Begin:
        return _Begin(self.connection)


def test_clickhouse_rows_map_live_observer_snapshots_and_safety_flags() -> None:
    rows = build_clickhouse_rows(_observer_payload())

    assert len(rows["market_snapshots"]) == 1
    assert len(rows["orderbook_snapshots"]) == 1
    market = rows["market_snapshots"][0]
    orderbook = rows["orderbook_snapshots"][0]
    assert market["market_id"] == "denver-high-65"
    assert market["mode"] == "paper"
    assert market["yes_price"] == 0.44
    assert orderbook["spread"] == pytest.approx(0.04)
    assert orderbook["bid_depth_levels"] == 1
    assert json.loads(str(market["raw"]))["paper_only"] is True
    assert json.loads(str(orderbook["raw"]))["live_order_allowed"] is False


def test_postgres_rows_map_live_observer_market_orderbook_and_health() -> None:
    rows = build_postgres_rows(_observer_payload())

    assert set(rows) == {"market_price_snapshots", "orderbook_snapshots", "ingestion_health"}
    assert rows["market_price_snapshots"][0]["price"] == 0.44
    assert rows["orderbook_snapshots"] == [
        {
            "snapshot_id": rows["orderbook_snapshots"][0]["snapshot_id"],
            "market_id": "denver-high-65",
            "token_id": "yes-token-1",
            "observed_at": "2026-04-29T09:00:01+00:00",
            "bids": [{"price": 0.42, "depth_usd": 120.0}],
            "asks": [{"price": 0.46, "depth_usd": 80.0}],
            "raw": {"row": _observer_payload()["shortlist"][0], "paper_only": True, "live_order_allowed": False},
            "schema_version": "1.0",
        }
    ]
    assert rows["ingestion_health"][0]["status"] == "ok"
    assert rows["ingestion_health"][0]["metrics"] == {
        "paper_only": True,
        "live_order_allowed": False,
        "rows": 1,
        "execution_snapshot_refreshed": 1,
        "execution_snapshot_errors": 0,
    }


def test_clickhouse_sink_dry_run_counts_rows_without_insert() -> None:
    writer = _Writer()
    summary = ClickHouseObserverSink(writer).write_live_observer_payload(_observer_payload(), dry_run=True)

    assert summary.storage_backend == "clickhouse"
    assert summary.rows_attempted == 7
    assert summary.rows_written == 0
    assert summary.dry_run is True
    assert summary.paper_only is True
    assert summary.live_order_allowed is False
    assert writer.inserted == []


def test_postgres_sink_writes_serialized_rows_through_engine() -> None:
    engine = _Engine()
    summary = PostgresObserverSink(engine).write_live_observer_payload(_observer_payload(), dry_run=False)

    assert summary.storage_backend == "postgres_timescale"
    assert summary.rows_attempted == 3
    assert summary.rows_written == 3
    assert summary.paper_only is True
    assert summary.live_order_allowed is False
    assert len(engine.connection.executed) == 3
    _, first_row = engine.connection.executed[0]
    assert isinstance(first_row["raw"], str)


def test_storage_sink_noops_when_config_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in [
        "PREDICTION_CORE_DATABASE_URL",
        "PANOPTIQUE_DATABASE_URL",
        "PREDICTION_CORE_SYNC_DATABASE_URL",
        "PANOPTIQUE_SYNC_DATABASE_URL",
        "PREDICTION_CORE_CLICKHOUSE_URL",
        "PREDICTION_CORE_CLICKHOUSE_HOST",
    ]:
        monkeypatch.delenv(key, raising=False)

    sink = create_live_observer_storage_sink(backend="auto")
    summary = sink.write_live_observer_payload(_observer_payload(), dry_run=False)

    assert summary.to_dict() == {
        "storage_backend": "noop",
        "rows_attempted": 1,
        "rows_written": 0,
        "dry_run": False,
        "paper_only": True,
        "live_order_allowed": False,
        "skipped_reason": "auto_storage_not_configured",
    }


def test_explicit_storage_dry_run_builds_rows_without_config() -> None:
    summary = write_live_observer_payload_to_storage(_observer_payload(), backend="clickhouse", dry_run=True)

    assert summary == {
        "storage_backend": "clickhouse",
        "rows_attempted": 7,
        "rows_written": 0,
        "dry_run": True,
        "paper_only": True,
        "live_order_allowed": False,
        "skipped_reason": None,
    }


def test_truenas_guard_rejects_unmounted_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os.path, "ismount", lambda path: False)

    with pytest.raises(ValueError, match="/mnt/truenas"):
        assert_not_unmounted_truenas_path("/mnt/truenas/weather/observer.json")


def test_cli_operator_refresh_storage_dry_run_summary(tmp_path: Path) -> None:
    shortlist_path = tmp_path / "shortlist.json"
    shortlist_path.write_text(
        json.dumps(
            {
                "run_id": "saved-run",
                "source": "fixture",
                "summary": {"shortlisted": 1, "action_counts": {}, "execution_blocker_counts": {}},
                "shortlist": [
                    {
                        "rank": 1,
                        "market_id": "denver-high-65",
                        "decision_status": "trade_small",
                        "execution_snapshot": {
                            "best_bid_yes": 0.42,
                            "best_ask_yes": 0.46,
                            "fetched_at": "2026-04-29T09:00:01+00:00",
                        },
                    }
                ],
            }
        )
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "weather_pm.cli",
            "operator-refresh",
            "--input-json",
            str(shortlist_path),
            "--source",
            "fixture",
            "--skip-resolution-status",
            "--skip-orderbook",
            "--storage-backend",
            "postgres",
            "--storage-dry-run",
        ],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": "python/src"},
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(result.stdout)
    assert payload["summary"]["storage_backend"] == "postgres_timescale"
    assert payload["summary"]["rows_attempted"] == 3
    assert payload["summary"]["rows_written"] == 0
    assert payload["summary"]["dry_run"] is True
    assert payload["summary"]["paper_only"] is True
    assert payload["summary"]["live_order_allowed"] is False
