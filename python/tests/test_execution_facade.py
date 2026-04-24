from __future__ import annotations

from prediction_core.execution.facade import estimate_order_cost, quote_execution_cost
from prediction_core.execution.fees import TradingFeeSchedule, TransferFeeSchedule
from prediction_core.execution.models import BookLevel, OrderBookSnapshot


def test_quote_execution_cost_delegates_to_execution_costs_surface() -> None:
    book = OrderBookSnapshot(
        bids=[BookLevel(price=0.42, quantity=100.0)],
        asks=[BookLevel(price=0.45, quantity=10.0), BookLevel(price=0.46, quantity=15.0)],
    )

    result = quote_execution_cost(
        book=book,
        side="buy",
        size=20.0,
        is_maker=False,
        trading_fees=TradingFeeSchedule(maker_bps=10.0, taker_bps=20.0, min_fee=0.0),
        transfer_fees=TransferFeeSchedule(
            deposit_fixed=1.0,
            deposit_bps=20.0,
            withdrawal_fixed=2.0,
            withdrawal_bps=30.0,
        ),
        edge_gross=5.5,
    )

    assert result.requested_quantity == 20.0
    assert result.estimated_filled_quantity == 20.0
    assert result.total_execution_cost == 0.4182
    assert result.total_all_in_cost == 3.4637
    assert result.edge_net_all_in == 2.0363


def test_estimate_order_cost_alias_matches_quote_execution_cost() -> None:
    book = OrderBookSnapshot(
        bids=[BookLevel(price=0.42, quantity=100.0)],
        asks=[BookLevel(price=0.45, quantity=10.0)],
    )
    trading_fees = TradingFeeSchedule(maker_bps=0.0, taker_bps=20.0, min_fee=0.0)
    transfer_fees = TransferFeeSchedule()

    quoted = quote_execution_cost(
        book=book,
        side="buy",
        size=8.0,
        is_maker=False,
        trading_fees=trading_fees,
        transfer_fees=transfer_fees,
        edge_gross=1.0,
    )
    estimated = estimate_order_cost(
        book=book,
        side="buy",
        size=8.0,
        is_maker=False,
        trading_fees=trading_fees,
        transfer_fees=transfer_fees,
        edge_gross=1.0,
    )

    assert estimated.to_dict() == quoted.to_dict()


def test_quote_execution_cost_accepts_missing_fee_schedules() -> None:
    book = OrderBookSnapshot(
        bids=[BookLevel(price=0.42, quantity=10.0)],
        asks=[BookLevel(price=0.45, quantity=10.0)],
    )

    result = quote_execution_cost(
        book=book,
        side="sell",
        size=5.0,
        is_maker=True,
        trading_fees=None,
        transfer_fees=None,
        edge_gross=0.2,
    )

    assert result.requested_quantity == 5.0
    assert result.estimated_filled_quantity == 5.0
    assert result.trading_fee_cost == 0.0
    assert result.deposit_fee_cost == 0.0
    assert result.withdrawal_fee_cost == 0.0
