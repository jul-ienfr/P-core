from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Iterable

from panoptique.bookmaker import BookmakerInput, BookmakerOutput, bookmaker_v0

from .contracts import StrategyMode, StrategySignal, StrategyTarget


@dataclass(frozen=True, kw_only=True)
class BookmakerBridgeResult:
    output: BookmakerOutput | None
    inputs: list[BookmakerInput]
    excluded: list[dict[str, Any]] = field(default_factory=list)
    research_only: bool = True
    paper_only: bool = True
    trading_action: str = "none"

    def to_dict(self) -> dict[str, Any]:
        return {
            "output": self.output.to_dict() if self.output else None,
            "inputs": [item.__dict__ for item in self.inputs],
            "excluded": self.excluded,
            "research_only": self.research_only,
            "paper_only": self.paper_only,
            "trading_action": self.trading_action,
        }


def signal_to_bookmaker_input(signal: StrategySignal) -> tuple[BookmakerInput | None, dict[str, Any] | None]:
    if signal.target != StrategyTarget.EVENT_OUTCOME_FORECASTING:
        return None, {"strategy_id": signal.strategy_id, "reason": "incompatible_target", "target": signal.target.value}
    if signal.probability is None:
        return None, {"strategy_id": signal.strategy_id, "reason": "missing_probability"}
    if signal.side.value in {"unknown", "skip"} or signal.gate_status in {"skip", "not_enough_data"}:
        return None, {"strategy_id": signal.strategy_id, "reason": "unknown_or_skip_signal"}
    return BookmakerInput(
        agent_id=signal.strategy_id,
        probability_yes=signal.probability,
        weight=float(signal.metadata.get("bookmaker_weight", signal.confidence or 1.0)),
        metric_target=signal.target.value,
        metadata={"mode": signal.mode.value, "market_id": signal.market_id, "source": signal.source, "features": signal.features},
    ), None


def run_bookmaker_from_signals(signals: Iterable[StrategySignal], *, market_id: str, generated_at: datetime | None = None) -> BookmakerBridgeResult:
    inputs: list[BookmakerInput] = []
    excluded: list[dict[str, Any]] = []
    for signal in signals:
        item, reason = signal_to_bookmaker_input(signal)
        if item is None:
            excluded.append(reason or {"strategy_id": signal.strategy_id, "reason": "excluded"})
        else:
            inputs.append(item)
    output = bookmaker_v0(inputs, market_id=market_id, generated_at=generated_at or datetime.now(UTC)) if inputs else None
    if output is not None:
        output.metadata["strategy_bridge"] = {"excluded": excluded, "metric_targets": sorted({item.metric_target for item in inputs})}
    return BookmakerBridgeResult(output=output, inputs=inputs, excluded=excluded)
