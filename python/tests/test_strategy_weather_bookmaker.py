from __future__ import annotations

from prediction_core.strategies import StrategyMode, StrategyRunRequest, StrategySide, StrategyTarget
from prediction_core.strategies.weather_bookmaker import WeatherBookmakerStrategy, build_weather_bookmaker_signal


def aligned_payload() -> dict:
    return {
        "market_id": "weather-shanghai-23c-no",
        "market_price": 0.61,
        "weather": {"probability_yes": 0.73, "confidence": 0.82, "edge": 0.12},
        "profitable_wallets": {"matched_count": 3, "alignment": "yes", "confidence": 0.7},
        "event_surface": {"inconsistency_count": 2, "consistent": True},
        "execution": {"spread": 0.02, "depth_usd": 450.0, "fillable_size_usd": 120.0, "best_effort_reason": None},
        "resolution": {"source_direct": True, "provider": "wunderground", "station_code": "ZSPD"},
    }


def test_weather_bookmaker_emits_paper_add_when_signals_align() -> None:
    signal = build_weather_bookmaker_signal(aligned_payload())

    assert signal.strategy_id == "weather_bookmaker_v1"
    assert signal.market_id == "weather-shanghai-23c-no"
    assert signal.mode == StrategyMode.PAPER_ONLY
    assert signal.target == StrategyTarget.EVENT_OUTCOME_FORECASTING
    assert signal.side == StrategySide.YES
    assert signal.probability == 0.73
    assert signal.confidence >= 0.75
    assert signal.expected_move == 0.12
    assert signal.gate_status == "paper_add"
    assert signal.trading_action == "none"
    assert signal.features["decision"] == "PAPER_ADD"
    assert "forecast_edge_positive" in signal.features["reasons"]
    assert "profitable_wallet_alignment" in signal.features["reasons"]
    assert "direct_resolution_source" in signal.features["reasons"]
    assert "execution_depth_ok" in signal.features["reasons"]
    assert signal.features["paper_only"] is True


def test_weather_bookmaker_skips_when_execution_is_blocked() -> None:
    payload = aligned_payload()
    payload["execution"] = {"spread": 0.2, "depth_usd": 5.0, "fillable_size_usd": 0.0, "best_effort_reason": "missing_tradeable_quote"}

    signal = build_weather_bookmaker_signal(payload)

    assert signal.side == StrategySide.SKIP
    assert signal.gate_status == "skip"
    assert signal.features["decision"] == "SKIP"
    assert "missing_tradeable_quote" in signal.features["blockers"]
    assert signal.trading_action == "none"


def test_weather_bookmaker_uses_probe_when_forecast_edge_has_no_confirming_wallets_or_surface() -> None:
    payload = aligned_payload()
    payload["profitable_wallets"] = {"matched_count": 0, "alignment": "none"}
    payload["event_surface"] = {"inconsistency_count": 0, "consistent": True}

    signal = build_weather_bookmaker_signal(payload)

    assert signal.side == StrategySide.YES
    assert signal.gate_status == "paper_probe"
    assert signal.features["decision"] == "PAPER_PROBE"
    assert "forecast_edge_positive" in signal.features["reasons"]
    assert "profitable_wallet_alignment" not in signal.features["reasons"]
    assert "surface_anomaly_support" not in signal.features["reasons"]


def test_weather_bookmaker_strategy_runs_payloads_paper_only_without_network() -> None:
    strategy = WeatherBookmakerStrategy(payloads=[aligned_payload()])
    result = strategy.run(StrategyRunRequest(market_id="weather-shanghai-23c-no"))

    assert result.strategy_id == "weather_bookmaker_v1"
    assert result.mode == StrategyMode.PAPER_ONLY
    assert result.errors == []
    assert len(result.signals) == 1
    assert result.signals[0].features["decision"] == "PAPER_ADD"
