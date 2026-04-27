from __future__ import annotations

from datetime import UTC, datetime

from prediction_core.strategies import StrategyMode, StrategySide, StrategySignal, StrategyTarget
from prediction_core.strategies.bookmaker_bridge import run_bookmaker_from_signals, signal_to_bookmaker_input


def signal(strategy_id: str, probability: float | None, target: StrategyTarget = StrategyTarget.EVENT_OUTCOME_FORECASTING, *, weight: float = 1.0, side: StrategySide = StrategySide.YES) -> StrategySignal:
    return StrategySignal(
        strategy_id=strategy_id,
        market_id="m",
        target=target,
        mode=StrategyMode.RESEARCH_ONLY,
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
        side=side,
        probability=probability,
        confidence=min(weight, 1.0),
        features={},
        risks=[],
        source={},
        metadata={"bookmaker_weight": weight},
        gate_status="pass",
    )


def test_weighted_average_from_compatible_signals() -> None:
    result = run_bookmaker_from_signals([signal("a", 0.6, weight=1.0), signal("b", 0.8, weight=3.0)], market_id="m", generated_at=datetime(2026, 1, 1, tzinfo=UTC))
    assert result.output is not None
    assert result.output.probability_yes == 0.75
    assert result.output.research_only is True
    assert result.output.paper_only is True
    assert result.output.trading_action == "none"
    assert result.output.contributing_agents == ["a", "b"]


def test_incompatible_target_excluded_without_affecting_probability() -> None:
    result = run_bookmaker_from_signals([
        signal("event", 0.6),
        signal("crowd", None, StrategyTarget.CROWD_MOVEMENT_FORECASTING),
    ], market_id="m")
    assert result.output is not None
    assert result.output.probability_yes == 0.6
    assert result.excluded == [{"strategy_id": "crowd", "reason": "incompatible_target", "target": "crowd_movement_forecasting"}]


def test_unknown_skip_and_missing_probability_excluded_with_reasons() -> None:
    missing = signal("missing", None)
    skip = signal("skip", 0.5, side=StrategySide.SKIP)
    assert signal_to_bookmaker_input(missing)[1]["reason"] == "missing_probability"
    assert signal_to_bookmaker_input(skip)[1]["reason"] == "unknown_or_skip_signal"


def test_bridge_result_invariants_when_no_inputs() -> None:
    result = run_bookmaker_from_signals([signal("crowd", None, StrategyTarget.CROWD_MOVEMENT_FORECASTING)], market_id="m")
    assert result.output is None
    assert result.research_only is True
    assert result.paper_only is True
    assert result.trading_action == "none"
