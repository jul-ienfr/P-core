from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from prediction_core.paper import (
    PaperTradeFill,
    PaperTradePostmortem,
    PaperTradeSimulation,
    PaperTradeStatus,
)


def test_paper_simulation_derives_average_fill_price_and_activity_state() -> None:
    simulation = PaperTradeSimulation(
        run_id="run-123",
        market_id="market-xyz",
        status=PaperTradeStatus.filled,
        requested_quantity=2.0,
        filled_quantity=2.0,
        gross_notional=0.84,
        fills=[
            PaperTradeFill(
                trade_id="trade-1",
                run_id="run-123",
                market_id="market-xyz",
                requested_quantity=2.0,
                filled_quantity=2.0,
                fill_price=0.42,
                gross_notional=0.84,
            )
        ],
    )

    assert simulation.average_fill_price == 0.42
    assert simulation.fill_count == 1
    assert simulation.is_active is True
    assert simulation.settlement_status == "simulated_settled"


def test_paper_simulation_marks_skipped_trades_as_not_settled() -> None:
    simulation = PaperTradeSimulation(
        run_id="run-124",
        market_id="market-abc",
        status=PaperTradeStatus.skipped,
    )

    assert simulation.is_active is False
    assert simulation.settlement_status == "not_settled"


def test_paper_simulation_generates_postmortem_summary_for_partial_fill() -> None:
    simulation = PaperTradeSimulation(
        run_id="run-125",
        market_id="market-partial",
        status=PaperTradeStatus.partial,
        requested_quantity=4.0,
        filled_quantity=3.0,
        gross_notional=1.59,
        fee_paid=0.01,
        reference_price=0.5,
        slippage_bps=12.5,
        fills=[
            PaperTradeFill(
                trade_id="trade-2",
                run_id="run-125",
                market_id="market-partial",
                requested_quantity=4.0,
                filled_quantity=2.0,
                fill_price=0.52,
                gross_notional=1.04,
            ),
            PaperTradeFill(
                trade_id="trade-2",
                run_id="run-125",
                market_id="market-partial",
                requested_quantity=4.0,
                filled_quantity=1.0,
                fill_price=0.55,
                gross_notional=0.55,
            ),
        ],
    )

    postmortem = simulation.postmortem()

    assert isinstance(postmortem, PaperTradePostmortem)
    assert postmortem.trade_id == simulation.trade_id
    assert postmortem.fill_rate == 0.75
    assert postmortem.fill_count == 2
    assert postmortem.average_fill_quantity == 1.5
    assert postmortem.fragmented is True
    assert postmortem.fragmentation_score == 0.333333
    assert postmortem.closing_line_drift_bps == 300.0
    assert postmortem.gross_cash_flow == -1.59
    assert postmortem.net_cash_flow == -1.6
    assert postmortem.effective_price_after_fees == 0.533333
    assert postmortem.no_trade_zone is False
    assert postmortem.stale_blocked is False
    assert postmortem.recommendation == "reduce_size"
    assert postmortem.notes == ["partial_fill", "fragmented"]


def test_paper_simulation_postmortem_marks_no_trade_zone_for_stale_skip() -> None:
    simulation = PaperTradeSimulation(
        run_id="run-126",
        market_id="market-stale",
        status=PaperTradeStatus.skipped,
        metadata={"reason": "snapshot_stale", "stale_blocked": True},
    )

    postmortem = simulation.postmortem()

    assert postmortem.fill_rate == 0.0
    assert postmortem.no_trade_zone is True
    assert postmortem.stale_blocked is True
    assert postmortem.recommendation == "no_trade"
    assert postmortem.notes == ["skipped", "no_trade_zone", "stale_blocked", "snapshot_stale"]
