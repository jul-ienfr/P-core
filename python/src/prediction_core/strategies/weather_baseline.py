from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Mapping

from .contracts import StrategyDescriptor, StrategyMode, StrategyRunRequest, StrategyRunResult, StrategySide, StrategySignal, StrategyTarget


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def weather_signal_from_payload(payload: Mapping[str, Any], *, strategy_id: str = "weather_baseline", mode: StrategyMode = StrategyMode.PAPER_ONLY) -> StrategySignal:
    decision = payload.get("decision", {}) if isinstance(payload.get("decision"), Mapping) else {}
    score = payload.get("score", {}) if isinstance(payload.get("score"), Mapping) else payload
    market_id = str(payload.get("market_id") or score.get("market_id") or decision.get("market_id") or "unknown")
    probability = _float_or_none(score.get("probability") or score.get("probability_yes") or score.get("forecast_probability"))
    confidence = float(score.get("confidence", decision.get("confidence", 0.0)) or 0.0)
    edge = _float_or_none(score.get("edge") if score.get("edge") is not None else decision.get("edge"))
    action = str(decision.get("action") or decision.get("status") or "skip").lower()
    side = StrategySide.YES if action in {"yes", "buy", "enter", "paper_trade_small"} else StrategySide.SKIP if action in {"skip", "none"} else StrategySide.UNKNOWN
    generated_at = payload.get("generated_at") or score.get("generated_at") or datetime.now(UTC)
    if isinstance(generated_at, str):
        generated_at = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    caveats = decision.get("execution_caveats") or decision.get("caveats") or []
    if isinstance(caveats, str):
        caveats = [caveats]
    source_refs = payload.get("source_references") or score.get("source_references") or payload.get("sources") or []
    features = {
        "edge": edge,
        "decision_action": action,
        "score": {k: v for k, v in score.items() if k not in {"probability", "probability_yes", "forecast_probability", "confidence"}},
        "execution_caveats": list(caveats),
    }
    return StrategySignal(
        strategy_id=strategy_id,
        market_id=market_id,
        target=StrategyTarget.EVENT_OUTCOME_FORECASTING,
        mode=mode,
        generated_at=generated_at,
        side=side,
        probability=probability,
        confidence=confidence,
        expected_move=edge,
        features=features,
        risks=list(caveats) or ["weather adapter fixture; no live execution"],
        source={"adapter": "weather_baseline", "references": source_refs},
        metadata={"raw_decision": dict(decision), "gate_status": decision.get("gate_status", action)},
        gate_status=str(decision.get("gate_status", action)),
    )


class WeatherBaselineStrategy:
    def __init__(self, payloads: list[Mapping[str, Any]] | None = None, *, mode: StrategyMode = StrategyMode.PAPER_ONLY) -> None:
        self.payloads = list(payloads or [])
        self.descriptor = StrategyDescriptor(
            strategy_id="weather_baseline",
            name="Weather baseline adapter",
            target=StrategyTarget.EVENT_OUTCOME_FORECASTING,
            mode=mode,
            source="weather_pm/prediction_core.orchestrator",
        )

    def run(self, request: StrategyRunRequest) -> StrategyRunResult:
        payloads = self.payloads or [request.payload]
        signals = [weather_signal_from_payload({**dict(payload), "market_id": dict(payload).get("market_id", request.market_id)}, strategy_id=self.descriptor.strategy_id, mode=self.descriptor.mode) for payload in payloads]
        return StrategyRunResult(strategy_id=self.descriptor.strategy_id, market_id=request.market_id, mode=self.descriptor.mode, signals=signals)
