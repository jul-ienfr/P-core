from __future__ import annotations


def test_capturable_buy_trade_has_entry_price_slippage_and_guardrails() -> None:
    from weather_pm.capturability import score_trade_capturability

    trade = {"side": "BUY", "price": 0.42, "size": 20}
    context = {
        "orderbook_context_available": True,
        "best_bid": 0.40,
        "best_ask": 0.421,
        "spread": 0.021,
        "available_size_at_or_better_price": 50,
        "estimated_entry_price": 0.421,
        "estimated_slippage_bps": 23.81,
    }

    score = score_trade_capturability(trade, context, price_tolerance=0.005, max_spread=0.05, max_tolerated_slippage_bps=100)

    assert score["capturability"] == "capturable"
    assert score["capturable_score"] >= 0.8
    assert score["estimated_entry_price"] == 0.421
    assert score["estimated_slippage_bps"] <= 100
    assert "touch_price_within_trade_tolerance" in score["capturability_reasons"]
    assert score["paper_only"] is True
    assert score["live_order_allowed"] is False


def test_missing_orderbook_context_is_unknown_with_reason() -> None:
    from weather_pm.capturability import score_trade_capturability

    score = score_trade_capturability({"side": "BUY", "price": 0.42, "size": 20}, {"orderbook_context_available": False})

    assert score["capturability"] == "unknown"
    assert score["capturable_score"] == 0.0
    assert score["estimated_entry_price"] is None
    assert score["estimated_slippage_bps"] is None
    assert "missing_orderbook_context" in score["capturability_reasons"]
    assert score["paper_only"] is True
    assert score["live_order_allowed"] is False


def test_massive_spread_is_not_capturable_with_reason() -> None:
    from weather_pm.capturability import score_trade_capturability

    score = score_trade_capturability(
        {"side": "BUY", "price": 0.42, "size": 20},
        {"orderbook_context_available": True, "best_bid": 0.20, "best_ask": 0.60, "spread": 0.40, "available_size_at_or_better_price": 100},
        max_spread=0.05,
    )

    assert score["capturability"] == "not_capturable"
    assert score["capturable_score"] == 0.0
    assert "spread_too_wide" in score["capturability_reasons"]
    assert score["paper_only"] is True
    assert score["live_order_allowed"] is False
