from __future__ import annotations

import pytest

from prediction_core.strategies import StrategyMode, StrategyRunRequest, StrategySide, StrategyTarget
from prediction_core.strategies.panoptique_shadow_flow import PanoptiqueShadowFlowStrategy, panoptique_signal_from_record


def test_not_enough_data_becomes_valid_skip_signal() -> None:
    signal = panoptique_signal_from_record({"market_id": "m", "status": "not_enough_data", "confidence": 0.0})
    assert signal.target == StrategyTarget.CROWD_MOVEMENT_FORECASTING
    assert signal.side == StrategySide.SKIP
    assert signal.gate_status == "not_enough_data"
    assert signal.probability is None
    assert signal.trading_action == "none"


@pytest.mark.parametrize(("direction", "side"), [("up", StrategySide.UP), ("down", StrategySide.DOWN), ("unknown", StrategySide.UNKNOWN)])
def test_crowd_directions_and_confidence_propagate(direction: str, side: StrategySide) -> None:
    signal = panoptique_signal_from_record(
        {
            "market_id": "m",
            "predicted_crowd_direction": direction,
            "confidence": 0.83,
            "expected_crowd_move": 0.07,
            "archetype": "burst",
            "window": "15m",
            "observed_count": 12,
            "matched_count": 8,
        }
    )
    assert signal.side == side
    assert signal.confidence == 0.83
    assert signal.features["archetype"] == "burst"
    assert signal.features["window"] == "15m"
    assert signal.features["expected_move"] == 0.07
    assert signal.features["observed_count"] == 12
    assert signal.features["matched_count"] == 8


def test_strategy_uses_supplied_records_without_db() -> None:
    strategy = PanoptiqueShadowFlowStrategy(records=[{"market_id": "m", "predicted_crowd_direction": "up", "confidence": 0.7}])
    result = strategy.run(StrategyRunRequest(market_id="m"))
    assert result.errors == []
    assert len(result.signals) == 1
    assert result.signals[0].mode == StrategyMode.RESEARCH_ONLY


def test_live_mode_rejected_for_panoptique_adapter() -> None:
    with pytest.raises(ValueError, match="research/paper"):
        PanoptiqueShadowFlowStrategy(mode=StrategyMode.LIVE_ALLOWED)
