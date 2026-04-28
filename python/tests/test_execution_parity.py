from __future__ import annotations

import pytest

from prediction_core.execution import (
    BookLevel,
    ExecutionAssumptions,
    OrderBookSnapshot,
    deterministic_replay_scenarios,
    quote_execution_parity,
)
from prediction_core.paper import PaperTradeStatus, simulate_paper_trade_from_execution


def test_replay_scenarios_cover_phase1_edge_cases() -> None:
    scenarios = {scenario.name: scenario for scenario in deterministic_replay_scenarios()}

    assert set(scenarios) == {
        "empty_book",
        "wide_spread_with_latency_and_fees",
        "partial_fill_insufficient_depth",
        "insufficient_depth_rejected",
        "single_level_no_sweep_partial",
        "queue_position_consumes_top_level",
    }

    for scenario in scenarios.values():
        quote = quote_execution_parity(
            book=scenario.book,
            side=scenario.side,
            requested_quantity=scenario.requested_quantity,
            assumptions=scenario.assumptions,
        )
        assert quote.status == scenario.expected_status
        assert quote.blocker == scenario.expected_blocker
        assert quote.mode in {"replay", "paper", "live_dry_run"}


def test_execution_parity_applies_latency_slippage_queue_depth_and_fees() -> None:
    book = OrderBookSnapshot(
        bids=[BookLevel(price=0.44, quantity=5.0)],
        asks=[BookLevel(price=0.45, quantity=2.0), BookLevel(price=0.47, quantity=4.0)],
    )
    assumptions = ExecutionAssumptions(
        mode="live_dry_run",
        latency_ms=900,
        slippage_bps=100.0,
        queue_ahead_quantity=2.0,
        taker_fee_bps=10.0,
    )

    quote = quote_execution_parity(book=book, side="buy", requested_quantity=3.0, assumptions=assumptions)

    assert quote.status == "filled"
    assert quote.latency_ms == 900
    assert quote.queue_ahead_quantity == 2.0
    assert quote.levels_consumed == 1
    assert quote.average_fill_price == 0.47
    assert quote.gross_notional == 1.41
    assert quote.assumption_slippage_cost == 0.0141
    assert quote.cost.trading_fee_cost == 0.00141
    assert quote.cost.book_slippage_cost == 0.0141


def test_execution_parity_can_reject_insufficient_depth_without_real_orders() -> None:
    book = OrderBookSnapshot(
        bids=[BookLevel(price=0.38, quantity=1.0)],
        asks=[BookLevel(price=0.40, quantity=1.5)],
    )

    quote = quote_execution_parity(
        book=book,
        side="buy",
        requested_quantity=3.0,
        assumptions=ExecutionAssumptions(mode="paper", reject_on_insufficient_depth=True),
    )

    assert quote.status == "rejected"
    assert quote.blocker == "insufficient_depth"
    assert quote.unfilled_quantity == 1.5


def test_execution_assumptions_reject_non_dry_run_modes() -> None:
    with pytest.raises(ValueError, match="paper/dry-run only"):
        ExecutionAssumptions(mode="live")  # type: ignore[arg-type]


def test_paper_simulation_embeds_parity_quote_metadata_without_live_order_fields() -> None:
    book = OrderBookSnapshot(
        bids=[BookLevel(price=0.38, quantity=1.0)],
        asks=[BookLevel(price=0.40, quantity=1.0)],
    )

    simulation = simulate_paper_trade_from_execution(
        run_id="phase1",
        market_id="demo-market",
        book=book,
        side="buy",
        size=2.0,
        is_maker=False,
        trading_fees=None,
        transfer_fees=None,
        execution_assumptions=ExecutionAssumptions(mode="paper", reject_on_insufficient_depth=True),
    )

    assert simulation.status == PaperTradeStatus.rejected
    parity_quote = simulation.metadata["execution"]["parity_quote"]
    assert parity_quote["status"] == "rejected"
    assert parity_quote["blocker"] == "insufficient_depth"
    assert parity_quote["mode"] == "paper"
    assert "wallet" not in simulation.metadata
    assert "credential" not in simulation.metadata
