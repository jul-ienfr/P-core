from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

_CLOB_MARKET_WS_ENDPOINT = "wss://ws-subscriptions-clob.polymarket.com/ws/market"


@dataclass(frozen=True, slots=True)
class WeatherModelRun:
    model: str
    market_id: str
    forecast_yes_probability: float
    published_at: str


@dataclass(frozen=True, slots=True)
class WeatherPriceSnapshot:
    market_id: str
    yes_best_ask: float
    yes_best_bid: float
    observed_at: str


def clob_websocket_subscription(token_ids: Iterable[str]) -> dict[str, Any]:
    return {
        "endpoint": _CLOB_MARKET_WS_ENDPOINT,
        "auth_required": False,
        "message": {"type": "market", "assets_ids": list(token_ids)},
        "tracks": ["orderbook_diffs", "new_orders", "cancellations", "fills"],
    }


def model_update_schedule_hours() -> dict[str, int]:
    return {"HRRR": 1, "GFS": 6, "ECMWF": 12}


def build_weather_latency_signal(
    *,
    run: WeatherModelRun,
    price: WeatherPriceSnapshot,
    min_edge: float,
) -> dict[str, Any]:
    if run.market_id != price.market_id:
        raise ValueError("model run and price snapshot must target the same market_id")

    yes_edge = round(run.forecast_yes_probability - price.yes_best_ask, 10)
    no_probability = 1.0 - run.forecast_yes_probability
    no_best_ask = 1.0 - price.yes_best_bid
    no_edge = round(no_probability - no_best_ask, 10)

    if yes_edge >= min_edge:
        return _signal(run=run, action="enter_yes", edge=yes_edge, max_entry_price=round(run.forecast_yes_probability - min_edge, 10))
    if no_edge >= min_edge:
        return _signal(run=run, action="enter_no", edge=no_edge, max_entry_price=round(no_probability - min_edge, 10))
    return _signal(run=run, action="hold", edge=max(yes_edge, no_edge), max_entry_price=None)


def _signal(*, run: WeatherModelRun, action: str, edge: float, max_entry_price: float | None) -> dict[str, Any]:
    return {
        "market_id": run.market_id,
        "model": run.model,
        "action": action,
        "edge": round(edge, 4),
        "max_entry_price": max_entry_price,
        "latency_thesis": "fresh_weather_model_before_market_reprice",
        "source": "weather_model_run_plus_clob_websocket",
    }
