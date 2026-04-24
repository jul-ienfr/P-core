from __future__ import annotations

from prediction_core.execution.fees import TradingFeeSchedule, TransferFeeSchedule
from prediction_core.paper import PaperTradeStatus, simulate_paper_trade_from_execution
from prediction_core.paper.simulation import PaperExecutionSide, PaperPositionSide
from prediction_core.execution.models import BookLevel, OrderBookSnapshot


def test_simulate_paper_trade_from_execution_builds_filled_simulation() -> None:
    book = OrderBookSnapshot(
        bids=[BookLevel(price=0.42, quantity=100.0)],
        asks=[BookLevel(price=0.45, quantity=10.0), BookLevel(price=0.46, quantity=15.0)],
    )

    simulation = simulate_paper_trade_from_execution(
        run_id="run-paper-1",
        market_id="market-paper-1",
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
        position_side=PaperPositionSide.yes,
        reference_price=0.435,
    )

    assert simulation.status is PaperTradeStatus.filled
    assert simulation.execution_side is PaperExecutionSide.buy
    assert simulation.position_side is PaperPositionSide.yes
    assert simulation.requested_quantity == 20.0
    assert simulation.filled_quantity == 20.0
    assert simulation.average_fill_price == 0.455
    assert simulation.gross_notional == 9.1
    assert simulation.fee_paid == 3.0637
    assert simulation.slippage_bps == 111.11
    assert simulation.fill_count == 1
    assert len(simulation.fills) == 1
    assert simulation.fills[0].filled_quantity == 20.0
    assert simulation.fills[0].fill_price == 0.455
    assert simulation.metadata["execution"]["total_all_in_cost"] == 3.4637


def test_simulate_paper_trade_from_execution_marks_partial_when_book_is_short() -> None:
    book = OrderBookSnapshot(
        bids=[BookLevel(price=0.42, quantity=5.0)],
        asks=[BookLevel(price=0.45, quantity=6.0), BookLevel(price=0.46, quantity=4.0)],
    )

    simulation = simulate_paper_trade_from_execution(
        run_id="run-paper-2",
        market_id="market-paper-2",
        book=book,
        side="buy",
        size=15.0,
        is_maker=False,
        trading_fees=None,
        transfer_fees=None,
    )

    assert simulation.status is PaperTradeStatus.partial
    assert simulation.requested_quantity == 15.0
    assert simulation.filled_quantity == 10.0
    assert simulation.average_fill_price == 0.454
    assert simulation.fill_count == 1
    assert simulation.fills[0].gross_notional == 4.54


def test_simulate_paper_trade_from_execution_marks_skipped_when_nothing_fills() -> None:
    book = OrderBookSnapshot(
        bids=[BookLevel(price=0.42, quantity=100.0)],
        asks=[],
    )

    simulation = simulate_paper_trade_from_execution(
        run_id="run-paper-3",
        market_id="market-paper-3",
        book=book,
        side="buy",
        size=5.0,
        is_maker=False,
        trading_fees=None,
        transfer_fees=None,
    )

    assert simulation.status is PaperTradeStatus.skipped
    assert simulation.filled_quantity == 0.0
    assert simulation.average_fill_price is None
    assert simulation.fill_count == 0
    assert simulation.fills == []
    assert simulation.metadata["reason"] == "no_fill"
