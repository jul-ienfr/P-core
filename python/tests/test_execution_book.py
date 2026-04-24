from __future__ import annotations

from prediction_core.execution.book import estimate_fill, estimate_fill_from_book
from prediction_core.execution.models import BookLevel, OrderBookSnapshot


def test_estimate_buy_fill_consumes_single_ask_level() -> None:
    book = OrderBookSnapshot(
        bids=[BookLevel(price=0.42, quantity=100.0)],
        asks=[BookLevel(price=0.45, quantity=10.0), BookLevel(price=0.46, quantity=15.0)],
    )

    result = estimate_fill_from_book(book=book, side="buy", requested_quantity=8.0)

    assert result.filled_quantity == 8.0
    assert result.unfilled_quantity == 0.0
    assert result.gross_notional == 3.6
    assert result.average_price == 0.45
    assert result.top_of_book_price == 0.45
    assert result.slippage_cost == 0.0
    assert result.slippage_bps == 0.0


def test_estimate_buy_fill_sweeps_multiple_ask_levels() -> None:
    book = OrderBookSnapshot(
        bids=[BookLevel(price=0.42, quantity=100.0)],
        asks=[BookLevel(price=0.45, quantity=10.0), BookLevel(price=0.46, quantity=15.0)],
    )

    result = estimate_fill_from_book(book=book, side="buy", requested_quantity=20.0)

    assert result.filled_quantity == 20.0
    assert result.unfilled_quantity == 0.0
    assert result.gross_notional == 9.1
    assert result.average_price == 0.455
    assert result.top_of_book_price == 0.45
    assert result.slippage_cost == 0.1
    assert result.slippage_bps == 111.11


def test_estimate_sell_fill_sweeps_multiple_bid_levels() -> None:
    book = OrderBookSnapshot(
        bids=[BookLevel(price=0.42, quantity=12.0), BookLevel(price=0.41, quantity=10.0)],
        asks=[BookLevel(price=0.45, quantity=10.0)],
    )

    result = estimate_fill_from_book(book=book, side="sell", requested_quantity=20.0)

    assert result.filled_quantity == 20.0
    assert result.unfilled_quantity == 0.0
    assert result.gross_notional == 8.32
    assert result.average_price == 0.416
    assert result.top_of_book_price == 0.42
    assert result.slippage_cost == 0.08
    assert result.slippage_bps == 95.24


def test_estimate_fill_returns_partial_when_book_is_insufficient() -> None:
    book = OrderBookSnapshot(
        bids=[BookLevel(price=0.42, quantity=5.0)],
        asks=[BookLevel(price=0.45, quantity=6.0), BookLevel(price=0.46, quantity=4.0)],
    )

    result = estimate_fill_from_book(book=book, side="buy", requested_quantity=15.0)

    assert result.filled_quantity == 10.0
    assert result.unfilled_quantity == 5.0
    assert result.gross_notional == 4.54
    assert result.average_price == 0.454
    assert result.top_of_book_price == 0.45
    assert result.slippage_cost == 0.04
    assert result.slippage_bps == 88.89


def test_estimate_fill_alias_exposes_requested_notional_and_levels_consumed() -> None:
    book = OrderBookSnapshot(
        bids=[BookLevel(price=0.42, quantity=100.0)],
        asks=[BookLevel(price=0.45, quantity=10.0), BookLevel(price=0.46, quantity=15.0)],
    )

    result = estimate_fill(book=book, side="buy", requested_quantity=20.0)

    assert result.requested_quantity == 20.0
    assert result.notional == 9.1
    assert result.gross_notional == 9.1
    assert result.levels_consumed == 2


def test_estimate_fill_invalid_side_returns_zero_fill_without_crashing() -> None:
    book = OrderBookSnapshot(bids=[BookLevel(price=0.42, quantity=100.0)], asks=[BookLevel(price=0.45, quantity=10.0)])

    result = estimate_fill(book=book, side="hold", requested_quantity=5.0)

    assert result.requested_quantity == 5.0
    assert result.filled_quantity == 0.0
    assert result.unfilled_quantity == 5.0
    assert result.notional == 0.0
    assert result.levels_consumed == 0
