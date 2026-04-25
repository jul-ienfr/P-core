from __future__ import annotations

from weather_pm.polymarket_client import normalize_market_record
from weather_pm.polymarket_live import _normalize_gamma_market


def test_normalize_market_record_exposes_book_level_aliases_when_depth_is_available() -> None:
    normalized = normalize_market_record(
        {
            "id": "market-depth",
            "category": "weather",
            "question": "Will the highest temperature in Denver be 64F or higher?",
            "yes_price": 0.44,
            "best_bid": 0.43,
            "best_ask": 0.45,
            "volume": 1000.0,
            "bids": [{"price": 0.43, "size": 20.0}],
            "asks": [{"price": 0.45, "size": 30.0}, {"price": 0.46, "size": 40.0}],
        }
    )

    assert normalized["bid_levels"] == [{"price": 0.43, "size": 20.0}]
    assert normalized["ask_levels"] == [{"price": 0.45, "size": 30.0}, {"price": 0.46, "size": 40.0}]
    assert normalized["bids"] == normalized["bid_levels"]
    assert normalized["asks"] == normalized["ask_levels"]


def test_normalize_market_record_builds_synthetic_top_of_book_levels_when_depth_is_missing() -> None:
    normalized = normalize_market_record(
        {
            "id": "market-top-of-book",
            "category": "weather",
            "question": "Will the highest temperature in Denver be 64F or higher?",
            "yes_price": 0.44,
            "best_bid": 0.43,
            "best_ask": 0.45,
            "best_bid_size": 20.0,
            "best_ask_size": 30.0,
            "volume": 1000.0,
        }
    )

    assert normalized["book_depth_source"] == "top_of_book_fallback"
    assert normalized["bid_levels"] == [{"price": 0.43, "size": 20.0}]
    assert normalized["ask_levels"] == [{"price": 0.45, "size": 30.0}]


def test_normalize_gamma_market_exposes_bid_ask_level_aliases_from_clob_book() -> None:
    from weather_pm import polymarket_live

    original_fetch_clob_book = polymarket_live._fetch_clob_book
    polymarket_live._fetch_clob_book = lambda token_id: {
        "bids": [{"price": "0.43", "size": "20"}],
        "asks": [{"price": "0.45", "size": "30"}],
    }
    try:
        normalized = _normalize_gamma_market(
            {
                "id": "gamma-depth",
                "question": "Will the highest temperature in Denver be 64F or higher?",
                "description": "Official observed high temperature for Denver.",
                "rules": "Source: NOAA climate report for station KDEN.",
                "outcomes": '["Yes", "No"]',
                "outcomePrices": '["0.44", "0.56"]',
                "clobTokenIds": '["token-yes", "token-no"]',
                "volume": "12345.6",
            }
        )
    finally:
        polymarket_live._fetch_clob_book = original_fetch_clob_book

    assert normalized["book_depth_source"] == "clob_book"
    assert normalized["bid_levels"] == [{"price": 0.43, "size": 20.0}]
    assert normalized["ask_levels"] == [{"price": 0.45, "size": 30.0}]
