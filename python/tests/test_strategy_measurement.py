from __future__ import annotations

from datetime import UTC, datetime

from prediction_core.strategies import StrategyMode, StrategySignal, StrategyTarget
from prediction_core.strategies.measurement import group_signals_for_read_model, project_strategy_metrics


def sig(strategy_id: str, target: StrategyTarget, *, probability: float | None = None, expected_move: float | None = None) -> StrategySignal:
    return StrategySignal(
        strategy_id=strategy_id,
        market_id="m",
        target=target,
        mode=StrategyMode.RESEARCH_ONLY,
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
        probability=probability,
        confidence=0.8,
        expected_move=expected_move,
        features={},
        risks=[],
        source={},
        gate_status="pass",
    )


def test_metrics_keep_event_and_crowd_targets_separate() -> None:
    snapshots = project_strategy_metrics(
        [
            sig("weather", StrategyTarget.EVENT_OUTCOME_FORECASTING, probability=0.6),
            sig("weather", StrategyTarget.EVENT_OUTCOME_FORECASTING, probability=0.7),
            sig("pan", StrategyTarget.CROWD_MOVEMENT_FORECASTING, expected_move=0.05),
            sig("pan", StrategyTarget.CROWD_MOVEMENT_FORECASTING, expected_move=0.07),
        ]
    )
    targets = {snapshot.target for snapshot in snapshots}
    assert targets == {StrategyTarget.EVENT_OUTCOME_FORECASTING, StrategyTarget.CROWD_MOVEMENT_FORECASTING}
    event = next(s for s in snapshots if s.target == StrategyTarget.EVENT_OUTCOME_FORECASTING)
    crowd = next(s for s in snapshots if s.target == StrategyTarget.CROWD_MOVEMENT_FORECASTING)
    assert event.probability_count == 2
    assert crowd.probability_count == 0
    assert crowd.average_expected_move == 0.06


def test_small_sample_returns_not_enough_data() -> None:
    snapshot = project_strategy_metrics([sig("weather", StrategyTarget.EVENT_OUTCOME_FORECASTING, probability=0.6)])[0]
    assert snapshot.gate_status == "not_enough_data"
    assert snapshot.metadata["sample_state"] == "not_enough_data"


def test_dashboard_read_model_and_execution_edge_metadata() -> None:
    read_model = group_signals_for_read_model([
        sig("edge", StrategyTarget.EXECUTABLE_EDGE_AFTER_COSTS, probability=0.55, expected_move=0.02),
        sig("edge", StrategyTarget.EXECUTABLE_EDGE_AFTER_COSTS, probability=0.56, expected_move=0.03),
    ])
    assert read_model["strategy_count"] == 1
    assert read_model["targets"] == ["executable_edge_after_costs"]
    assert read_model["snapshots"][0]["metadata"]["execution_edge_reported_separately"] is True
