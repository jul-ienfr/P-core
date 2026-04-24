from __future__ import annotations

from datetime import datetime, timedelta, timezone

from weather_pm.polymarket_live import _normalize_gamma_market


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
        "clobTokenIds": '["token-yes", "token-no"]',
        "volume": "12345.6",
        "endDate": future_end,
    }
    payload.update(overrides)
    return payload


def test_normalize_gamma_market_enriches_with_clob_book_depth_and_top_levels() -> None:
    from weather_pm import polymarket_live

    original_fetch_clob_book = polymarket_live._fetch_clob_book
    polymarket_live._fetch_clob_book = lambda token_id: {
        "bids": [
            {"price": "0.44", "size": "60"},
            {"price": "0.43", "size": "100"},
        ],
        "asks": [
            {"price": "0.45", "size": "70"},
            {"price": "0.46", "size": "150"},
        ],
    } if token_id == "token-yes" else (_ for _ in ()).throw(AssertionError(token_id))
    try:
        normalized = _normalize_gamma_market(_sample_gamma_market())
    finally:
        polymarket_live._fetch_clob_book = original_fetch_clob_book

    assert normalized["clob_token_id"] == "token-yes"
    assert normalized["best_bid"] == 0.44
    assert normalized["best_ask"] == 0.45
    assert normalized["best_bid_size"] == 60.0
    assert normalized["best_ask_size"] == 70.0
    assert normalized["bid_depth_usd"] == 69.4
    assert normalized["ask_depth_usd"] == 100.5
    assert normalized["bids"][0] == {"price": 0.44, "size": 60.0}
    assert normalized["asks"][1] == {"price": 0.46, "size": 150.0}


def test_normalize_gamma_market_tolerates_missing_clob_book_with_404() -> None:
    from weather_pm import polymarket_live

    original_fetch_clob_book = polymarket_live._fetch_clob_book
    polymarket_live._fetch_clob_book = lambda token_id: (_ for _ in ()).throw(RuntimeError(f"CLOB request failed with HTTP 404 for https://clob.polymarket.com/book?token_id={token_id}: not found"))
    try:
        normalized = _normalize_gamma_market(_sample_gamma_market())
    finally:
        polymarket_live._fetch_clob_book = original_fetch_clob_book

    assert normalized["clob_token_id"] == "token-yes"
    assert normalized["best_bid"] == 0.43
    assert normalized["best_ask"] == 0.45
    assert normalized["best_bid_size"] is None
    assert normalized["best_ask_size"] is None
    assert normalized["bid_depth_usd"] == 0.0
    assert normalized["ask_depth_usd"] == 0.0