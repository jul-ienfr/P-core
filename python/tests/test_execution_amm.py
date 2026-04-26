from __future__ import annotations

import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from prediction_core.execution import amm_prices, quote_amm_buy, quote_amm_sell


def test_amm_prices_are_complementary_and_follow_pool_skew() -> None:
    yes_price, no_price = amm_prices(reserve_yes=300.0, reserve_no=700.0)

    assert yes_price == pytest.approx(0.7)
    assert no_price == pytest.approx(0.3)
    assert yes_price + no_price == pytest.approx(1.0)


def test_quote_amm_buy_uses_complete_set_mint_and_unwanted_side_swap() -> None:
    quote = quote_amm_buy(
        reserve_yes=100.0,
        reserve_no=100.0,
        outcome="YES",
        amount_usd=10.0,
    )

    assert quote.shares_received == pytest.approx(19.0909090909)
    assert quote.effective_price == pytest.approx(0.5238095238)
    assert quote.total_cost == pytest.approx(10.0)
    assert quote.new_reserve_yes == pytest.approx(90.9090909091)
    assert quote.new_reserve_no == pytest.approx(110.0)


def test_quote_amm_sell_solves_split_swap_burn_redemption() -> None:
    quote = quote_amm_sell(
        reserve_yes=100.0,
        reserve_no=100.0,
        outcome="YES",
        shares=10.0,
    )

    assert quote.cash_received == pytest.approx(4.8750780275)
    assert quote.effective_price == pytest.approx(0.4875078027)
    assert quote.total_cost == pytest.approx(-4.8750780275)
    assert quote.new_reserve_yes == pytest.approx(105.1249219725)
    assert quote.new_reserve_no == pytest.approx(95.1249219725)


def test_amm_quotes_reject_non_positive_trade_sizes() -> None:
    with pytest.raises(ValueError, match="amount_usd must be positive"):
        quote_amm_buy(reserve_yes=100.0, reserve_no=100.0, outcome="YES", amount_usd=0.0)

    with pytest.raises(ValueError, match="shares must be positive"):
        quote_amm_sell(reserve_yes=100.0, reserve_no=100.0, outcome="NO", shares=-1.0)
