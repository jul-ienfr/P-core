from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from prediction_core.decision.entry_policy import EntryDecision, EntryPolicy, evaluate_entry

from .contracts import StrategyMode, StrategySide, StrategySignal, StrategyTarget


@dataclass(frozen=True, kw_only=True)
class PaperBridgeContext:
    market_price: float
    spread: float
    depth_usd: float
    execution_cost_bps: float = 0.0
    policy: EntryPolicy = field(default_factory=lambda: EntryPolicy(name="strategy_paper_default", q_min=0.05, q_max=0.95, min_edge=0.02, min_confidence=0.6, max_spread=0.05, min_depth_usd=100.0, max_position_usd=10.0))


@dataclass(frozen=True, kw_only=True)
class PaperBridgeDecision:
    signal: StrategySignal
    decision: EntryDecision
    paper_only: bool = True
    trading_action: str = "none"

    def to_dict(self) -> dict[str, Any]:
        payload = self.decision.to_dict()
        payload.update({"strategy_id": self.signal.strategy_id, "paper_only": True, "trading_action": "none", "target": self.signal.target.value})
        return payload


def _skip(signal: StrategySignal, context: PaperBridgeContext, reasons: list[str]) -> PaperBridgeDecision:
    probability = signal.probability if signal.probability is not None else context.market_price
    decision = EntryDecision(
        policy=context.policy.name,
        enter=False,
        action="skip",
        side="yes",
        market_price=round(context.market_price, 4),
        model_probability=round(float(probability), 4),
        confidence=round(float(signal.confidence), 4),
        edge_gross=0.0,
        edge_net_all_in=0.0,
        blocked_by=reasons,
        size_hint_usd=0.0,
    )
    return PaperBridgeDecision(signal=signal, decision=decision)


def paper_decision_from_signal(signal: StrategySignal, context: PaperBridgeContext) -> PaperBridgeDecision:
    if signal.mode == StrategyMode.LIVE_ALLOWED:
        raise ValueError("paper bridge rejects live_allowed signals")
    if signal.probability is None or signal.target != StrategyTarget.EVENT_OUTCOME_FORECASTING:
        return _skip(signal, context, ["non_probability_signal"])
    if signal.side in {StrategySide.NO, StrategySide.DOWN}:
        side = "no"
    elif signal.side in {StrategySide.YES, StrategySide.UP, StrategySide.UNKNOWN}:
        side = "yes"
    else:
        return _skip(signal, context, ["skip_signal"])
    decision = evaluate_entry(
        policy=context.policy,
        market_price=context.market_price,
        model_probability=signal.probability,
        confidence=signal.confidence,
        spread=context.spread,
        depth_usd=context.depth_usd,
        execution_cost_bps=context.execution_cost_bps,
        side=side,
    )
    return PaperBridgeDecision(signal=signal, decision=decision)
