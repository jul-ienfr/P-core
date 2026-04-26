from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import UTC, datetime
from copy import deepcopy
import json
from typing import Any, Mapping

JsonDict = dict[str, Any]
SCHEMA_VERSION = "1.0"


def utc_now() -> datetime:
    return datetime.now(UTC)


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value):
        return asdict(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _to_json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, default=_json_default, sort_keys=True))


@dataclass(frozen=True, kw_only=True)
class SerializableContract:
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> JsonDict:
        return _to_json_safe(asdict(self))

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    def to_record(self) -> JsonDict:
        return deepcopy(self.to_dict())


@dataclass(frozen=True, kw_only=True)
class Market(SerializableContract):
    market_id: str
    slug: str
    question: str
    source: str
    active: bool = True
    closed: bool = False
    created_at: datetime | None = None
    raw: JsonDict = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True)
class MarketSnapshot(SerializableContract):
    snapshot_id: str
    market_id: str
    slug: str
    question: str
    source: str
    observed_at: datetime
    active: bool = True
    closed: bool = False
    yes_price: float | None = None
    best_bid: float | None = None
    best_ask: float | None = None
    volume: float | None = None
    liquidity: float | None = None
    token_ids: list[str] = field(default_factory=list)
    raw: JsonDict = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True)
class OrderbookSnapshot(SerializableContract):
    snapshot_id: str
    market_id: str
    token_id: str
    observed_at: datetime
    bids: list[Mapping[str, Any]] = field(default_factory=list)
    asks: list[Mapping[str, Any]] = field(default_factory=list)
    raw: JsonDict = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True)
class TradeEvent(SerializableContract):
    trade_id: str
    market_id: str
    token_id: str
    observed_at: datetime
    price: float
    size: float
    side: str
    raw: JsonDict = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True)
class ShadowPrediction(SerializableContract):
    prediction_id: str
    market_id: str
    agent_id: str
    observed_at: datetime
    horizon_seconds: int
    predicted_crowd_direction: str
    confidence: float
    rationale: str
    features: JsonDict = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True)
class CrowdFlowObservation(SerializableContract):
    observation_id: str
    prediction_id: str
    market_id: str
    observed_at: datetime
    window_seconds: int
    price_delta: float
    volume_delta: float
    direction_hit: bool
    liquidity_caveat: str | None
    metrics: JsonDict = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True)
class IngestionHealth(SerializableContract):
    health_id: str
    source: str
    checked_at: datetime
    status: str
    detail: str | None = None
    metrics: JsonDict = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True)
class ArtifactMetadata(SerializableContract):
    artifact_id: str
    artifact_type: str
    path: str
    created_at: datetime
    schema_version: str = SCHEMA_VERSION
    source: str
    row_count: int
    sha256: str
