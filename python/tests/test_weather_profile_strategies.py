from __future__ import annotations

import pytest

from weather_pm.strategy_profiles import get_strategy_profile

from prediction_core.strategies.contracts import StrategyMode, StrategyRunRequest, StrategyTarget
from prediction_core.strategies.weather_profile_strategies import WeatherProfileStrategy, build_weather_profile_strategies


EXPECTED_PROFILE_IDS = [
    "surface_grid_trader",
    "exact_bin_anomaly_hunter",
    "threshold_resolution_harvester",
    "profitable_consensus_radar",
    "conviction_signal_follower",
    "macro_weather_event_trader",
]


def test_build_weather_profile_strategies_preserves_canonical_order() -> None:
    strategies = build_weather_profile_strategies()

    assert [strategy.descriptor.strategy_id for strategy in strategies] == EXPECTED_PROFILE_IDS


def test_weather_profile_strategy_emits_safe_signal() -> None:
    strategy = WeatherProfileStrategy(
        "surface_grid_trader",
        payloads=[
            {
                "market_id": "fixture-surface",
                "probability_yes": 0.58,
                "confidence": 0.64,
                "edge": 0.04,
                "action": "paper_probe",
                "satisfied_gates": ["surface_inconsistency_present", "source_confirmed", "edge_survives_fill", "strict_limit_not_crossed"],
                "source_references": ["fixture://surface"],
            }
        ],
    )

    result = strategy.run(StrategyRunRequest(market_id="fixture"))
    signal = result.signals[0]

    assert signal.trading_action == "none"
    assert signal.mode == StrategyMode.PAPER_ONLY
    assert signal.target == StrategyTarget.EVENT_OUTCOME_FORECASTING
    assert signal.features["profile_id"] == "surface_grid_trader"
    assert signal.source["adapter"] == "weather_profile_strategy"
    assert "paper/research profile adapter; no live execution" in signal.risks


def test_weather_profile_strategy_rejects_live_allowed() -> None:
    with pytest.raises(ValueError, match="paper/research only"):
        WeatherProfileStrategy("surface_grid_trader", mode=StrategyMode.LIVE_ALLOWED)
    with pytest.raises(ValueError, match="paper/research only"):
        WeatherProfileStrategy("surface_grid_trader", mode="live_allowed")
    with pytest.raises(ValueError, match="paper/research only"):
        build_weather_profile_strategies(mode="live_allowed")


@pytest.mark.parametrize("profile_id", EXPECTED_PROFILE_IDS)
def test_weather_profile_strategy_emits_ready_signal_when_all_entry_gates_are_satisfied(profile_id: str) -> None:
    profile = get_strategy_profile(profile_id)
    strategy = WeatherProfileStrategy(
        profile_id,
        payloads=[
            {
                "market_id": f"fixture-{profile_id}",
                "probability_yes": 0.58,
                "confidence": 0.64,
                "edge": 0.04,
                "action": "paper_probe",
                "satisfied_gates": list(profile["entry_gates"]),
            }
        ],
    )

    signal = strategy.run(StrategyRunRequest(market_id="fixture")).signals[0]

    assert signal.gate_status == "fixture_profile_ready"
    assert signal.side.value == "yes"
    assert signal.trading_action == "none"
    assert signal.features["missing_gates"] == []


@pytest.mark.parametrize("profile_id", EXPECTED_PROFILE_IDS)
def test_weather_profile_strategy_requires_all_entry_gates_before_ready_signal(profile_id: str) -> None:
    profile = get_strategy_profile(profile_id)
    satisfied_gates = list(profile["entry_gates"][:-1])
    strategy = WeatherProfileStrategy(
        profile_id,
        payloads=[
            {
                "market_id": f"fixture-{profile_id}",
                "probability_yes": 0.58,
                "confidence": 0.64,
                "edge": 0.04,
                "action": "paper_probe",
                "profile_gate_status": "fixture_profile_ready",
                "satisfied_gates": satisfied_gates,
            }
        ],
    )

    signal = strategy.run(StrategyRunRequest(market_id="fixture")).signals[0]

    assert signal.gate_status == "not_enough_data"
    assert signal.side.value == "skip"
    assert signal.features["missing_gates"] == [profile["entry_gates"][-1]]
