from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class MarketStructure:
    city: str
    measurement_kind: str
    unit: str
    is_threshold: bool
    is_exact_bin: bool
    target_value: float | None
    range_low: float | None
    range_high: float | None
    threshold_direction: str | None = None
    date_local: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ResolutionMetadata:
    provider: str
    source_url: str | None
    station_code: str | None
    station_name: str | None
    station_type: str
    wording_clear: bool
    rules_clear: bool
    manual_review_needed: bool
    revision_risk: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ForecastBundle:
    source_count: int
    consensus_value: float | None
    dispersion: float | None
    historical_station_available: bool
    source_provider: str | None = None
    source_station_code: str | None = None
    source_url: str | None = None
    source_latency_tier: str = "fallback"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class StationHistoryPoint:
    timestamp: str
    value: float
    unit: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class StationHistoryBundle:
    source_provider: str
    station_code: str | None
    source_url: str | None
    latency_tier: str
    points: list[StationHistoryPoint]
    summary: dict[str, float]
    polling_focus: str | None = None
    expected_lag_seconds: int | None = None
    source_lag_seconds: int | None = None

    def latest(self) -> StationHistoryPoint | None:
        if not self.points:
            return None
        return self.points[-1]

    def latency_diagnostics(self) -> dict[str, Any]:
        latest = self.latest()
        payload: dict[str, Any] = {
            "provider": self.source_provider,
            "station_code": self.station_code,
            "tier": self.latency_tier,
            "direct": self.latency_tier.startswith("direct"),
            "point_count": len(self.points),
            "latest_timestamp": latest.timestamp if latest else None,
            "latest_value": latest.value if latest else None,
            "unit": latest.unit if latest else None,
            "source_url": self.source_url,
        }
        if self.polling_focus is not None:
            payload["polling_focus"] = self.polling_focus
        if self.expected_lag_seconds is not None:
            payload["expected_lag_seconds"] = self.expected_lag_seconds
        if self.source_lag_seconds is not None:
            payload["source_lag_seconds"] = self.source_lag_seconds
        return payload

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        latest = self.latest()
        if latest:
            payload["summary"] = {
                **payload["summary"],
                "latest": round(latest.value, 2),
                "point_count": float(len(self.points)),
            }
        payload["latest"] = latest.to_dict() if latest else None
        return payload


@dataclass(slots=True)
class ModelOutput:
    probability_yes: float
    confidence: float
    method: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class NeighborContext:
    neighbor_market_count: int
    neighbor_inconsistency: float
    threshold_bin_inconsistency: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ExecutionFeatures:
    spread: float
    hours_to_resolution: float | None
    volume_usd: float
    fillable_size_usd: float
    execution_speed_required: str
    slippage_risk: str
    max_impact_bps: float = 150.0
    transaction_fee_bps: float = 0.0
    deposit_fee_usd: float = 0.0
    withdrawal_fee_usd: float = 0.0
    order_book_depth_usd: float = 0.0
    expected_slippage_bps: float = 0.0
    all_in_cost_bps: float = 0.0
    all_in_cost_usd: float = 0.0
    quoted_best_bid: float | None = None
    quoted_best_ask: float | None = None
    quoted_mid_price: float | None = None
    estimated_avg_fill_price: float | None = None
    estimated_slippage_bps: float = 0.0
    estimated_trading_fee_bps: float = 0.0
    estimated_total_cost_bps: float = 0.0
    edge_net_execution: float | None = None
    edge_net_all_in: float | None = None
    best_effort_reason: str | None = None
    tradeability_status: str = "tradeable"
    cost_risk: str = "low"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ScoreResult:
    raw_edge: float
    edge_theoretical: float
    data_quality: float
    resolution_clarity: float
    execution_friction: float
    competition_inefficiency: float
    total_score: float
    grade: str
    edge_net_execution: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class DecisionResult:
    status: str
    max_position_pct_bankroll: float
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
