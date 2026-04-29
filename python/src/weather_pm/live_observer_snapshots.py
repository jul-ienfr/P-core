"""Weather live-observer snapshot contracts.

These dataclasses are intentionally paper-only serialization contracts.  They do
not place orders, reference wallets, sign payloads, or allow copy-trading side
effects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class CompactMarketSnapshot:
    observed_at: datetime
    market_id: str
    event_id: str
    slug: str
    question: str
    city: str
    metric: str
    target_date: str | date
    best_bid: float | None = None
    best_ask: float | None = None
    last_trade_price: float | None = None
    volume: float | None = None
    liquidity: float | None = None
    open_interest: float | None = None
    active: bool | None = None
    closed: bool | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    paper_only: bool = True
    live_order_allowed: bool = False

    def __post_init__(self) -> None:
        _enforce_paper_contract(self.paper_only, self.live_order_allowed)

    def to_dict(self) -> dict[str, Any]:
        return _clean_none(
            {
                "snapshot_type": "compact_market_snapshot",
                "observed_at": _json_value(self.observed_at),
                "market_id": self.market_id,
                "event_id": self.event_id,
                "slug": self.slug,
                "question": self.question,
                "city": self.city,
                "metric": self.metric,
                "target_date": _json_value(self.target_date),
                "best_bid": self.best_bid,
                "best_ask": self.best_ask,
                "last_trade_price": self.last_trade_price,
                "volume": self.volume,
                "liquidity": self.liquidity,
                "open_interest": self.open_interest,
                "active": self.active,
                "closed": self.closed,
                "metadata": _json_value(dict(self.metadata)),
                "paper_only": self.paper_only,
                "live_order_allowed": self.live_order_allowed,
            }
        )


@dataclass(frozen=True)
class WeatherBinSurfaceSnapshot:
    observed_at: datetime
    market_id: str
    event_id: str
    city: str
    metric: str
    target_date: str | date
    bins: Sequence[Mapping[str, Any]]
    source_market_ids: Sequence[str] = field(default_factory=tuple)
    surface_version: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    paper_only: bool = True
    live_order_allowed: bool = False

    def __post_init__(self) -> None:
        _enforce_paper_contract(self.paper_only, self.live_order_allowed)

    def to_dict(self) -> dict[str, Any]:
        return _clean_none(
            {
                "snapshot_type": "weather_bin_surface_snapshot",
                "observed_at": _json_value(self.observed_at),
                "market_id": self.market_id,
                "event_id": self.event_id,
                "city": self.city,
                "metric": self.metric,
                "target_date": _json_value(self.target_date),
                "bins": _json_value([dict(item) for item in self.bins]),
                "source_market_ids": list(self.source_market_ids),
                "surface_version": self.surface_version,
                "metadata": _json_value(dict(self.metadata)),
                "paper_only": self.paper_only,
                "live_order_allowed": self.live_order_allowed,
            }
        )


@dataclass(frozen=True)
class ForecastSourceSnapshot:
    observed_at: datetime
    source: str
    city: str
    metric: str
    target_date: str | date
    forecast_value: float | int | str | None = None
    forecast_units: str | None = None
    issued_at: datetime | None = None
    source_uri: str | None = None
    raw_payload: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    paper_only: bool = True
    live_order_allowed: bool = False

    def __post_init__(self) -> None:
        _enforce_paper_contract(self.paper_only, self.live_order_allowed)

    def to_dict(self) -> dict[str, Any]:
        return _clean_none(
            {
                "snapshot_type": "forecast_source_snapshot",
                "observed_at": _json_value(self.observed_at),
                "source": self.source,
                "source_uri": self.source_uri,
                "city": self.city,
                "metric": self.metric,
                "target_date": _json_value(self.target_date),
                "forecast_value": self.forecast_value,
                "forecast_units": self.forecast_units,
                "issued_at": _json_value(self.issued_at),
                "raw_payload": _json_value(dict(self.raw_payload)),
                "metadata": _json_value(dict(self.metadata)),
                "paper_only": self.paper_only,
                "live_order_allowed": self.live_order_allowed,
            }
        )


@dataclass(frozen=True)
class FollowedAccountTradeTrigger:
    observed_at: datetime
    account: str
    profile_id: str
    transaction_hash: str
    market_id: str
    side: str
    price: float
    size: float
    paper_decision: str = "capture_rich_snapshot"
    event_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    paper_only: bool = True
    live_order_allowed: bool = False

    def __post_init__(self) -> None:
        _enforce_paper_contract(self.paper_only, self.live_order_allowed)

    def to_dict(self) -> dict[str, Any]:
        return _clean_none(
            {
                "snapshot_type": "followed_account_trade_trigger",
                "observed_at": _json_value(self.observed_at),
                "account": self.account,
                "profile_id": self.profile_id,
                "transaction_hash": self.transaction_hash,
                "market_id": self.market_id,
                "event_id": self.event_id,
                "side": self.side,
                "price": self.price,
                "size": self.size,
                "paper_decision": self.paper_decision,
                "metadata": _json_value(dict(self.metadata)),
                "paper_only": self.paper_only,
                "live_order_allowed": self.live_order_allowed,
            }
        )


def assert_paper_only_storage_result(result: Any) -> None:
    """Validate a storage manifest preserves paper-only/no-live-order semantics."""

    if hasattr(result, "to_dict"):
        payload = result.to_dict()
    elif isinstance(result, Mapping):
        payload = dict(result)
    else:
        raise TypeError("storage result must be a mapping or expose to_dict()")
    if payload.get("paper_only") is not True:
        raise ValueError("storage result paper_only must be true")
    if payload.get("live_order_allowed", False) is not False:
        raise ValueError("storage result live_order_allowed must be false")


def _enforce_paper_contract(paper_only: bool, live_order_allowed: bool) -> None:
    if paper_only is not True:
        raise ValueError("paper_only must be true for live observer snapshots")
    if live_order_allowed is not False:
        raise ValueError("live_order_allowed must be false for live observer snapshots")


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _clean_none(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}
