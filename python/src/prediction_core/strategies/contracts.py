from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import UTC, datetime
from enum import Enum
import json
import math
from typing import Any


class StrategyMode(str, Enum):
    RESEARCH_ONLY = "research_only"
    PAPER_ONLY = "paper_only"
    LIVE_ALLOWED = "live_allowed"


class StrategyTarget(str, Enum):
    EVENT_OUTCOME_FORECASTING = "event_outcome_forecasting"
    CROWD_MOVEMENT_FORECASTING = "crowd_movement_forecasting"
    EXECUTABLE_EDGE_AFTER_COSTS = "executable_edge_after_costs"


class StrategySide(str, Enum):
    YES = "yes"
    NO = "no"
    UP = "up"
    DOWN = "down"
    UNKNOWN = "unknown"
    SKIP = "skip"


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return asdict(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _jsonable(payload: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(payload, default=_json_default, sort_keys=True))


def _mode(value: StrategyMode | str) -> StrategyMode:
    return value if isinstance(value, StrategyMode) else StrategyMode(str(value))


def _target(value: StrategyTarget | str) -> StrategyTarget:
    return value if isinstance(value, StrategyTarget) else StrategyTarget(str(value))


def _side(value: StrategySide | str | None) -> StrategySide:
    if value is None:
        return StrategySide.UNKNOWN
    return value if isinstance(value, StrategySide) else StrategySide(str(value).lower())


def _bounded(name: str, value: float | None, *, optional: bool = False) -> float | None:
    if value is None and optional:
        return None
    resolved = float(value)  # type: ignore[arg-type]
    if not math.isfinite(resolved) or resolved < 0.0 or resolved > 1.0:
        raise ValueError(f"{name} must be between 0 and 1")
    return resolved


def _expected_move(value: float | None) -> float | None:
    if value is None:
        return None
    resolved = float(value)
    if not math.isfinite(resolved) or resolved < -1.0 or resolved > 1.0:
        raise ValueError("expected_move must be between -1 and 1")
    return resolved


@dataclass(frozen=True, kw_only=True)
class StrategyDescriptor:
    strategy_id: str
    name: str
    target: StrategyTarget | str
    mode: StrategyMode | str = StrategyMode.RESEARCH_ONLY
    version: str = "0.1.0"
    description: str = ""
    source: str = "prediction_core.strategies"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.strategy_id.strip():
            raise ValueError("strategy_id is required")
        object.__setattr__(self, "mode", _mode(self.mode))
        object.__setattr__(self, "target", _target(self.target))

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(asdict(self))

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True, kw_only=True)
class StrategyRunRequest:
    market_id: str
    requested_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.market_id.strip():
            raise ValueError("market_id is required")
        if self.requested_at.tzinfo is None:
            object.__setattr__(self, "requested_at", self.requested_at.replace(tzinfo=UTC))

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(asdict(self))


@dataclass(frozen=True, kw_only=True)
class StrategySignal:
    strategy_id: str
    market_id: str
    target: StrategyTarget | str
    mode: StrategyMode | str
    generated_at: datetime
    side: StrategySide | str = StrategySide.UNKNOWN
    probability: float | None = None
    confidence: float = 0.0
    expected_move: float | None = None
    features: dict[str, Any] = field(default_factory=dict)
    risks: list[str] = field(default_factory=list)
    source: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    trading_action: str = "none"
    gate_status: str = "unknown"

    def __post_init__(self) -> None:
        if not self.strategy_id.strip():
            raise ValueError("strategy_id is required")
        if not self.market_id.strip():
            raise ValueError("market_id is required")
        object.__setattr__(self, "target", _target(self.target))
        object.__setattr__(self, "mode", _mode(self.mode))
        object.__setattr__(self, "side", _side(self.side))
        object.__setattr__(self, "probability", _bounded("probability", self.probability, optional=True))
        object.__setattr__(self, "confidence", _bounded("confidence", self.confidence) or 0.0)
        object.__setattr__(self, "expected_move", _expected_move(self.expected_move))
        if self.generated_at.tzinfo is None:
            object.__setattr__(self, "generated_at", self.generated_at.replace(tzinfo=UTC))
        if self.trading_action != "none":
            raise ValueError('StrategySignal.trading_action must be "none"')
        if not isinstance(self.features, dict):
            raise ValueError("features must be a dict")
        if not isinstance(self.source, dict):
            raise ValueError("source must be a dict")

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(asdict(self))

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True, kw_only=True)
class StrategyRunResult:
    strategy_id: str
    market_id: str
    mode: StrategyMode | str
    signals: list[StrategySignal] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "mode", _mode(self.mode))

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(asdict(self))

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
