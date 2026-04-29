from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
import os
from pathlib import Path
from typing import Any, Protocol
from uuid import NAMESPACE_URL, uuid5

from prediction_core.analytics.clickhouse_writer import create_clickhouse_writer_from_env
from prediction_core.analytics.events import serialize_event
from prediction_core.analytics.metrics import build_profile_metric_events, build_strategy_metric_events
from prediction_core.storage.config import load_storage_stack_config
from prediction_core.storage.postgres import create_prediction_core_sync_engine_from_env
from weather_pm.analytics_adapter import debug_decision_events_from_shortlist, profile_decision_events_from_shortlist, strategy_signal_events_from_shortlist


@dataclass(frozen=True)
class StorageWriteSummary:
    storage_backend: str
    rows_attempted: int
    rows_written: int
    dry_run: bool
    paper_only: bool = True
    live_order_allowed: bool = False
    skipped_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class StorageSink(Protocol):
    backend: str

    def write_live_observer_payload(self, payload: dict[str, Any], *, dry_run: bool) -> StorageWriteSummary:
        ...


class NoopStorageSink:
    backend = "noop"

    def __init__(self, *, skipped_reason: str = "storage_not_configured") -> None:
        self.skipped_reason = skipped_reason

    def write_live_observer_payload(self, payload: dict[str, Any], *, dry_run: bool) -> StorageWriteSummary:
        rows_attempted = len([row for row in payload.get("shortlist", []) if isinstance(row, dict)])
        return StorageWriteSummary(
            storage_backend=self.backend,
            rows_attempted=rows_attempted,
            rows_written=0,
            dry_run=dry_run,
            skipped_reason=self.skipped_reason,
        )


class CompositeStorageSink:
    def __init__(self, sinks: list[StorageSink]) -> None:
        self.sinks = sinks
        self.backend = "+".join(sink.backend for sink in sinks) if sinks else "noop"

    def write_live_observer_payload(self, payload: dict[str, Any], *, dry_run: bool) -> StorageWriteSummary:
        summaries = [sink.write_live_observer_payload(payload, dry_run=dry_run) for sink in self.sinks]
        if not summaries:
            return NoopStorageSink().write_live_observer_payload(payload, dry_run=dry_run)
        return StorageWriteSummary(
            storage_backend=self.backend,
            rows_attempted=sum(summary.rows_attempted for summary in summaries),
            rows_written=sum(summary.rows_written for summary in summaries),
            dry_run=dry_run,
            skipped_reason=";".join(summary.skipped_reason for summary in summaries if summary.skipped_reason) or None,
        )


class DryRunObserverSink:
    def __init__(self, *, backend: str) -> None:
        self.backend = backend

    def write_live_observer_payload(self, payload: dict[str, Any], *, dry_run: bool) -> StorageWriteSummary:
        if self.backend == "postgres_timescale":
            rows_by_table = build_postgres_rows(payload)
        elif self.backend == "clickhouse":
            rows_by_table = build_clickhouse_rows(payload)
        else:
            rows_by_table = {**build_postgres_rows(payload), **build_clickhouse_rows(payload)}
        rows_attempted = sum(len(rows) for rows in rows_by_table.values())
        return StorageWriteSummary(storage_backend=self.backend, rows_attempted=rows_attempted, rows_written=0, dry_run=True)


class ClickHouseObserverSink:
    backend = "clickhouse"

    def __init__(self, writer: Any) -> None:
        self.writer = writer

    def write_live_observer_payload(self, payload: dict[str, Any], *, dry_run: bool) -> StorageWriteSummary:
        rows_by_table = build_clickhouse_rows(payload)
        rows_attempted = sum(len(rows) for rows in rows_by_table.values())
        if dry_run:
            return StorageWriteSummary(storage_backend=self.backend, rows_attempted=rows_attempted, rows_written=0, dry_run=True)
        for table, rows in rows_by_table.items():
            self.writer.insert_rows(table, rows)
        return StorageWriteSummary(storage_backend=self.backend, rows_attempted=rows_attempted, rows_written=rows_attempted, dry_run=False)


