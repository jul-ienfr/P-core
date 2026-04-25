from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from weather_pm.polymarket_live import (
    _compute_hours_to_resolution,
    _infer_yes_index,
    _looks_like_weather_market,
    _matches_requested_state,
    _normalize_gamma_market,
    _normalize_gamma_series_event,
    _parse_jsonish_list,
    get_live_market_by_id,
    list_live_weather_markets,
)


def _sample_gamma_market(**overrides: object) -> dict[str, object]:
    future_end = (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat()
    payload: dict[str, object] = {
        "id": "gamma-weather-1",
        "question": "Will the highest temperature in Denver be 64F or higher?",
        "category": None,
        "description": "Official observed high temperature for Denver.",
        "rules": "Source: NOAA climate report for station KDEN.",
        "resolutionSource": "NOAA daily climate report",
        "outcomes": '["Yes", "No"]',
        "outcomePrices": '["0.44", "0.56"]',
        "bestBids": '["0.43", "0.55"]',
        "bestAsks": '["0.45", "0.57"]',
        "volume": "12345.6",
        "endDate": future_end,
    }
    payload.update(overrides)
    return payload


def test_parse_jsonish_list_handles_json_string_native_list_and_nullish_values() -> None:
    assert _parse_jsonish_list('["Yes", "No"]') == ["Yes", "No"]
    assert _parse_jsonish_list(["Yes", "No"]) == ["Yes", "No"]
    assert _parse_jsonish_list(None) == []
    assert _parse_jsonish_list("null") == []


def test_infer_yes_index_prefers_explicit_yes_and_falls_back_from_no() -> None:
    assert _infer_yes_index({"outcomes": '["No", "Yes"]'}) == 1
    assert _infer_yes_index({"outcomes": '["NO", "MAYBE"]'}) == 1


def test_compute_hours_to_resolution_returns_reasonable_future_delta() -> None:
    raw = {"endDate": (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat()}

    hours = _compute_hours_to_resolution(raw)

    assert hours is not None
    assert math.isfinite(hours)
    assert 5.5 <= hours <= 6.5


def test_looks_like_weather_market_accepts_supported_weather_question_with_null_category() -> None:
    assert _looks_like_weather_market(_sample_gamma_market()) is True


def test_normalize_gamma_market_maps_representative_gamma_payload_to_pipeline_shape() -> None:
    normalized = _normalize_gamma_market(_sample_gamma_market())

    assert normalized["id"] == "gamma-weather-1"
    assert normalized["category"] == "weather"
    assert normalized["question"] == "Will the highest temperature in Denver be 64F or higher?"
    assert normalized["yes_price"] == 0.44
    assert normalized["best_bid"] == 0.43
    assert normalized["best_ask"] == 0.45
    assert normalized["volume"] == 12345.6
    assert normalized["resolution_source"] == "NOAA daily climate report"
    assert normalized["description"] == "Official observed high temperature for Denver."
    assert normalized["rules"] == "Source: NOAA climate report for station KDEN."
    assert normalized["hours_to_resolution"] is not None


def test_normalize_gamma_market_uses_gamma_quote_when_clob_yes_book_has_only_expensive_asks() -> None:
    from weather_pm import polymarket_live

    original_fetch_clob_book = polymarket_live._fetch_clob_book
    polymarket_live._fetch_clob_book = lambda token_id: {
        "bids": [],
        "asks": [{"price": "0.999", "size": "2243.99"}],
    }
    try:
        normalized = _normalize_gamma_market(
            _sample_gamma_market(
                id="dallas-low-quote",
                question="Will the highest temperature in Dallas be 67°F or below on April 26?",
                outcomePrices='["0.001", "0.999"]',
                bestBids=None,
                bestAsks=None,
                bestBid=None,
                bestAsk="0.002",
                clobTokenIds='["yes-token", "no-token"]',
            )
        )
    finally:
        polymarket_live._fetch_clob_book = original_fetch_clob_book

    assert normalized["yes_price"] == 0.001
    assert normalized["best_bid"] == 0.0
    assert normalized["best_ask"] == 0.002
    assert normalized["book_depth_source"] == "clob_book"
    assert normalized["asks"] == [{"price": 0.999, "size": 2243.99}]


def test_normalize_gamma_market_falls_back_to_description_when_live_market_lacks_resolution_source_and_rules() -> None:
    normalized = _normalize_gamma_market(
        _sample_gamma_market(
            description="Gamma market description with embedded resolution guidance.",
            rules=None,
            resolutionSource=None,
        )
    )

    assert normalized["description"] == "Gamma market description with embedded resolution guidance."
    assert normalized["rules"] == "Gamma market description with embedded resolution guidance."
    assert normalized["resolution_source"] == "Gamma market description with embedded resolution guidance."


def test_matches_requested_state_rejects_closed_or_archived_events_for_open_scan() -> None:
    assert _matches_requested_state({"active": True, "closed": False, "archived": False}, active=True, closed=False) is True
    assert _matches_requested_state({"active": True, "closed": True, "archived": False}, active=True, closed=False) is False
    assert _matches_requested_state({"active": True, "closed": False, "archived": True}, active=True, closed=False) is False
    assert _matches_requested_state({"active": False, "closed": False, "archived": False}, active=True, closed=False) is False


def test_normalize_gamma_series_event_maps_weather_event_to_pipeline_shape() -> None:
    raw = {
        "id": "376652",
        "title": "Lowest temperature in Tokyo on April 15?",
        "description": "This market will resolve to the temperature range that contains the lowest temperature recorded at the Tokyo Haneda Airport Station in degrees Celsius on 15 Apr '26.",
        "resolutionSource": "https://www.wunderground.com/history/daily/jp/tokyo/RJTT",
        "volume": 82853.23,
        "openInterest": 29936.44,
        "endDate": "2026-04-16T12:00:00Z",
        "seriesSlug": "tokyo-daily-lowest-temperature",
        "tags": [
            {"label": "Weather", "slug": "weather"},
            {"label": "Lowest temperature", "slug": "lowest-temperature"},
        ],
    }

    normalized = _normalize_gamma_series_event(raw)

    assert normalized["id"] == "376652"
    assert normalized["category"] == "weather"
    assert normalized["question"] == "Lowest temperature in Tokyo on April 15?"
    assert normalized["yes_price"] == 0.0
    assert normalized["best_bid"] == 0.0
    assert normalized["best_ask"] == 0.0
    assert normalized["volume"] == 82853.23
    assert normalized["resolution_source"] == "https://www.wunderground.com/history/daily/jp/tokyo/RJTT"
    assert normalized["description"].startswith("This market will resolve to the temperature range")
    assert normalized["rules"] == normalized["description"]
    assert normalized["hours_to_resolution"] is not None


def test_get_live_market_by_id_falls_back_to_highest_temperature_event_payload_when_market_endpoint_404s() -> None:
    event_payload = {
        "id": "322442",
        "title": "Highest temperature in Hong Kong on April 1?",
        "description": "This market will resolve to the temperature range that contains the highest temperature recorded by the Hong Kong Observatory in degrees Celsius on 1 Apr '26.",
        "resolutionSource": "https://www.weather.gov.hk/en/cis/climat.htm",
        "volume": 221180.29265700004,
        "endDate": "2099-04-01T12:00:00Z",
    }

    from weather_pm import polymarket_live

    original_fetch_market = polymarket_live._fetch_gamma_market
    original_fetch_json = polymarket_live._fetch_gamma_json
    polymarket_live._fetch_gamma_market = lambda market_id: (_ for _ in ()).throw(RuntimeError("Gamma request failed with HTTP 404 for https://gamma-api.polymarket.com/markets/322442: {\"type\":\"not found error\"}"))
    polymarket_live._fetch_gamma_json = lambda path, params=None: event_payload if path == "/events/322442" else (_ for _ in ()).throw(AssertionError(path))
    try:
        normalized = get_live_market_by_id("322442")
    finally:
        polymarket_live._fetch_gamma_market = original_fetch_market
        polymarket_live._fetch_gamma_json = original_fetch_json

    assert normalized["id"] == "322442"
    assert normalized["question"] == "Highest temperature in Hong Kong on April 1?"
    assert normalized["resolution_source"] == "https://www.weather.gov.hk/en/cis/climat.htm"
    assert normalized["best_bid"] == 0.0
    assert normalized["best_ask"] == 0.0
    assert normalized["yes_price"] == 0.0


def test_get_live_event_book_by_id_inherits_weather_context_for_sparse_child_markets() -> None:
    event_payload = {
        "id": "404359",
        "title": "Lowest temperature in Miami on April 23?",
        "description": "This market will resolve to the temperature range that contains the lowest temperature recorded at the Miami Intl Airport Station in degrees Fahrenheit on 23 Apr '26.",
        "resolutionSource": "https://www.wunderground.com/history/daily/us/fl/miami/KMIA",
        "rules": "This market resolves based on the finalized Wunderground observation.",
        "markets": [
            {
                "id": "2047576",
                "question": "Will the lowest temperature in Miami be 63°F or below on April 23?",
                "outcomes": '["Yes", "No"]',
                "outcomePrices": '["0.12", "0.88"]',
                "bestBids": '["0.11", "0.87"]',
                "bestAsks": '["0.13", "0.89"]',
                "volume": "100.0",
                "endDate": "2099-04-23T12:00:00Z",
                "active": True,
                "closed": False,
                "archived": False,
            }
        ],
    }

    from weather_pm import polymarket_live

    original_fetch_json = polymarket_live._fetch_gamma_json
    polymarket_live._fetch_gamma_json = lambda path, params=None: event_payload if path == "/events/404359" else (_ for _ in ()).throw(AssertionError(path))
    try:
        event = polymarket_live.get_live_event_book_by_id("404359")
    finally:
        polymarket_live._fetch_gamma_json = original_fetch_json

    assert event["id"] == "404359"
    assert [market["id"] for market in event["markets"]] == ["2047576"]
    assert event["markets"][0]["question"] == "Will the lowest temperature in Miami be 63°F or below on April 23?"
    assert event["markets"][0]["resolution_source"] == "https://www.wunderground.com/history/daily/us/fl/miami/KMIA"
    assert event["markets"][0]["rules"] == "This market resolves based on the finalized Wunderground observation."
    assert event["markets"][0]["yes_price"] == 0.12



def test_get_live_event_book_by_id_inherits_derived_event_resolution_text_for_sparse_hong_kong_child_markets() -> None:
    event_payload = {
        "id": "322442",
        "title": "Highest temperature in Hong Kong on April 1?",
        "description": (
            "This market will resolve to the temperature range that contains the highest "
            "temperature recorded by the Hong Kong Observatory in degrees Celsius on 1 Apr '26.'"
        ),
        "markets": [
            {
                "id": "1779986",
                "question": "Will the highest temperature in Hong Kong be 20°C or below on April 1?",
                "outcomes": '["Yes", "No"]',
                "outcomePrices": '["0.00", "1.00"]',
                "bestBids": '["0.00", "0.99"]',
                "bestAsks": '["0.001", "1.00"]',
                "volume": "16763.62071",
                "endDate": "2099-04-01T12:00:00Z",
                "active": True,
                "closed": False,
                "archived": False,
            }
        ],
    }

    from weather_pm import polymarket_live

    original_fetch_json = polymarket_live._fetch_gamma_json
    polymarket_live._fetch_gamma_json = lambda path, params=None: event_payload if path == "/events/322442" else (_ for _ in ()).throw(AssertionError(path))
    try:
        event = polymarket_live.get_live_event_book_by_id("322442")
    finally:
        polymarket_live._fetch_gamma_json = original_fetch_json

    assert event["id"] == "322442"
    assert [market["id"] for market in event["markets"]] == ["1779986"]
    assert event["resolution_source"] == event_payload["description"]
    assert event["rules"] == event_payload["description"]
    assert event["markets"][0]["description"] == event_payload["description"]
    assert event["markets"][0]["resolution_source"] == event_payload["description"]
    assert event["markets"][0]["rules"] == event_payload["description"]
    assert event["markets"][0]["best_ask"] == 0.001
    assert event["markets"][0]["yes_price"] == 0.0


def test_get_live_event_book_by_id_returns_event_container_with_child_markets() -> None:
    event_payload = {
        "id": "event-404359",
        "title": "Lowest temperature in Miami on April 23?",
        "description": "This event groups Miami daily low temperature range markets.",
        "resolutionSource": "https://www.wunderground.com/history/daily/us/fl/miami/KMIA",
        "markets": [
            {
                "id": "market-1",
                "question": "Will the lowest temperature in Miami be between 67F and 68F?",
                "outcomes": '["Yes", "No"]',
                "outcomePrices": '["0.41", "0.59"]',
                "bestBids": '["0.40", "0.58"]',
                "bestAsks": '["0.42", "0.60"]',
                "volume": "321.0",
                "endDate": "2099-04-23T12:00:00Z",
                "description": "Child market 1",
                "rules": "Source: Wunderground KMIA",
                "resolutionSource": "https://www.wunderground.com/history/daily/us/fl/miami/KMIA",
            },
            {
                "id": "market-2",
                "question": "Will the lowest temperature in Miami be between 69F and 70F?",
                "outcomes": '["Yes", "No"]',
                "outcomePrices": '["0.22", "0.78"]',
                "bestBids": '["0.20", "0.76"]',
                "bestAsks": '["0.24", "0.80"]',
                "volume": "111.0",
                "endDate": "2099-04-23T12:00:00Z",
                "description": "Child market 2",
                "rules": "Source: Wunderground KMIA",
                "resolutionSource": "https://www.wunderground.com/history/daily/us/fl/miami/KMIA",
            },
        ],
    }

    from weather_pm import polymarket_live

    original_fetch_json = polymarket_live._fetch_gamma_json
    polymarket_live._fetch_gamma_json = lambda path, params=None: event_payload if path == "/events/event-404359" else (_ for _ in ()).throw(AssertionError(path))
    try:
        event = polymarket_live.get_live_event_book_by_id("event-404359")
    finally:
        polymarket_live._fetch_gamma_json = original_fetch_json

    assert event["id"] == "event-404359"
    assert event["category"] == "weather"
    assert event["question"] == "Lowest temperature in Miami on April 23?"
    assert "yes_price" not in event
    assert [market["id"] for market in event["markets"]] == ["market-1", "market-2"]
    assert event["markets"][0]["yes_price"] == 0.41
    assert event["markets"][0]["best_bid"] == 0.4
    assert event["markets"][0]["best_ask"] == 0.42
    assert event["markets"][1]["yes_price"] == 0.22
    assert event["resolution_source"] == "https://www.wunderground.com/history/daily/us/fl/miami/KMIA"


def test_list_live_weather_markets_includes_highest_temperature_series_events_when_markets_endpoint_has_no_weather_matches() -> None:
    series_payload = [
        {
            "id": "hong-kong-daily-highest-temperature",
            "events": [
                {
                    "id": "322442",
                    "title": "Highest temperature in Hong Kong on April 1?",
                    "description": "This market will resolve to the temperature range that contains the highest temperature recorded by the Hong Kong Observatory in degrees Celsius on 1 Apr '26.",
                    "resolutionSource": "https://www.weather.gov.hk/en/cis/climat.htm",
                    "volume": 221180.29265700004,
                    "endDate": "2099-04-01T12:00:00Z",
                }
            ],
        }
    ]
    calls: list[tuple[str, dict[str, object] | None]] = []

    from weather_pm import polymarket_live

    original_fetch_markets = polymarket_live._fetch_gamma_markets
    original_fetch_json = polymarket_live._fetch_gamma_json
    polymarket_live._fetch_gamma_markets = lambda limit, active, closed: [
        {
            "id": "ignore-me",
            "question": "Will candidate X win state Y?",
            "category": "politics",
        }
    ]

    def fake_fetch_json(path: str, params: dict[str, object] | None = None) -> object:
        calls.append((path, params))
        if path == "/series":
            return series_payload
        if path == "/events/322442":
            raise RuntimeError("Gamma request failed with HTTP 404 for https://gamma-api.polymarket.com/events/322442")
        raise AssertionError(path)

    polymarket_live._fetch_gamma_json = fake_fetch_json
    try:
        markets = list_live_weather_markets(limit=5)
    finally:
        polymarket_live._fetch_gamma_markets = original_fetch_markets
        polymarket_live._fetch_gamma_json = original_fetch_json

    assert len(markets) == 1
    assert markets[0]["id"] == "322442"
    assert markets[0]["question"] == "Highest temperature in Hong Kong on April 1?"
    assert markets[0]["resolution_source"] == "https://www.weather.gov.hk/en/cis/climat.htm"
    assert markets[0]["yes_price"] == 0.0
    assert [path for path, _ in calls] == ["/series", "/events/322442"]


def test_list_live_weather_markets_paginates_series_until_limit_is_reached_without_event_lookups_for_non_weather_rows() -> None:
    from weather_pm import polymarket_live

    series_page_0 = [
        {
            "id": "page-0",
            "events": [
                {
                    "id": "non-weather-1",
                    "title": "Will candidate X win state Y?",
                    "description": "Politics market",
                }
            ],
        }
    ]
    series_page_1 = [
        {
            "id": "page-1",
            "events": [
                {
                    "id": "weather-2",
                    "title": "Highest temperature in Hong Kong on April 2?",
                    "description": "This market will resolve to the temperature range that contains the highest temperature recorded by the Hong Kong Observatory in degrees Celsius on 2 Apr '26.",
                    "resolutionSource": "https://www.weather.gov.hk/en/cis/climat.htm",
                    "volume": 289784.951444,
                    "endDate": "2099-04-02T12:00:00Z",
                    "active": True,
                    "closed": False,
                    "archived": False,
                }
            ],
        }
    ]
    calls: list[tuple[str, dict[str, object] | None]] = []

    original_fetch_markets = polymarket_live._fetch_gamma_markets
    original_fetch_json = polymarket_live._fetch_gamma_json
    polymarket_live._fetch_gamma_markets = lambda limit, active, closed: []

    def fake_fetch_json(path: str, params: dict[str, object] | None = None) -> object:
        calls.append((path, params))
        if path != "/series":
            raise AssertionError(path)
        offset = int((params or {}).get("offset", 0))
        if offset == 0:
            return series_page_0
        if offset == 1:
            return series_page_1
        return []

    polymarket_live._fetch_gamma_json = fake_fetch_json
    try:
        markets = list_live_weather_markets(limit=1)
    finally:
        polymarket_live._fetch_gamma_markets = original_fetch_markets
        polymarket_live._fetch_gamma_json = original_fetch_json

    assert len(markets) == 1
    assert markets[0]["id"] == "weather-2"
    assert calls == [
        ("/series", {"limit": 1, "offset": 0}),
        ("/series", {"limit": 1, "offset": 1}),
    ]


def test_list_live_weather_markets_filters_closed_series_events_even_when_series_is_active() -> None:
    from weather_pm import polymarket_live

    closed_weather_event = {
        "id": "closed-weather-1",
        "title": "Highest temperature in Hong Kong on April 2?",
        "description": "This market will resolve to the temperature range that contains the highest temperature recorded by the Hong Kong Observatory in degrees Celsius on 2 Apr '26.",
        "resolutionSource": "https://www.weather.gov.hk/en/cis/climat.htm",
        "volume": 289784.951444,
        "endDate": "2026-04-02T12:00:00Z",
        "active": True,
        "closed": True,
        "archived": False,
        "closedTime": "2026-04-03T05:00:00Z",
    }
    open_weather_event = {
        "id": "open-weather-1",
        "title": "Highest temperature in Hong Kong on April 24?",
        "description": "This market will resolve to the temperature range that contains the highest temperature recorded by the Hong Kong Observatory in degrees Celsius on 24 Apr '26.",
        "resolutionSource": "https://www.weather.gov.hk/en/cis/climat.htm",
        "volume": 123.0,
        "endDate": "2099-04-24T12:00:00Z",
        "active": True,
        "closed": False,
        "archived": False,
    }
    series_payload = [{"id": "series-1", "events": [closed_weather_event, open_weather_event]}]
    calls: list[tuple[str, dict[str, object] | None]] = []

    original_fetch_markets = polymarket_live._fetch_gamma_markets
    original_fetch_json = polymarket_live._fetch_gamma_json
    polymarket_live._fetch_gamma_markets = lambda limit, active, closed: []

    def fake_fetch_json(path: str, params: dict[str, object] | None = None) -> object:
        calls.append((path, params))
        if path == "/series":
            return series_payload
        raise AssertionError(path)

    polymarket_live._fetch_gamma_json = fake_fetch_json
    try:
        markets = list_live_weather_markets(limit=5)
    finally:
        polymarket_live._fetch_gamma_markets = original_fetch_markets
        polymarket_live._fetch_gamma_json = original_fetch_json

    assert [market["id"] for market in markets] == ["open-weather-1"]
    assert [path for path, _ in calls] == ["/series"]


def test_list_live_weather_markets_prefers_series_child_markets_over_parent_event_rows() -> None:
    from weather_pm import polymarket_live

    series_payload = [
        {
            "id": "series-1",
            "events": [
                {
                    "id": "event-1",
                    "title": "Highest temperature in Hong Kong on April 24?",
                    "description": "This market will resolve to the temperature range that contains the highest temperature recorded by the Hong Kong Observatory in degrees Celsius on 24 Apr '26.",
                    "resolutionSource": "https://www.weather.gov.hk/en/cis/climat.htm",
                    "active": True,
                    "closed": False,
                    "archived": False,
                    "markets": [
                        {
                            "id": "child-open-1",
                            "question": "Will the highest temperature in Hong Kong be between 27C and 28C?",
                            "description": "Child market 1",
                            "resolutionSource": "https://www.weather.gov.hk/en/cis/climat.htm",
                            "outcomes": '["Yes", "No"]',
                            "outcomePrices": '["0.31", "0.69"]',
                            "bestBids": '["0.30", "0.68"]',
                            "bestAsks": '["0.32", "0.70"]',
                            "volume": "100.0",
                            "endDate": "2099-04-24T12:00:00Z",
                            "active": True,
                            "closed": False,
                            "archived": False,
                        },
                        {
                            "id": "child-open-2",
                            "question": "Will the highest temperature in Hong Kong be between 28C and 29C?",
                            "description": "Child market 2",
                            "resolutionSource": "https://www.weather.gov.hk/en/cis/climat.htm",
                            "outcomes": '["Yes", "No"]',
                            "outcomePrices": '["0.21", "0.79"]',
                            "bestBids": '["0.20", "0.78"]',
                            "bestAsks": '["0.22", "0.80"]',
                            "volume": "200.0",
                            "endDate": "2099-04-24T12:00:00Z",
                            "active": True,
                            "closed": False,
                            "archived": False,
                        },
                    ],
                }
            ],
        }
    ]

    original_fetch_markets = polymarket_live._fetch_gamma_markets
    original_fetch_json = polymarket_live._fetch_gamma_json
    polymarket_live._fetch_gamma_markets = lambda limit, active, closed: []
    polymarket_live._fetch_gamma_json = lambda path, params=None: series_payload if path == "/series" else (_ for _ in ()).throw(AssertionError(path))
    try:
        markets = list_live_weather_markets(limit=5)
    finally:
        polymarket_live._fetch_gamma_markets = original_fetch_markets
        polymarket_live._fetch_gamma_json = original_fetch_json

    assert [market["id"] for market in markets] == ["child-open-1", "child-open-2"]
    assert all(market["question"].startswith("Will the highest temperature") for market in markets)
    assert all("yes_price" in market for market in markets)



def test_list_live_weather_markets_fetches_event_details_for_numeric_weather_event_ids_without_inline_child_markets() -> None:
    from weather_pm import polymarket_live

    series_payload = [
        {
            "id": "series-1",
            "events": [
                {
                    "id": "401685",
                    "title": "Highest temperature in Hong Kong on April 23?",
                    "description": "This market will resolve to the temperature range that contains the highest temperature recorded by the Hong Kong Observatory in degrees Celsius on 23 Apr '26.",
                    "resolutionSource": "https://www.weather.gov.hk/en/cis/climat.htm",
                    "active": True,
                    "closed": False,
                    "archived": False,
                }
            ],
        }
    ]
    event_payload = {
        "id": "401685",
        "title": "Highest temperature in Hong Kong on April 23?",
        "description": "This market will resolve to the temperature range that contains the highest temperature recorded by the Hong Kong Observatory in degrees Celsius on 23 Apr '26.",
        "resolutionSource": "https://www.weather.gov.hk/en/cis/climat.htm",
        "active": True,
        "closed": False,
        "archived": False,
        "markets": [
            {
                "id": "2040371",
                "question": "Will the highest temperature in Hong Kong be 26C or below on April 23?",
                "outcomes": '["Yes", "No"]',
                "outcomePrices": '["0.05", "0.95"]',
                "bestBids": '["0.04", "0.94"]',
                "bestAsks": '["0.06", "0.96"]',
                "volume": "111.0",
                "endDate": "2099-04-23T12:00:00Z",
                "active": True,
                "closed": False,
                "archived": False,
            },
            {
                "id": "2040372",
                "question": "Will the highest temperature in Hong Kong be 27C or higher on April 23?",
                "outcomes": '["Yes", "No"]',
                "outcomePrices": '["0.25", "0.75"]',
                "bestBids": '["0.24", "0.74"]',
                "bestAsks": '["0.26", "0.76"]',
                "volume": "222.0",
                "endDate": "2099-04-23T12:00:00Z",
                "active": True,
                "closed": False,
                "archived": False,
            },
        ],
    }
    calls: list[tuple[str, dict[str, object] | None]] = []

    original_fetch_markets = polymarket_live._fetch_gamma_markets
    original_fetch_json = polymarket_live._fetch_gamma_json
    polymarket_live._fetch_gamma_markets = lambda limit, active, closed: []

    def fake_fetch_json(path: str, params: dict[str, object] | None = None) -> object:
        calls.append((path, params))
        if path == "/series":
            return series_payload
        if path == "/events/401685":
            return event_payload
        raise AssertionError(path)

    polymarket_live._fetch_gamma_json = fake_fetch_json
    try:
        markets = list_live_weather_markets(limit=5)
    finally:
        polymarket_live._fetch_gamma_markets = original_fetch_markets
        polymarket_live._fetch_gamma_json = original_fetch_json

    assert [market["id"] for market in markets] == ["2040371", "2040372"]
    assert [path for path, _ in calls] == ["/series", "/events/401685"]
    assert all(market["question"].startswith("Will the highest temperature") for market in markets)
    assert all(market["id"] != "401685" for market in markets)
    assert markets[0]["resolution_source"] == "https://www.weather.gov.hk/en/cis/climat.htm"
    assert markets[1]["yes_price"] == 0.25


def test_list_live_weather_markets_fills_remaining_slots_from_series_child_markets() -> None:
    from weather_pm import polymarket_live

    live_market = _sample_gamma_market(id="gamma-weather-1")
    series_payload = [
        {
            "id": "series-1",
            "events": [
                {
                    "id": "event-1",
                    "title": "Highest temperature in Hong Kong on April 24?",
                    "description": "This market will resolve to the temperature range that contains the highest temperature recorded by the Hong Kong Observatory in degrees Celsius on 24 Apr '26.",
                    "resolutionSource": "https://www.weather.gov.hk/en/cis/climat.htm",
                    "active": True,
                    "closed": False,
                    "archived": False,
                    "markets": [
                        {
                            "id": "child-fill-1",
                            "question": "Will the highest temperature in Hong Kong be between 27C and 28C?",
                            "description": "Child market 1",
                            "resolutionSource": "https://www.weather.gov.hk/en/cis/climat.htm",
                            "outcomes": '["Yes", "No"]',
                            "outcomePrices": '["0.31", "0.69"]',
                            "bestBids": '["0.30", "0.68"]',
                            "bestAsks": '["0.32", "0.70"]',
                            "volume": "100.0",
                            "endDate": "2099-04-24T12:00:00Z",
                            "active": True,
                            "closed": False,
                            "archived": False,
                        },
                        {
                            "id": "child-fill-2",
                            "question": "Will the highest temperature in Hong Kong be between 28C and 29C?",
                            "description": "Child market 2",
                            "resolutionSource": "https://www.weather.gov.hk/en/cis/climat.htm",
                            "outcomes": '["Yes", "No"]',
                            "outcomePrices": '["0.21", "0.79"]',
                            "bestBids": '["0.20", "0.78"]',
                            "bestAsks": '["0.22", "0.80"]',
                            "volume": "200.0",
                            "endDate": "2099-04-24T12:00:00Z",
                            "active": True,
                            "closed": False,
                            "archived": False,
                        },
                    ],
                }
            ],
        }
    ]

    original_fetch_markets = polymarket_live._fetch_gamma_markets
    original_fetch_json = polymarket_live._fetch_gamma_json
    polymarket_live._fetch_gamma_markets = lambda limit, active, closed: [live_market]
    polymarket_live._fetch_gamma_json = lambda path, params=None: series_payload if path == "/series" else (_ for _ in ()).throw(AssertionError(path))
    try:
        markets = list_live_weather_markets(limit=3)
    finally:
        polymarket_live._fetch_gamma_markets = original_fetch_markets
        polymarket_live._fetch_gamma_json = original_fetch_json

    assert [market["id"] for market in markets] == ["gamma-weather-1", "child-fill-1", "child-fill-2"]


def test_list_live_weather_markets_filters_series_child_markets_by_child_state() -> None:
    from weather_pm import polymarket_live

    series_payload = [
        {
            "id": "series-1",
            "events": [
                {
                    "id": "event-1",
                    "title": "Highest temperature in Hong Kong on April 24?",
                    "description": "This market will resolve to the temperature range that contains the highest temperature recorded by the Hong Kong Observatory in degrees Celsius on 24 Apr '26.",
                    "resolutionSource": "https://www.weather.gov.hk/en/cis/climat.htm",
                    "active": True,
                    "closed": False,
                    "archived": False,
                    "markets": [
                        {
                            "id": "child-closed",
                            "question": "Will the highest temperature in Hong Kong be between 27C and 28C?",
                            "description": "Closed child",
                            "resolutionSource": "https://www.weather.gov.hk/en/cis/climat.htm",
                            "outcomes": '["Yes", "No"]',
                            "outcomePrices": '["0.31", "0.69"]',
                            "bestBids": '["0.30", "0.68"]',
                            "bestAsks": '["0.32", "0.70"]',
                            "volume": "100.0",
                            "endDate": "2099-04-24T12:00:00Z",
                            "active": True,
                            "closed": True,
                            "archived": False,
                        },
                        {
                            "id": "child-archived",
                            "question": "Will the highest temperature in Hong Kong be between 28C and 29C?",
                            "description": "Archived child",
                            "resolutionSource": "https://www.weather.gov.hk/en/cis/climat.htm",
                            "outcomes": '["Yes", "No"]',
                            "outcomePrices": '["0.21", "0.79"]',
                            "bestBids": '["0.20", "0.78"]',
                            "bestAsks": '["0.22", "0.80"]',
                            "volume": "200.0",
                            "endDate": "2099-04-24T12:00:00Z",
                            "active": True,
                            "closed": False,
                            "archived": True,
                        },
                        {
                            "id": "child-open",
                            "question": "Will the highest temperature in Hong Kong be between 29C and 30C?",
                            "description": "Open child",
                            "resolutionSource": "https://www.weather.gov.hk/en/cis/climat.htm",
                            "outcomes": '["Yes", "No"]',
                            "outcomePrices": '["0.11", "0.89"]',
                            "bestBids": '["0.10", "0.88"]',
                            "bestAsks": '["0.12", "0.90"]',
                            "volume": "300.0",
                            "endDate": "2099-04-24T12:00:00Z",
                            "active": True,
                            "closed": False,
                            "archived": False,
                        },
                    ],
                }
            ],
        }
    ]

    original_fetch_markets = polymarket_live._fetch_gamma_markets
    original_fetch_json = polymarket_live._fetch_gamma_json
    polymarket_live._fetch_gamma_markets = lambda limit, active, closed: []
    polymarket_live._fetch_gamma_json = lambda path, params=None: series_payload if path == "/series" else (_ for _ in ()).throw(AssertionError(path))
    try:
        markets = list_live_weather_markets(limit=5)
    finally:
        polymarket_live._fetch_gamma_markets = original_fetch_markets
        polymarket_live._fetch_gamma_json = original_fetch_json

    assert [market["id"] for market in markets] == ["child-open"]


def test_list_live_weather_markets_inherits_weather_context_from_parent_event_for_sparse_child_markets() -> None:
    from weather_pm import polymarket_live

    series_payload = [
        {
            "id": "series-1",
            "events": [
                {
                    "id": "event-1",
                    "title": "Highest temperature in Hong Kong on April 24?",
                    "description": "This market will resolve to the temperature range that contains the highest temperature recorded by the Hong Kong Observatory in degrees Celsius on 24 Apr '26.",
                    "resolutionSource": "https://www.weather.gov.hk/en/cis/climat.htm",
                    "rules": "Source: Hong Kong Observatory daily climate report.",
                    "active": True,
                    "closed": False,
                    "archived": False,
                    "markets": [
                        {
                            "id": "child-inherit-1",
                            "question": "Will the highest temperature in Hong Kong be between 29C and 30C?",
                            "outcomes": '["Yes", "No"]',
                            "outcomePrices": '["0.11", "0.89"]',
                            "bestBids": '["0.10", "0.88"]',
                            "bestAsks": '["0.12", "0.90"]',
                            "volume": "300.0",
                            "endDate": "2099-04-24T12:00:00Z",
                            "active": True,
                            "closed": False,
                            "archived": False,
                        }
                    ],
                }
            ],
        }
    ]

    original_fetch_markets = polymarket_live._fetch_gamma_markets
    original_fetch_json = polymarket_live._fetch_gamma_json
    polymarket_live._fetch_gamma_markets = lambda limit, active, closed: []
    polymarket_live._fetch_gamma_json = lambda path, params=None: series_payload if path == "/series" else (_ for _ in ()).throw(AssertionError(path))
    try:
        markets = list_live_weather_markets(limit=5)
    finally:
        polymarket_live._fetch_gamma_markets = original_fetch_markets
        polymarket_live._fetch_gamma_json = original_fetch_json

    assert [market["id"] for market in markets] == ["child-inherit-1"]
    assert markets[0]["resolution_source"] == "https://www.weather.gov.hk/en/cis/climat.htm"
    assert markets[0]["description"] == "This market will resolve to the temperature range that contains the highest temperature recorded by the Hong Kong Observatory in degrees Celsius on 24 Apr '26."
    assert markets[0]["rules"] == "Source: Hong Kong Observatory daily climate report."


def test_list_live_weather_markets_fetches_child_markets_from_event_when_series_event_has_no_embedded_markets() -> None:
    from weather_pm import polymarket_live

    series_payload = [
        {
            "id": "series-1",
            "events": [
                {
                    "id": "event-405178",
                    "title": "Lowest temperature in Hong Kong on April 24?",
                    "description": "This market will resolve to the temperature range that contains the lowest temperature recorded by the Hong Kong Observatory in degrees Celsius on 24 Apr '26.",
                    "resolutionSource": "https://www.weather.gov.hk/en/cis/climat.htm",
                    "rules": "Source: Hong Kong Observatory daily climate report.",
                    "active": True,
                    "closed": False,
                    "archived": False,
                }
            ],
        }
    ]
    event_payload = {
        "id": "event-405178",
        "title": "Lowest temperature in Hong Kong on April 24?",
        "description": "This market will resolve to the temperature range that contains the lowest temperature recorded by the Hong Kong Observatory in degrees Celsius on 24 Apr '26.",
        "resolutionSource": "https://www.weather.gov.hk/en/cis/climat.htm",
        "rules": "Source: Hong Kong Observatory daily climate report.",
        "active": True,
        "closed": False,
        "archived": False,
        "markets": [
            {
                "id": "hk-child-1",
                "question": "Will the lowest temperature in Hong Kong be between 22C and 23C?",
                "outcomes": '["Yes", "No"]',
                "outcomePrices": '["0.41", "0.59"]',
                "bestBids": '["0.40", "0.58"]',
                "bestAsks": '["0.42", "0.60"]',
                "volume": "321.0",
                "endDate": "2099-04-24T12:00:00Z",
                "active": True,
                "closed": False,
                "archived": False,
            },
            {
                "id": "hk-child-2",
                "question": "Will the lowest temperature in Hong Kong be between 23C and 24C?",
                "outcomes": '["Yes", "No"]',
                "outcomePrices": '["0.22", "0.78"]',
                "bestBids": '["0.20", "0.76"]',
                "bestAsks": '["0.24", "0.80"]',
                "volume": "111.0",
                "endDate": "2099-04-24T12:00:00Z",
                "active": True,
                "closed": False,
                "archived": False,
            },
        ],
    }

    original_fetch_markets = polymarket_live._fetch_gamma_markets
    original_fetch_json = polymarket_live._fetch_gamma_json
    polymarket_live._fetch_gamma_markets = lambda limit, active, closed: []

    def fake_fetch_json(path: str, params=None):
        if path == "/series":
            return series_payload
        if path == "/events/event-405178":
            return event_payload
        raise AssertionError(path)

    polymarket_live._fetch_gamma_json = fake_fetch_json
    try:
        markets = list_live_weather_markets(limit=5)
    finally:
        polymarket_live._fetch_gamma_markets = original_fetch_markets
        polymarket_live._fetch_gamma_json = original_fetch_json

    assert [market["id"] for market in markets] == ["hk-child-1", "hk-child-2"]
    assert markets[0]["resolution_source"] == "https://www.weather.gov.hk/en/cis/climat.htm"
    assert markets[0]["rules"] == "Source: Hong Kong Observatory daily climate report."


def test_list_live_weather_markets_falls_back_to_event_row_when_event_lookup_has_no_usable_child_markets() -> None:
    from weather_pm import polymarket_live

    series_payload = [
        {
            "id": "series-1",
            "events": [
                {
                    "id": "event-405178",
                    "title": "Lowest temperature in Hong Kong on April 24?",
                    "description": "This market will resolve to the temperature range that contains the lowest temperature recorded by the Hong Kong Observatory in degrees Celsius on 24 Apr '26.",
                    "resolutionSource": "https://www.weather.gov.hk/en/cis/climat.htm",
                    "active": True,
                    "closed": False,
                    "archived": False,
                }
            ],
        }
    ]
    event_payload = {
        "id": "event-405178",
        "title": "Lowest temperature in Hong Kong on April 24?",
        "description": "This market will resolve to the temperature range that contains the lowest temperature recorded by the Hong Kong Observatory in degrees Celsius on 24 Apr '26.",
        "resolutionSource": "https://www.weather.gov.hk/en/cis/climat.htm",
        "active": True,
        "closed": False,
        "archived": False,
        "markets": [
            {
                "id": "non-weather-child",
                "question": "Will candidate X win district Y?",
                "active": True,
                "closed": False,
                "archived": False,
            }
        ],
    }

    original_fetch_markets = polymarket_live._fetch_gamma_markets
    original_fetch_json = polymarket_live._fetch_gamma_json
    polymarket_live._fetch_gamma_markets = lambda limit, active, closed: []

    def fake_fetch_json(path: str, params=None):
        if path == "/series":
            return series_payload
        if path == "/events/event-405178":
            return event_payload
        raise AssertionError(path)

    polymarket_live._fetch_gamma_json = fake_fetch_json
    try:
        markets = list_live_weather_markets(limit=5)
    finally:
        polymarket_live._fetch_gamma_markets = original_fetch_markets
        polymarket_live._fetch_gamma_json = original_fetch_json

    assert [market["id"] for market in markets] == ["event-405178"]
    assert markets[0]["question"] == "Lowest temperature in Hong Kong on April 24?"


def test_normalize_gamma_series_event_uses_price_fields_when_event_payload_contains_them() -> None:
    raw = {
        "id": "376652",
        "title": "Lowest temperature in Tokyo on April 15?",
        "description": "This market will resolve to the temperature range that contains the lowest temperature recorded at the Tokyo Haneda Airport Station in degrees Celsius on 15 Apr '26.",
        "resolutionSource": "https://www.wunderground.com/history/daily/jp/tokyo/RJTT",
        "volume": 82853.23,
        "endDate": "2026-04-16T12:00:00Z",
        "outcomes": '["Yes", "No"]',
        "outcomePrices": '["0.61", "0.39"]',
        "bestBids": '["0.60", "0.38"]',
        "bestAsks": '["0.62", "0.40"]',
    }

    normalized = _normalize_gamma_series_event(raw)

    assert normalized["yes_price"] == 0.61
    assert normalized["best_bid"] == 0.6
    assert normalized["best_ask"] == 0.62


def test_get_live_market_by_id_falls_back_to_highest_temperature_event_payload_when_market_endpoint_404s_duplicate_coverage() -> None:
    event_payload = {
        "id": "322442",
        "title": "Highest temperature in Hong Kong on April 1?",
        "description": "This market will resolve to the temperature range that contains the highest temperature recorded by the Hong Kong Observatory in degrees Celsius on 1 Apr '26.",
        "resolutionSource": "https://www.weather.gov.hk/en/cis/climat.htm",
        "volume": 221180.29265700004,
        "endDate": "2099-04-01T12:00:00Z",
    }

    from weather_pm import polymarket_live

    original_fetch_market = polymarket_live._fetch_gamma_market
    original_fetch_json = polymarket_live._fetch_gamma_json
    polymarket_live._fetch_gamma_market = lambda market_id: (_ for _ in ()).throw(RuntimeError("Gamma request failed with HTTP 404 for https://gamma-api.polymarket.com/markets/322442: {\"type\":\"not found error\"}"))
    polymarket_live._fetch_gamma_json = lambda path, params=None: event_payload if path == "/events/322442" else (_ for _ in ()).throw(AssertionError(path))
    try:
        normalized = get_live_market_by_id("322442")
    finally:
        polymarket_live._fetch_gamma_market = original_fetch_market
        polymarket_live._fetch_gamma_json = original_fetch_json

    assert normalized["id"] == "322442"
    assert normalized["question"] == "Highest temperature in Hong Kong on April 1?"
    assert normalized["resolution_source"] == "https://www.weather.gov.hk/en/cis/climat.htm"
    assert normalized["best_bid"] == 0.0
    assert normalized["best_ask"] == 0.0
    assert normalized["yes_price"] == 0.0