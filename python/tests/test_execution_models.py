from __future__ import annotations

from prediction_core.execution.models import (
    BookLevel,
    ExecutionCostBreakdown,
    OrderBookSnapshot,
)


def test_order_book_snapshot_derives_best_prices_and_mid_price() -> None:
    book = OrderBookSnapshot(
        bids=[BookLevel(price=0.42, quantity=100.0)],
        asks=[BookLevel(price=0.45, quantity=80.0)],
        venue="polymarket",
    )

    assert book.best_bid == 0.42
    assert book.best_ask == 0.45
    assert book.mid_price == 0.435
    assert book.spread == 0.03


def test_order_book_snapshot_returns_none_mid_price_when_one_side_missing() -> None:
    book = OrderBookSnapshot(
        bids=[BookLevel(price=0.42, quantity=100.0)],
        asks=[],
    )

    assert book.best_bid == 0.42
    assert book.best_ask is None
    assert book.mid_price is None
    assert book.spread is None


def test_execution_cost_breakdown_derives_total_costs_and_effective_price() -> None:
    breakdown = ExecutionCostBreakdown(
        requested_quantity=100.0,
        estimated_filled_quantity=80.0,
        estimated_avg_fill_price=0.47,
        quoted_mid_price=0.435,
        quoted_best_bid=0.42,
        quoted_best_ask=0.45,
        spread_cost=1.2,
        book_slippage_cost=1.6,
        trading_fee_cost=0.8,
        deposit_fee_cost=2.0,
        withdrawal_fee_cost=3.0,
        edge_gross=5.5,
    )

    assert breakdown.total_execution_cost == 3.6
    assert breakdown.total_all_in_cost == 8.6
    assert breakdown.effective_unit_price == 0.5775
    assert breakdown.edge_net_execution == 1.9
    assert breakdown.edge_net_all_in == -3.1
