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
    bid_levels = _normalized_book_levels(raw.get("bid_levels") or raw.get("bids"))
    ask_levels = _normalized_book_levels(raw.get("ask_levels") or raw.get("asks"))
    if not bid_levels and best_bid > 0.0:
        best_bid_size = _as_float(raw.get("best_bid_size"))
        if best_bid_size > 0.0:
            bid_levels = [{"price": best_bid, "size": best_bid_size}]
    if not ask_levels and best_ask > 0.0:
        best_ask_size = _as_float(raw.get("best_ask_size"))
        if best_ask_size > 0.0:
            ask_levels = [{"price": best_ask, "size": best_ask_size}]
    book_depth_source = str(raw.get("book_depth_source") or ("clob_book" if bid_levels or ask_levels else "top_of_book_unavailable"))
    if book_depth_source == "clob_book" and not _has_full_book_depth(raw) and (bid_levels or ask_levels):
        book_depth_source = "top_of_book_fallback"
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
        "bid_levels": bid_levels,
        "ask_levels": ask_levels,
        "bids": bid_levels,
        "asks": ask_levels,
        "book_depth_source": book_depth_source,
        "resolution_source": raw.get("resolution_source"),
        "description": raw.get("description"),
        "rules": raw.get("rules"),
    }


def _has_full_book_depth(raw: dict[str, Any]) -> bool:
    return bool(_normalized_book_levels(raw.get("bid_levels") or raw.get("bids")) or _normalized_book_levels(raw.get("ask_levels") or raw.get("asks")))


def _normalized_book_levels(levels: Any) -> list[dict[str, float]]:
    if not isinstance(levels, list):
        return []
    normalized: list[dict[str, float]] = []
    for level in levels:
        if not isinstance(level, dict):
            continue
        price = _as_float(level.get("price"))
        size = _as_float(level.get("size", level.get("quantity")))
        if price <= 0.0 or size <= 0.0:
            continue
        normalized.append({"price": price, "size": size})
    return normalized


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