class PostgresObserverSink:
    backend = "postgres_timescale"

    def __init__(self, engine: Any) -> None:
        self.engine = engine

    def write_live_observer_payload(self, payload: dict[str, Any], *, dry_run: bool) -> StorageWriteSummary:
        rows_by_table = build_postgres_rows(payload)
        rows_attempted = sum(len(rows) for rows in rows_by_table.values())
        if dry_run:
            return StorageWriteSummary(storage_backend=self.backend, rows_attempted=rows_attempted, rows_written=0, dry_run=True)
        rows_written = 0
        with self.engine.begin() as connection:
            for table, rows in rows_by_table.items():
                for row in rows:
                    connection.execute(_sql_text(_insert_sql(table, row)), _serialize_row(row))
                    rows_written += 1
        return StorageWriteSummary(storage_backend=self.backend, rows_attempted=rows_attempted, rows_written=rows_written, dry_run=False)


def create_live_observer_storage_sink(*, backend: str = "auto") -> StorageSink:
    requested = backend.strip().lower()
    if requested in {"", "none", "noop"}:
        return NoopStorageSink()
    if requested not in {"auto", "postgres", "clickhouse", "all"}:
        raise ValueError("storage backend must be one of: auto, noop, postgres, clickhouse, all")

    sinks: list[StorageSink] = []
    config = load_storage_stack_config()
    if requested in {"auto", "postgres", "all"} and (config.postgres.sync_database_url or config.postgres.database_url):
        sinks.append(PostgresObserverSink(create_prediction_core_sync_engine_from_env()))
    if requested in {"auto", "clickhouse", "all"}:
        writer = create_clickhouse_writer_from_env()
        if writer is not None:
            sinks.append(ClickHouseObserverSink(writer))

    if sinks:
        return sinks[0] if len(sinks) == 1 else CompositeStorageSink(sinks)
    return NoopStorageSink(skipped_reason=f"{requested}_storage_not_configured")


def write_live_observer_payload_to_storage(payload: dict[str, Any], *, backend: str = "auto", dry_run: bool = False) -> dict[str, Any]:
    if dry_run:
        requested = backend.strip().lower()
        if requested == "postgres":
            return DryRunObserverSink(backend="postgres_timescale").write_live_observer_payload(payload, dry_run=True).to_dict()
        if requested == "clickhouse":
            return DryRunObserverSink(backend="clickhouse").write_live_observer_payload(payload, dry_run=True).to_dict()
        if requested in {"auto", "all"}:
            return DryRunObserverSink(backend="postgres_timescale+clickhouse").write_live_observer_payload(payload, dry_run=True).to_dict()
    sink = create_live_observer_storage_sink(backend=backend)
    return sink.write_live_observer_payload(payload, dry_run=dry_run).to_dict()


