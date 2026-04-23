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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


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
    transaction_fee_bps: float = 0.0
    deposit_fee_usd: float = 0.0
    withdrawal_fee_usd: float = 0.0
    order_book_depth_usd: float = 0.0
    expected_slippage_bps: float = 0.0
    all_in_cost_bps: float = 0.0
    all_in_cost_usd: float = 0.0

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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class DecisionResult:
    status: str
    max_position_pct_bankroll: float
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
