from __future__ import annotations

import pytest

from prediction_core.execution import (
    PolymarketFeeCategory,
    PolymarketMarketRules,
    estimate_polymarket_fee,
    normalize_polymarket_market_rules,
    polymarket_order_size_for_notional,
    validate_polymarket_limit_order,
)


def test_weather_taker_fee_uses_official_share_price_formula() -> None:
    fee = estimate_polymarket_fee(
        shares=100,
        price=0.50,
        category=PolymarketFeeCategory.WEATHER,
        liquidity_role="taker",
    )

    assert fee.fee_usdc == 1.25
    assert fee.fee_rate == 0.05
    assert fee.formula == "shares * fee_rate * price * (1 - price)"


def test_polymarket_maker_fee_is_zero_even_when_category_has_taker_fee() -> None:
    fee = estimate_polymarket_fee(shares=100, price=0.50, category="weather", liquidity_role="maker")

    assert fee.fee_usdc == 0.0
    assert fee.fee_rate == 0.0


def test_normalizes_live_clob_market_minimum_as_shares_and_tick_size() -> None:
    rules = normalize_polymarket_market_rules(
        {
            "minimum_order_size": 5,
            "minimum_tick_size": 0.001,
            "maker_base_fee": 1000,
            "taker_base_fee": 1000,
            "category": "Weather",
        }
    )

    assert rules.minimum_order_size_shares == 5.0
    assert rules.minimum_tick_size == 0.001
    assert rules.category == PolymarketFeeCategory.WEATHER
    assert rules.minimum_notional_usdc(price=0.99) == 4.95
    assert rules.taker_fee_rate == 0.05
    assert rules.maker_fee_rate == 0.0


def test_order_size_for_notional_rounds_down_to_size_tick_and_enforces_five_share_minimum() -> None:
    rules = PolymarketMarketRules(minimum_order_size_shares=5.0, minimum_tick_size=0.01)

    assert polymarket_order_size_for_notional(notional_usdc=2.57, price=0.50, rules=rules) == 5.14
    with pytest.raises(ValueError, match="below Polymarket minimum_order_size"):
        polymarket_order_size_for_notional(notional_usdc=0.01, price=0.01, rules=rules)


def test_validate_polymarket_limit_order_reports_minimum_tick_and_market_buy_notional_guards() -> None:
    rules = PolymarketMarketRules(minimum_order_size_shares=5.0, minimum_tick_size=0.01)

    limit_check = validate_polymarket_limit_order(price=0.123, shares=5, rules=rules)
    assert limit_check.ok is False
    assert "price_not_on_minimum_tick_size" in limit_check.blockers

    market_buy_check = validate_polymarket_limit_order(price=0.01, shares=5, rules=rules, market_buy=True)
    assert market_buy_check.ok is False
    assert "market_buy_notional_below_ui_minimum" in market_buy_check.blockers

    valid_limit = validate_polymarket_limit_order(price=0.01, shares=5, rules=rules)
    assert valid_limit.ok is True
    assert valid_limit.notional_usdc == 0.05
