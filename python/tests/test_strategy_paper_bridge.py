from __future__ import annotations

from datetime import UTC, datetime

import pytest

from prediction_core.strategies import StrategyMode, StrategySide, StrategySignal, StrategyTarget
from prediction_core.strategies.paper_bridge import PaperBridgeContext, paper_decision_from_signal


def make_signal(*, probability: float | None = 0.7, confidence: float = 0.8, target: StrategyTarget = StrategyTarget.EVENT_OUTCOME_FORECASTING, mode: StrategyMode = StrategyMode.PAPER_ONLY, side: StrategySide = StrategySide.YES) -> StrategySignal:
    return StrategySignal(
        strategy_id="s",
        market_id="m",
        target=target,
        mode=mode,
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
        side=side,
        probability=probability,
        confidence=confidence,
        features={},
        risks=[],
        source={},
        gate_status="pass",
    )


def test_valid_paper_decision_uses_entry_policy() -> None:
    result = paper_decision_from_signal(make_signal(probability=0.7, confidence=0.8), PaperBridgeContext(market_price=0.6, spread=0.02, depth_usd=500.0))
    assert result.decision.enter is True
    assert result.decision.action == "paper_trade_small"
    assert result.paper_only is True
    assert result.trading_action == "none"
    assert result.to_dict()["trading_action"] == "none"


def test_skip_on_low_confidence() -> None:
    result = paper_decision_from_signal(make_signal(confidence=0.2), PaperBridgeContext(market_price=0.6, spread=0.02, depth_usd=500.0))
    assert result.decision.enter is False
    assert "confidence_below_threshold" in result.decision.blocked_by


def test_skip_on_wide_spread() -> None:
    result = paper_decision_from_signal(make_signal(), PaperBridgeContext(market_price=0.6, spread=0.2, depth_usd=500.0))
    assert result.decision.enter is False
    assert "spread_too_wide" in result.decision.blocked_by


def test_skip_on_non_probability_crowd_flow_signal() -> None:
    result = paper_decision_from_signal(make_signal(probability=None, target=StrategyTarget.CROWD_MOVEMENT_FORECASTING), PaperBridgeContext(market_price=0.6, spread=0.02, depth_usd=500.0))
    assert result.decision.enter is False
    assert result.decision.blocked_by == ["non_probability_signal"]


def test_live_mode_rejection() -> None:
    with pytest.raises(ValueError, match="live_allowed"):
        paper_decision_from_signal(make_signal(mode=StrategyMode.LIVE_ALLOWED), PaperBridgeContext(market_price=0.6, spread=0.02, depth_usd=500.0))
