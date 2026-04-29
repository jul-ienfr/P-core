"""Deterministic storage estimates for the weather live observer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from weather_pm.live_observer_config import LiveObserverConfig, ScenarioConfig

COMPACT_MARKET_SNAPSHOT_BYTES = 600
BIN_SURFACE_SNAPSHOT_BYTES = 2500
FORECAST_SOURCE_SNAPSHOT_BYTES = 1800
TRADE_TRIGGER_BYTES = 1000

SECONDS_PER_DAY = 86_400
DAYS_PER_MONTH = 30
BYTES_PER_MIB = 1024 * 1024
BYTES_PER_GIB = 1024 * 1024 * 1024


@dataclass(frozen=True)
class StreamStorageEstimate:
    """Per-stream deterministic storage estimate."""

    enabled: bool
    items_per_interval: int
    interval_seconds: int
    bytes_per_item: int
    applies_if_enabled_bytes_per_day: int
    bytes_per_day: int

    @property
    def mb_per_day(self) -> float:
        return self.bytes_per_day / BYTES_PER_MIB

    @property
    def applies_if_enabled_mb_per_day(self) -> float:
        return self.applies_if_enabled_bytes_per_day / BYTES_PER_MIB

    def to_dict(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "items_per_interval": self.items_per_interval,
            "interval_seconds": self.interval_seconds,
            "bytes_per_item": self.bytes_per_item,
            "bytes_per_day": self.bytes_per_day,
            "mb_per_day": round(self.mb_per_day, 2),
            "applies_if_enabled_bytes_per_day": self.applies_if_enabled_bytes_per_day,
            "applies_if_enabled_mb_per_day": round(self.applies_if_enabled_mb_per_day, 2),
        }


@dataclass(frozen=True)
class LiveObserverStorageEstimate:
    """Top-level weather live observer storage estimate."""

    scenario: str
    collection_enabled: bool
    collection_active: bool
    estimate_applies_if_enabled: bool
    streams: Mapping[str, StreamStorageEstimate]
    active_streams: Mapping[str, StreamStorageEstimate]
    storage_primary: str | None = None
    base_dir: str | None = None
    paper_only: bool | None = None
    live_order_allowed: bool | None = None

    @property
    def bytes_per_day(self) -> int:
        return sum(stream.applies_if_enabled_bytes_per_day for stream in self.streams.values())

    @property
    def active_bytes_per_day(self) -> int:
        return sum(stream.bytes_per_day for stream in self.active_streams.values())

    @property
    def mb_per_day(self) -> float:
        return self.bytes_per_day / BYTES_PER_MIB

    @property
    def gb_per_month(self) -> float:
        return (self.bytes_per_day * DAYS_PER_MONTH) / BYTES_PER_GIB

    @property
    def active_mb_per_day(self) -> float:
        return self.active_bytes_per_day / BYTES_PER_MIB

    @property
    def active_gb_per_month(self) -> float:
        return (self.active_bytes_per_day * DAYS_PER_MONTH) / BYTES_PER_GIB

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "scenario": self.scenario,
            "collection_enabled": self.collection_enabled,
            "collection_active": self.collection_active,
            "estimate_applies_if_enabled": self.estimate_applies_if_enabled,
            "bytes_per_day": self.bytes_per_day,
            "mb_per_day": round(self.mb_per_day, 2),
            "gb_per_month": round(self.gb_per_month, 2),
            "active_bytes_per_day": self.active_bytes_per_day,
            "active_mb_per_day": round(self.active_mb_per_day, 2),
            "active_gb_per_month": round(self.active_gb_per_month, 2),
            "streams": {name: stream.to_dict() for name, stream in self.streams.items()},
            "active_streams": {name: stream.to_dict() for name, stream in self.active_streams.items()},
        }
        if self.storage_primary is not None:
            payload["storage_primary"] = self.storage_primary
        if self.base_dir is not None:
            payload["base_dir"] = self.base_dir
        if self.paper_only is not None:
            payload["paper_only"] = self.paper_only
        if self.live_order_allowed is not None:
            payload["live_order_allowed"] = self.live_order_allowed
        return payload


def estimate_live_observer_storage(config: LiveObserverConfig | ScenarioConfig) -> LiveObserverStorageEstimate:
    """Estimate storage for the active scenario in MiB/day and GiB/month.

    When a full ``LiveObserverConfig`` is supplied, stream toggles and the global
    collection switch are reflected in ``bytes_per_day`` for each active stream.
    The top-level ``mb_per_day``/``gb_per_month`` remains the prepared estimate
    that applies if collection is enabled, matching the operator-facing CLI.
    """

    if isinstance(config, LiveObserverConfig):
        scenario = config.active
        scenario_name = config.active_scenario
        collection_enabled = config.collection.enabled
        collection_active = config.live_collection_active
        stream_enabled = {
            "compact_market_snapshot": _stream_enabled(config, "market_snapshots"),
            "weather_bin_surface_snapshot": _stream_enabled(config, "bin_surfaces"),
            "forecast_source_snapshot": _stream_enabled(config, "forecasts"),
            "followed_account_trade_trigger": _stream_enabled(config, "account_trades"),
        }
        storage_primary = config.storage.primary
        base_dir = config.paths.base_dir
        paper_only = config.safety.paper_only
        live_order_allowed = config.safety.live_order_allowed
    else:
        scenario = config
        scenario_name = "scenario"
        collection_enabled = True
        collection_active = True
        stream_enabled = {
            "compact_market_snapshot": True,
            "weather_bin_surface_snapshot": True,
            "forecast_source_snapshot": True,
            "followed_account_trade_trigger": True,
        }
        storage_primary = None
        base_dir = None
        paper_only = None
        live_order_allowed = None

    streams = _scenario_stream_estimates(scenario, stream_enabled, collection_active=True)
    active_streams = _scenario_stream_estimates(
        scenario,
        stream_enabled,
        collection_active=collection_active,
    )
    return LiveObserverStorageEstimate(
        scenario=scenario_name,
        collection_enabled=collection_enabled,
        collection_active=collection_active,
        estimate_applies_if_enabled=not collection_active,
        streams=streams,
        active_streams=active_streams,
        storage_primary=storage_primary,
        base_dir=base_dir,
        paper_only=paper_only,
        live_order_allowed=live_order_allowed,
    )


def _scenario_stream_estimates(
    scenario: ScenarioConfig,
    stream_enabled: Mapping[str, bool],
    *,
    collection_active: bool,
) -> dict[str, StreamStorageEstimate]:
    return {
        "compact_market_snapshot": _stream_estimate(
            enabled=stream_enabled["compact_market_snapshot"],
            collection_active=collection_active,
            items_per_interval=scenario.market_limit,
            interval_seconds=scenario.compact_market_snapshot_interval_seconds,
            bytes_per_item=COMPACT_MARKET_SNAPSHOT_BYTES,
        ),
        "weather_bin_surface_snapshot": _stream_estimate(
            enabled=stream_enabled["weather_bin_surface_snapshot"],
            collection_active=collection_active,
            items_per_interval=scenario.surface_limit,
            interval_seconds=scenario.bin_surface_snapshot_interval_seconds,
            bytes_per_item=BIN_SURFACE_SNAPSHOT_BYTES,
        ),
        "forecast_source_snapshot": _stream_estimate(
            enabled=stream_enabled["forecast_source_snapshot"],
            collection_active=collection_active,
            items_per_interval=scenario.surface_limit,
            interval_seconds=scenario.forecast_snapshot_interval_seconds,
            bytes_per_item=FORECAST_SOURCE_SNAPSHOT_BYTES,
        ),
        "followed_account_trade_trigger": _stream_estimate(
            enabled=stream_enabled["followed_account_trade_trigger"],
            collection_active=collection_active,
            items_per_interval=1,
            interval_seconds=scenario.trade_trigger_poll_interval_seconds,
            bytes_per_item=TRADE_TRIGGER_BYTES,
        ),
    }


def _stream_estimate(
    *,
    enabled: bool,
    collection_active: bool,
    items_per_interval: int,
    interval_seconds: int,
    bytes_per_item: int,
) -> StreamStorageEstimate:
    applies_if_enabled_bytes_per_day = _bytes_per_day(
        items_per_interval=items_per_interval,
        interval_seconds=interval_seconds,
        bytes_per_item=bytes_per_item,
    )
    bytes_per_day = applies_if_enabled_bytes_per_day if enabled and collection_active else 0
    return StreamStorageEstimate(
        enabled=enabled,
        items_per_interval=items_per_interval,
        interval_seconds=interval_seconds,
        bytes_per_item=bytes_per_item,
        applies_if_enabled_bytes_per_day=applies_if_enabled_bytes_per_day,
        bytes_per_day=bytes_per_day,
    )


def _bytes_per_day(*, items_per_interval: int, interval_seconds: int, bytes_per_item: int) -> int:
    if items_per_interval <= 0 or interval_seconds <= 0 or bytes_per_item <= 0:
        return 0
    return int((SECONDS_PER_DAY / interval_seconds) * items_per_interval * bytes_per_item)


def _stream_enabled(config: LiveObserverConfig, name: str) -> bool:
    toggle = config.streams.get(name)
    return True if toggle is None else bool(toggle.enabled)
