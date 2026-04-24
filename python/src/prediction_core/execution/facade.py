from __future__ import annotations

from prediction_core.execution.costs import estimate_execution_costs
from prediction_core.execution.fees import TradingFeeSchedule, TransferFeeSchedule
from prediction_core.execution.models import ExecutionCostBreakdown, OrderBookSnapshot


BookSide = str


def quote_execution_cost(
    *,
    book: OrderBookSnapshot,
    side: BookSide,
    size: float,
    is_maker: bool,
    trading_fees: TradingFeeSchedule | None,
    transfer_fees: TransferFeeSchedule | None,
    edge_gross: float = 0.0,
) -> ExecutionCostBreakdown:
    return estimate_execution_costs(
        book=book,
        side=side,
        requested_quantity=size,
        trading_fee_schedule=trading_fees,
        transfer_fee_schedule=transfer_fees,
        is_maker=is_maker,
        edge_gross=edge_gross,
    )


def estimate_order_cost(
    *,
    book: OrderBookSnapshot,
    side: BookSide,
    size: float,
    is_maker: bool,
    trading_fees: TradingFeeSchedule | None,
    transfer_fees: TransferFeeSchedule | None,
    edge_gross: float = 0.0,
) -> ExecutionCostBreakdown:
    return quote_execution_cost(
        book=book,
        side=side,
        size=size,
        is_maker=is_maker,
        trading_fees=trading_fees,
        transfer_fees=transfer_fees,
        edge_gross=edge_gross,
    )
