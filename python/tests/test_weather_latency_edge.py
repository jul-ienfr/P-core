from __future__ import annotations

from weather_pm.weather_latency_edge import (
    WeatherModelRun,
    WeatherPriceSnapshot,
    build_weather_latency_signal,
    clob_websocket_subscription,
    model_update_schedule_hours,
)


def test_clob_websocket_subscription_uses_polymarket_market_stream_and_token_ids() -> None:
    subscription = clob_websocket_subscription(["yes-token", "no-token"])

    assert subscription["endpoint"] == "wss://ws-subscriptions-clob.polymarket.com/ws/market"
    assert subscription["auth_required"] is False
    assert subscription["message"] == {"type": "market", "assets_ids": ["yes-token", "no-token"]}
    assert subscription["tracks"] == ["orderbook_diffs", "new_orders", "cancellations", "fills"]


def test_model_update_schedule_hours_prioritizes_hrrr_then_gfs_then_ecmwf() -> None:
    assert model_update_schedule_hours() == {"HRRR": 1, "GFS": 6, "ECMWF": 12}


def test_build_weather_latency_signal_flags_entry_window_when_forecast_edge_exceeds_live_price() -> None:
    signal = build_weather_latency_signal(
        run=WeatherModelRun(model="HRRR", market_id="denver-high-64", forecast_yes_probability=0.68, published_at="2026-04-26T08:00:00Z"),
        price=WeatherPriceSnapshot(market_id="denver-high-64", yes_best_ask=0.55, yes_best_bid=0.53, observed_at="2026-04-26T08:01:00Z"),
        min_edge=0.05,
    )

    assert signal == {
        "market_id": "denver-high-64",
        "model": "HRRR",
        "action": "enter_yes",
        "edge": 0.13,
        "max_entry_price": 0.63,
        "latency_thesis": "fresh_weather_model_before_market_reprice",
        "source": "weather_model_run_plus_clob_websocket",
    }
