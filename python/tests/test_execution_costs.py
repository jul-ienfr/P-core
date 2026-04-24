from __future__ import annotations

from prediction_core.execution.book import FillEstimate
from prediction_core.execution.costs import estimate_execution_costs
from prediction_core.execution.fees import TradingFeeSchedule, TransferFeeSchedule
from prediction_core.execution.models import BookLevel, OrderBookSnapshot


def test_estimate_execution_costs_builds_all_in_breakdown_for_buy_taker() -> None:
    book = OrderBookSnapshot(
        bids=[BookLevel(price=0.42, quantity=100.0)],
        asks=[BookLevel(price=0.45, quantity=10.0), BookLevel(price=0.46, quantity=15.0)],
    )
    trading_fees = TradingFeeSchedule(maker_bps=10.0, taker_bps=20.0, min_fee=0.0)
    transfer_fees = TransferFeeSchedule(
        deposit_fixed=1.0,
        deposit_bps=20.0,
        withdrawal_fixed=2.0,
        withdrawal_bps=30.0,
    )

    result = estimate_execution_costs(
        book=book,
        side="buy",
        requested_quantity=20.0,
        trading_fee_schedule=trading_fees,
        transfer_fee_schedule=transfer_fees,
        is_maker=False,
        edge_gross=5.5,
    )

    assert result.requested_quantity == 20.0
    assert result.estimated_filled_quantity == 20.0
    assert result.estimated_avg_fill_price == 0.455
    assert result.quoted_mid_price == 0.435
    assert result.quoted_best_bid == 0.42
    assert result.quoted_best_ask == 0.45
    assert result.spread_cost == 0.3
    assert result.book_slippage_cost == 0.1
    assert result.trading_fee_cost == 0.0182
    assert result.deposit_fee_cost == 1.0182
    assert result.withdrawal_fee_cost == 2.0273
    assert result.total_execution_cost == 0.4182
    assert result.total_all_in_cost == 3.4637
    assert result.effective_unit_price == 0.628185
    assert result.edge_net_execution == 5.0818
    assert result.edge_net_all_in == 2.0363


def test_estimate_execution_costs_returns_zero_costs_when_nothing_fills() -> None:
    book = OrderBookSnapshot(
        bids=[BookLevel(price=0.42, quantity=100.0)],
        asks=[],
    )

    result = estimate_execution_costs(
        book=book,
        side="buy",
        requested_quantity=5.0,
        trading_fee_schedule=TradingFeeSchedule(maker_bps=10.0, taker_bps=20.0, min_fee=0.5),
        transfer_fee_schedule=TransferFeeSchedule(deposit_fixed=1.0, withdrawal_fixed=2.0),
        is_maker=False,
        edge_gross=1.0,
    )

    assert result.estimated_filled_quantity == 0.0
    assert result.estimated_avg_fill_price is None
    assert result.spread_cost == 0.0
    assert result.book_slippage_cost == 0.0
    assert result.trading_fee_cost == 0.0
    assert result.deposit_fee_cost == 0.0
    assert result.withdrawal_fee_cost == 0.0
    assert result.total_execution_cost == 0.0
    assert result.total_all_in_cost == 0.0
    assert result.effective_unit_price is None
    assert result.edge_net_execution == 1.0
    assert result.edge_net_all_in == 1.0


def test_estimate_execution_costs_accepts_precomputed_fill_estimate() -> None:
    book = OrderBookSnapshot(
        bids=[BookLevel(price=0.42, quantity=100.0)],
        asks=[BookLevel(price=0.45, quantity=10.0)],
    )
    fill = FillEstimate(
        filled_quantity=8.0,
        unfilled_quantity=0.0,
        gross_notional=3.68,
        average_price=0.46,
        top_of_book_price=0.45,
        slippage_cost=0.08,
        slippage_bps=222.22,
    )

    result = estimate_execution_costs(
        book=book,
        side="buy",
        requested_quantity=8.0,
        fill_estimate=fill,
        trading_fee_schedule=TradingFeeSchedule(maker_bps=0.0, taker_bps=0.0, min_fee=0.0),
        transfer_fee_schedule=None,
        is_maker=False,
        edge_gross=0.5,
    )

    assert result.estimated_filled_quantity == 8.0
    assert result.estimated_avg_fill_price == 0.46
    assert result.spread_cost == 0.12
    assert result.book_slippage_cost == 0.08
    assert result.total_execution_cost == 0.2
    assert result.total_all_in_cost == 0.2
