from __future__ import annotations

from prediction_core.strategies import StrategyMode, StrategyRunRequest, StrategySide, StrategyTarget
from prediction_core.strategies.weather_baseline import WeatherBaselineStrategy, weather_signal_from_payload


def test_weather_payload_adapts_to_event_signal() -> None:
    payload = {
        "market_id": "weather-nyc-rain",
        "score": {"probability_yes": 0.64, "confidence": 0.78, "edge": 0.09, "model": "fixture"},
        "decision": {"action": "paper_trade_small", "execution_caveats": ["paper only"], "gate_status": "pass"},
        "source_references": ["fixture://weather"],
        "generated_at": "2026-01-01T00:00:00Z",
    }
    signal = weather_signal_from_payload(payload)
    assert signal.target == StrategyTarget.EVENT_OUTCOME_FORECASTING
    assert signal.mode == StrategyMode.PAPER_ONLY
    assert signal.market_id == "weather-nyc-rain"
    assert signal.probability == 0.64
    assert signal.confidence == 0.78
    assert signal.expected_move == 0.09
    assert signal.features["edge"] == 0.09
    assert signal.features["execution_caveats"] == ["paper only"]
    assert signal.source["references"] == ["fixture://weather"]
    assert signal.trading_action == "none"


def test_weather_skip_case_remains_no_action_signal() -> None:
    signal = weather_signal_from_payload(
        {
            "market_id": "m",
            "score": {"forecast_probability": 0.51, "confidence": 0.3},
            "decision": {"action": "skip", "execution_caveats": "low confidence"},
        }
    )
    assert signal.side == StrategySide.SKIP
    assert signal.gate_status == "skip"
    assert signal.trading_action == "none"
    assert "low confidence" in signal.risks


def test_weather_strategy_uses_supplied_fixtures_without_network() -> None:
    strategy = WeatherBaselineStrategy(payloads=[{"market_id": "m", "score": {"probability_yes": 0.6, "confidence": 0.7}}])
    result = strategy.run(StrategyRunRequest(market_id="m"))
    assert result.errors == []
    assert len(result.signals) == 1
    assert result.signals[0].source["adapter"] == "weather_baseline"
