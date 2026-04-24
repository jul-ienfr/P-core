from __future__ import annotations

from copy import deepcopy
from typing import Any

_VALID_SOURCES = {"fixture", "live"}

_FIXTURE_MARKETS: list[dict[str, Any]] = [
    {
        "id": "denver-high-64",
        "category": "weather",
        "question": "Will the highest temperature in Denver be 64F or higher?",
        "yes_price": 0.43,
        "best_bid": 0.42,
        "best_ask": 0.45,
        "volume": 14000,
        "hours_to_resolution": 18,
        "resolution_source": "Resolution source: NOAA daily climate report for station KDEN",
        "description": "Official observed high temperature at Denver International Airport station KDEN.",
        "rules": "Source: https://www.weather.gov/wrh/climate?wfo=bou station KDEN.",
    },
    {
        "id": "denver-high-65",
        "category": "weather",
        "question": "Will the highest temperature in Denver be 65F or higher?",
        "yes_price": 0.37,
        "best_bid": 0.35,
        "best_ask": 0.39,
        "volume": 9800,
        "hours_to_resolution": 18,
        "resolution_source": "Resolution source: NOAA daily climate report for station KDEN",
        "description": "Official observed high temperature at Denver International Airport station KDEN.",
        "rules": "Source: https://www.weather.gov/wrh/climate?wfo=bou station KDEN.",
    },
    {
        "id": "denver-bin-64-65",
        "category": "weather",
        "question": "Will the highest temperature in Denver be between 64F and 65F?",
        "yes_price": 0.17,
        "best_bid": 0.15,
        "best_ask": 0.19,
        "volume": 6200,
        "hours_to_resolution": 18,
        "resolution_source": "Resolution source: NOAA daily climate report for station KDEN",
        "description": "Official observed high temperature at Denver International Airport station KDEN.",
        "rules": "Source: https://www.weather.gov/wrh/climate?wfo=bou station KDEN.",
    },
    {
        "id": "politics-fixture-ignore",
        "category": "politics",
        "question": "Will candidate X win state Y?",
        "yes_price": 0.51,
        "best_bid": 0.50,
        "best_ask": 0.52,
        "volume": 50000,
        "hours_to_resolution": 72,
    },
]

_FIXTURE_EVENT_BOOKS: dict[str, dict[str, Any]] = {
    "denver-daily-highs": {
        "id": "denver-daily-highs",
        "category": "weather",
        "question": "Denver daily highest temperature event",
        "description": "Fixture event grouping Denver daily highest temperature markets.",
        "resolution_source": "Resolution source: NOAA daily climate report for station KDEN",
        "rules": "Source: https://www.weather.gov/wrh/climate?wfo=bou station KDEN.",
        "markets": ["denver-high-64", "denver-high-65", "denver-bin-64-65"],
    }
}


def list_fixture_weather_markets() -> list[dict[str, Any]]:
    return [deepcopy(market) for market in _FIXTURE_MARKETS if market.get("category") == "weather"]


def get_fixture_market_by_id(market_id: str) -> dict[str, Any]:
    for market in _FIXTURE_MARKETS:
        if market.get("id") == market_id:
            return deepcopy(market)
    raise KeyError(f"Unknown fixture market id: {market_id}")


def get_fixture_event_book_by_id(event_id: str) -> dict[str, Any]:
    raw_event = _FIXTURE_EVENT_BOOKS.get(event_id)
    if raw_event is None:
        raise KeyError(f"Unknown fixture event id: {event_id}")

    event = deepcopy(raw_event)
    event["markets"] = [get_fixture_market_by_id(market_id) for market_id in raw_event.get("markets", [])]
    return event


def list_weather_markets(source: str = "fixture", limit: int = 100) -> list[dict[str, Any]]:
    resolved_source = _validate_source(source)
    if resolved_source == "fixture":
        return list_fixture_weather_markets()

    live_module = _load_live_module()
    return live_module.list_live_weather_markets(limit=limit)


def get_market_by_id(market_id: str, source: str = "fixture") -> dict[str, Any]:
    resolved_source = _validate_source(source)
    if resolved_source == "fixture":
        return get_fixture_market_by_id(market_id)

    live_module = _load_live_module()
    return live_module.get_live_market_by_id(market_id)


def get_event_book_by_id(event_id: str, source: str = "fixture") -> dict[str, Any]:
    resolved_source = _validate_source(source)
    if resolved_source == "fixture":
        return get_fixture_event_book_by_id(event_id)

    live_module = _load_live_module()
    return live_module.get_live_event_book_by_id(event_id)


def normalize_market_record(raw: dict[str, Any]) -> dict[str, Any]:
    best_bid = _as_float(raw.get("best_bid"))
    best_ask = _as_float(raw.get("best_ask"))
    spread = round(max(best_ask - best_bid, 0.0), 2)
    volume_usd = _as_float(raw.get("volume"))
    return {
        "id": str(raw.get("id", "")),
        "category": str(raw.get("category", "unknown")),
        "question": str(raw.get("question", "")),
        "yes_price": _as_float(raw.get("yes_price")),
        "best_bid": best_bid,
        "best_ask": best_ask,
        "spread": spread,
        "volume_usd": volume_usd,
        "hours_to_resolution": _as_float(raw.get("hours_to_resolution")),
        "max_impact_bps": _as_float(raw.get("max_impact_bps")) or 150.0,
        "resolution_source": raw.get("resolution_source"),
        "description": raw.get("description"),
        "rules": raw.get("rules"),
    }


def _validate_source(source: str) -> str:
    resolved_source = str(source).strip().lower() or "fixture"
    if resolved_source not in _VALID_SOURCES:
        supported = ", ".join(sorted(_VALID_SOURCES))
        raise ValueError(f"Unsupported source '{source}'. Expected one of: {supported}")
    return resolved_source


def _load_live_module() -> Any:
    from weather_pm import polymarket_live

    return polymarket_live


def _as_float(value: Any) -> float:
    if value is None:
        return 0.0
    return float(value)
