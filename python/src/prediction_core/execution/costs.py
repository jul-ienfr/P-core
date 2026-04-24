from __future__ import annotations

from prediction_core.execution.book import FillEstimate, estimate_fill_from_book
from prediction_core.execution.fees import (
    TradingFeeSchedule,
    TransferFeeSchedule,
    estimate_trading_fee,
    estimate_transfer_costs,
)
from prediction_core.execution.models import ExecutionCostBreakdown, OrderBookSnapshot


BookSide = str


def estimate_execution_costs(
    *,
    book: OrderBookSnapshot,
    side: BookSide,
    requested_quantity: float,
    trading_fee_schedule: TradingFeeSchedule | None,
    transfer_fee_schedule: TransferFeeSchedule | None,
    is_maker: bool,
    edge_gross: float = 0.0,
    fill_estimate: FillEstimate | None = None,
) -> ExecutionCostBreakdown:
    fill = fill_estimate or estimate_fill_from_book(
        book=book,
        side=side,
        requested_quantity=requested_quantity,
    )

    filled_quantity = fill.filled_quantity
    gross_notional = fill.gross_notional if filled_quantity > 0 else 0.0

    spread_cost = 0.0
    if filled_quantity > 0 and book.mid_price is not None and fill.top_of_book_price is not None:
        spread_cost = round(abs(fill.top_of_book_price - book.mid_price) * filled_quantity, 6)

    trading_fee_cost = 0.0
    if filled_quantity > 0 and trading_fee_schedule is not None:
        trading_fee_cost = estimate_trading_fee(
            notional=gross_notional,
            schedule=trading_fee_schedule,
            is_maker=is_maker,
        ).fee

    deposit_fee_cost = 0.0
    withdrawal_fee_cost = 0.0
    if filled_quantity > 0 and transfer_fee_schedule is not None:
        transfer_costs = estimate_transfer_costs(
            amount=gross_notional,
            schedule=transfer_fee_schedule,
        )
        deposit_fee_cost = transfer_costs.deposit_fee
        withdrawal_fee_cost = transfer_costs.withdrawal_fee

    return ExecutionCostBreakdown(
        requested_quantity=round(max(0.0, float(requested_quantity)), 6),
        estimated_filled_quantity=filled_quantity,
        estimated_avg_fill_price=fill.average_price,
        quoted_mid_price=book.mid_price,
        quoted_best_bid=book.best_bid,
        quoted_best_ask=book.best_ask,
        spread_cost=spread_cost,
        book_slippage_cost=fill.slippage_cost,
        trading_fee_cost=trading_fee_cost,
        deposit_fee_cost=deposit_fee_cost,
        withdrawal_fee_cost=withdrawal_fee_cost,
        edge_gross=round(float(edge_gross), 6),
    )