def build_clickhouse_rows(payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    profile_events = profile_decision_events_from_shortlist(payload)
    debug_events = debug_decision_events_from_shortlist(payload)
    signal_events = strategy_signal_events_from_shortlist(payload)
    metric_events = [*build_profile_metric_events(profile_events), *build_strategy_metric_events(profile_events)]
    market_rows, orderbook_rows = _clickhouse_live_snapshot_rows(payload)
    return {
        "market_snapshots": market_rows,
        "orderbook_snapshots": orderbook_rows,
        "profile_decisions": [serialize_event(event) for event in profile_events],
        "debug_decisions": [serialize_event(event) for event in debug_events],
        "profile_metrics": [serialize_event(event) for event in metric_events if event.table == "profile_metrics"],
        "strategy_metrics": [serialize_event(event) for event in metric_events if event.table == "strategy_metrics"],
        "strategy_signals": [serialize_event(event) for event in signal_events],
    }


def build_postgres_rows(payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    observed_at = _observed_at(payload)
    markets: list[dict[str, Any]] = []
    orderbooks: list[dict[str, Any]] = []
    health: list[dict[str, Any]] = []
    for row in [item for item in payload.get("shortlist", []) if isinstance(item, dict)]:
        market_id = str(row.get("market_id") or "")
        if market_id:
            markets.append(_market_price_row(row, observed_at=observed_at))
        snapshot = row.get("execution_snapshot") if isinstance(row.get("execution_snapshot"), dict) else None
        if market_id and snapshot:
            orderbooks.append(_orderbook_row(row, snapshot, observed_at=observed_at))
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    health.append(
        {
            "health_id": _stable_id("weather-live-observer-health", str(payload.get("run_id") or "unknown"), observed_at),
            "source": "weather_pm.operator_refresh",
            "checked_at": observed_at,
            "status": "ok" if not summary.get("execution_snapshot_errors") else "degraded",
            "detail": "weather live observer storage bridge",
            "metrics": {
                "paper_only": True,
                "live_order_allowed": False,
                "rows": len([item for item in payload.get("shortlist", []) if isinstance(item, dict)]),
                "execution_snapshot_refreshed": summary.get("execution_snapshot_refreshed", 0),
                "execution_snapshot_errors": summary.get("execution_snapshot_errors", 0),
            },
            "schema_version": "1.0",
        }
    )
    return {"market_price_snapshots": markets, "orderbook_snapshots": orderbooks, "ingestion_health": health}


def assert_not_unmounted_truenas_path(path: str | Path) -> None:
    resolved = Path(path).expanduser().resolve(strict=False)
    truenas_root = Path("/mnt/truenas")
    if resolved == truenas_root or truenas_root in resolved.parents:
        if not os.path.ismount(truenas_root):
            raise ValueError("refusing to write under /mnt/truenas because it is not a mountpoint")


def _observed_at(payload: dict[str, Any]) -> str:
    generated_at = payload.get("generated_at") or payload.get("refreshed_at")
    if isinstance(generated_at, str) and generated_at:
        return generated_at
    artifacts = payload.get("artifacts") if isinstance(payload.get("artifacts"), dict) else {}
    artifact_generated_at = artifacts.get("generated_at")
    if isinstance(artifact_generated_at, str) and artifact_generated_at:
        return artifact_generated_at
    return datetime.now(UTC).isoformat()


def _clickhouse_live_snapshot_rows(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    observed_at = _observed_at(payload)
    run_id = str(payload.get("run_id") or "")
    market_rows: list[dict[str, Any]] = []
    orderbook_rows: list[dict[str, Any]] = []
    for row in [item for item in payload.get("shortlist", []) if isinstance(item, dict)]:
        market_id = str(row.get("market_id") or "")
        if not market_id:
            continue
        snapshot = row.get("execution_snapshot") if isinstance(row.get("execution_snapshot"), dict) else {}
        row_observed_at = snapshot.get("fetched_at") or observed_at
        token_id = str(row.get("token_id") or row.get("condition_id") or "")
        market_rows.append(
            {
                "run_id": run_id,
                "strategy_id": str(row.get("strategy_id") or row.get("matched_strategy_id") or ""),
                "profile_id": str(row.get("strategy_profile_id") or row.get("profile_id") or ""),
                "market_id": market_id,
                "token_id": token_id,
                "observed_at": row_observed_at,
                "mode": "paper",
                "slug": str(row.get("slug") or ""),
                "question": str(row.get("question") or row.get("title") or ""),
                "active": bool(row.get("active", True)),
                "closed": bool(row.get("closed", False)),
                "yes_price": _optional_float(row.get("yes_price") or row.get("market_price")),
                "best_bid": _optional_float(snapshot.get("best_bid_yes") or row.get("best_bid")),
                "best_ask": _optional_float(snapshot.get("best_ask_yes") or row.get("best_ask")),
                "volume": _optional_float(row.get("volume")),
                "liquidity": _optional_float(row.get("liquidity") or row.get("liquidity_usd")),
                "raw": json.dumps({"row": row, "paper_only": True, "live_order_allowed": False}, sort_keys=True, separators=(",", ":")),
            }
        )
        if snapshot:
            orderbook_rows.append(
                {
                    "run_id": run_id,
                    "strategy_id": str(row.get("strategy_id") or row.get("matched_strategy_id") or ""),
                    "profile_id": str(row.get("strategy_profile_id") or row.get("profile_id") or ""),
                    "market_id": market_id,
                    "token_id": token_id or "yes",
                    "observed_at": row_observed_at,
                    "mode": "paper",
                    "best_bid": _optional_float(snapshot.get("best_bid_yes")),
                    "best_ask": _optional_float(snapshot.get("best_ask_yes")),
                    "spread": _spread(snapshot),
                    "bid_depth_levels": len(snapshot.get("bids", [])) if isinstance(snapshot.get("bids"), list) else 0,
                    "ask_depth_levels": len(snapshot.get("asks", [])) if isinstance(snapshot.get("asks"), list) else 0,
                    "bids_json": json.dumps(snapshot.get("bids") or [], sort_keys=True, separators=(",", ":")),
                    "asks_json": json.dumps(snapshot.get("asks") or [], sort_keys=True, separators=(",", ":")),
                    "raw": json.dumps({"row": row, "snapshot": snapshot, "paper_only": True, "live_order_allowed": False}, sort_keys=True, separators=(",", ":")),
                }
            )
    return market_rows, orderbook_rows


def _market_price_row(row: dict[str, Any], *, observed_at: str) -> dict[str, Any]:
    market_id = str(row.get("market_id"))
    snapshot = row.get("execution_snapshot") if isinstance(row.get("execution_snapshot"), dict) else {}
    return {
        "snapshot_id": _stable_id("weather-live-observer-market", market_id, observed_at),
        "market_id": market_id,
        "token_id": str(row.get("token_id") or row.get("condition_id") or "yes"),
        "observed_at": snapshot.get("fetched_at") or observed_at,
        "price": _optional_float(row.get("yes_price") or row.get("market_price")),
        "volume": _optional_float(row.get("volume")),
        "raw": {"row": row, "paper_only": True, "live_order_allowed": False},
        "schema_version": "1.0",
    }


def _orderbook_row(row: dict[str, Any], snapshot: dict[str, Any], *, observed_at: str) -> dict[str, Any]:
    market_id = str(row.get("market_id"))
    return {
        "snapshot_id": _stable_id("weather-live-observer-orderbook", market_id, observed_at),
        "market_id": market_id,
        "token_id": str(row.get("token_id") or row.get("condition_id") or "yes"),
        "observed_at": snapshot.get("fetched_at") or observed_at,
        "bids": _book_side(snapshot, price_key="best_bid_yes", depth_key="yes_bid_depth_usd"),
        "asks": _book_side(snapshot, price_key="best_ask_yes", depth_key="yes_ask_depth_usd"),
        "raw": {"row": row, "paper_only": True, "live_order_allowed": False},
        "schema_version": "1.0",
    }


def _book_side(snapshot: dict[str, Any], *, price_key: str, depth_key: str) -> list[dict[str, Any]]:
    price = snapshot.get(price_key)
    if price is None:
        return []
    return [{"price": price, "depth_usd": snapshot.get(depth_key)}]


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _spread(snapshot: dict[str, Any]) -> float | None:
    bid = _optional_float(snapshot.get("best_bid_yes"))
    ask = _optional_float(snapshot.get("best_ask_yes"))
    if bid is None or ask is None:
        return None
    return ask - bid


def _stable_id(*parts: str) -> str:
    return str(uuid5(NAMESPACE_URL, ":".join(parts)))


def _insert_sql(table: str, row: dict[str, Any]) -> str:
    columns = list(row)
    names = ", ".join(columns)
    values = ", ".join(f"CAST(:{column} AS jsonb)" if column in {"bids", "asks", "raw", "metrics"} else f":{column}" for column in columns)
    conflict = "checked_at" if table == "ingestion_health" else "observed_at"
    return f"INSERT INTO {table} ({names}) VALUES ({values}) ON CONFLICT DO NOTHING"


def _sql_text(sql: str) -> Any:
    try:
        from sqlalchemy import text
    except ImportError:
        return sql
    return text(sql)


def _serialize_row(row: dict[str, Any]) -> dict[str, Any]:
    serialized = dict(row)
    for key in {"bids", "asks", "raw", "metrics"}.intersection(serialized):
        serialized[key] = json.dumps(serialized[key], sort_keys=True, separators=(",", ":"))
    return serialized
