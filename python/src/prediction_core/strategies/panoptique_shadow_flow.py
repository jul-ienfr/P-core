from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Mapping

from .contracts import StrategyDescriptor, StrategyMode, StrategyRunRequest, StrategyRunResult, StrategySide, StrategySignal, StrategyTarget


def _dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return datetime.now(UTC)


def _side(direction: str) -> StrategySide:
    direction = direction.lower()
    if direction in {"up", "yes", "buy"}:
        return StrategySide.UP
    if direction in {"down", "no", "sell"}:
        return StrategySide.DOWN
    return StrategySide.UNKNOWN


def panoptique_signal_from_record(record: Mapping[str, Any], *, strategy_id: str = "panoptique_shadow_flow", mode: StrategyMode = StrategyMode.RESEARCH_ONLY) -> StrategySignal:
    prediction = record.get("prediction", {}) if isinstance(record.get("prediction"), Mapping) else {}
    metrics = record.get("metrics", {}) if isinstance(record.get("metrics"), Mapping) else {}
    observation = record.get("observation", {}) if isinstance(record.get("observation"), Mapping) else {}
    status = str(record.get("status") or metrics.get("status") or prediction.get("status") or "ok")
    direction = str(record.get("predicted_crowd_direction") or prediction.get("predicted_crowd_direction") or metrics.get("predicted_crowd_direction") or "unknown")
    expected_move = float(record.get("expected_crowd_move", prediction.get("expected_crowd_move", metrics.get("expected_crowd_move", 0.0))) or 0.0)
    confidence = float(record.get("confidence", prediction.get("confidence", metrics.get("confidence", 0.0))) or 0.0)
    market_id = str(record.get("market_id") or prediction.get("market_id") or observation.get("market_id") or "unknown")
    generated_at = _dt(record.get("generated_at") or prediction.get("generated_at") or prediction.get("observed_at") or observation.get("observed_at"))
    features = {
        "archetype": record.get("archetype") or prediction.get("archetype") or metrics.get("archetype") or "crowd_flow",
        "window": record.get("window") or prediction.get("window") or metrics.get("window"),
        "expected_move": expected_move,
        "observed_move": record.get("observed_crowd_move", observation.get("price_delta")),
        "observed_count": record.get("observed_count", metrics.get("observed_count")),
        "matched_count": record.get("matched_count", metrics.get("matched_count")),
        "status": status,
    }
    risks = ["not enough matched observations"] if status == "not_enough_data" else ["crowd-flow research signal; no execution"]
    return StrategySignal(
        strategy_id=strategy_id,
        market_id=market_id,
        target=StrategyTarget.CROWD_MOVEMENT_FORECASTING,
        mode=mode,
        generated_at=generated_at,
        side=StrategySide.SKIP if status == "not_enough_data" else _side(direction),
        probability=None,
        confidence=confidence,
        expected_move=expected_move,
        features=features,
        risks=risks,
        source={"adapter": "panoptique_shadow_flow", "record_id": record.get("prediction_id") or prediction.get("prediction_id")},
        metadata={"gate_status": status, "direction": direction},
        gate_status=status,
    )


class PanoptiqueShadowFlowStrategy:
    def __init__(self, records: list[Mapping[str, Any]] | None = None, *, mode: StrategyMode = StrategyMode.RESEARCH_ONLY) -> None:
        if mode == StrategyMode.LIVE_ALLOWED:
            raise ValueError("PanoptiqueShadowFlowStrategy is research/paper only")
        self.records = list(records or [])
        self.descriptor = StrategyDescriptor(
            strategy_id="panoptique_shadow_flow",
            name="Panoptique shadow-flow adapter",
            target=StrategyTarget.CROWD_MOVEMENT_FORECASTING,
            mode=mode,
            source="panoptique.shadow_bots/crowd_flow",
        )

    def run(self, request: StrategyRunRequest) -> StrategyRunResult:
        rows = self.records or [request.payload]
        signals = [panoptique_signal_from_record({**dict(row), "market_id": dict(row).get("market_id", request.market_id)}, strategy_id=self.descriptor.strategy_id, mode=self.descriptor.mode) for row in rows]
        return StrategyRunResult(strategy_id=self.descriptor.strategy_id, market_id=request.market_id, mode=self.descriptor.mode, signals=signals)
