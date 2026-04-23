from __future__ import annotations

from weather_pm import polymarket_client
from weather_pm.polymarket_client import (
    get_event_book_by_id,
    get_market_by_id,
    list_fixture_weather_markets,
    list_weather_markets,
    normalize_market_record,
)
from weather_pm.polymarket_live import _normalize_gamma_series_event



def test_list_fixture_weather_markets_returns_only_weather_markets() -> None:
    markets = list_fixture_weather_markets()

    assert len(markets) >= 3
    assert all(market["category"] == "weather" for market in markets)
    assert {market["id"] for market in markets} >= {"denver-high-64", "denver-high-65", "denver-bin-64-65"}


def test_normalize_market_record_extracts_expected_fields() -> None:
    raw = {
        "id": "denver-high-64",
        "category": "weather",
        "question": "Will the highest temperature in Denver be 64F or higher?",
        "yes_price": 0.43,
        "best_bid": 0.42,
        "best_ask": 0.45,
        "volume": 14000,
        "hours_to_resolution": 18,
    }

    normalized = normalize_market_record(raw)

    assert normalized["id"] == "denver-high-64"
    assert normalized["question"] == raw["question"]
    assert normalized["yes_price"] == 0.43
    assert normalized["spread"] == 0.03
    assert normalized["volume_usd"] == 14000.0


def test_list_weather_markets_fixture_source_matches_fixture_helper() -> None:
    assert list_weather_markets(source="fixture") == list_fixture_weather_markets()


def test_live_facade_routes_to_live_module() -> None:
    class _LiveModule:
        @staticmethod
        def list_live_weather_markets(limit: int = 100) -> list[dict[str, object]]:
            return [{"id": f"live-{limit}", "category": "weather", "question": "q"}]

        @staticmethod
        def get_live_market_by_id(market_id: str) -> dict[str, object]:
            return {"id": market_id, "category": "weather", "question": "q"}

    original = polymarket_client._load_live_module
    polymarket_client._load_live_module = lambda: _LiveModule
    try:
        assert list_weather_markets(source="live", limit=7) == [{"id": "live-7", "category": "weather", "question": "q"}]
        assert get_market_by_id("live-market-1", source="live") == {
            "id": "live-market-1",
            "category": "weather",
            "question": "q",
        }
    finally:
        polymarket_client._load_live_module = original


def test_get_event_book_by_id_fixture_returns_event_container_with_child_markets() -> None:
    event = get_event_book_by_id("denver-daily-highs", source="fixture")

    assert event["id"] == "denver-daily-highs"
    assert event["category"] == "weather"
    assert "yes_price" not in event
    assert [market["id"] for market in event["markets"]] == ["denver-high-64", "denver-high-65", "denver-bin-64-65"]
    assert event["markets"][0]["yes_price"] == 0.43
    assert event["markets"][0]["best_bid"] == 0.42
    assert event["markets"][0]["best_ask"] == 0.45


def test_get_event_book_by_id_live_routes_to_live_module() -> None:
    class _LiveModule:
        @staticmethod
        def get_live_event_book_by_id(event_id: str) -> dict[str, object]:
            return {"id": event_id, "category": "weather", "markets": [{"id": "m1"}]}

    original = polymarket_client._load_live_module
    polymarket_client._load_live_module = lambda: _LiveModule
    try:
        assert get_event_book_by_id("event-123", source="live") == {
            "id": "event-123",
            "category": "weather",
            "markets": [{"id": "m1"}],
        }
    finally:
        polymarket_client._load_live_module = original


def test_normalize_market_record_preserves_series_event_volume_field_shape() -> None:
    raw = _normalize_gamma_series_event(
        {
            "id": "404359",
            "title": "Lowest temperature in Miami on April 23?",
            "description": "This market will resolve to the temperature range that contains the lowest temperature recorded at the Miami Intl Airport Station in degrees Fahrenheit on 23 Apr '26.",
            "resolutionSource": "https://www.wunderground.com/history/daily/us/fl/miami/KMIA",
            "volume": 13146.135531999998,
            "endDate": "2099-04-23T12:00:00Z",
        }
    )

    normalized = normalize_market_record(raw)

    assert normalized["id"] == "404359"
    assert normalized["question"] == "Lowest temperature in Miami on April 23?"
    assert normalized["spread"] == 0.0
    assert normalized["volume_usd"] == 13146.135531999998
    assert normalized["resolution_source"] == "https://www.wunderground.com/history/daily/us/fl/miami/KMIA"
