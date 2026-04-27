from __future__ import annotations

import pytest

from prediction_core.paper import (
    PaperLedgerError,
    paper_ledger_place,
    paper_ledger_refresh,
    summarize_paper_ledger,
)


def _candidate(**overrides):
    payload = {
        "surface_id": "generic-surface",
        "market_id": "generic-market",
        "token_id": "generic-token",
        "side": "NO",
        "strict_limit": 0.30,
        "spend_usdc": 5.0,
        "orderbook": {"no_asks": [{"price": 0.28, "size": 100.0}]},
        "actual_refresh_price": 0.28,
        "source_status": "source_confirmed",
        "station_status": "station_confirmed",
        "model_reason": "generic paper decision",
    }
    payload.update(overrides)
    return payload


def test_paper_ledger_place_creates_generic_limit_only_order_with_cost_summary() -> None:
    ledger = paper_ledger_place(
        _candidate(
            spend_usdc=10.0,
            orderbook={"no_asks": [{"price": 0.28, "size": 20.0}, {"price": 0.30, "size": 20.0}]},
            taker_base_fee=0.005,
            opening_fee_usdc=0.10,
            estimated_exit_fee_bps=40.0,
            estimated_exit_fee_usdc=0.20,
        )
    )

    order = ledger["orders"][0]
    assert order["paper_only"] is True
    assert order["live_order_allowed"] is False
    assert order["order_type"] == "limit_only_paper"
    assert order["status"] == "filled"
    assert order["filled_usdc"] == 10.0
    assert order["shares"] == pytest.approx(34.666611, rel=1e-6)
    assert order["avg_fill_price"] == pytest.approx(0.288462, rel=1e-6)
    assert order["opening_fee_usdc"] == 0.15
    assert order["slippage_usdc"] == pytest.approx(0.293349, rel=1e-6)
    assert order["estimated_exit_fee_usdc"] == 0.24
    assert order["pnl_usdc"] == -10.39
    assert ledger["summary"]["status_counts"] == {"filled": 1}
    assert ledger["summary"]["net_pnl_after_all_costs"] == -10.39


def test_paper_ledger_place_enforces_book_and_strict_limit_without_market_fallback() -> None:
    with pytest.raises(PaperLedgerError, match="requires a refresh orderbook"):
        paper_ledger_place(_candidate(orderbook=None, actual_refresh_price=None))

    moved = paper_ledger_place(
        _candidate(actual_refresh_price=0.34, orderbook={"no_asks": [{"price": 0.34, "size": 100.0}]})
    )

    order = moved["orders"][0]
    assert order["status"] == "skipped_price_moved"
    assert order["filled_usdc"] == 0.0
    assert order["simulated_fill"]["execution_blocker"] == "strict_limit_price_exceeded"


def test_paper_ledger_refresh_marks_to_market_and_settles_orders() -> None:
    ledger = {
        "orders": [
            paper_ledger_place(_candidate(token_id="active", market_id="m1"))["orders"][0],
            paper_ledger_place(_candidate(token_id="winner", market_id="m2"))["orders"][0],
            paper_ledger_place(_candidate(token_id="loser", market_id="m3"))["orders"][0],
        ]
    }

    refreshed = paper_ledger_refresh(
        ledger,
        refreshes={"active": {"best_bid": 0.43, "actual_refresh_price": 0.44}},
        settlements={"winner": "win", "loser": "loss"},
        max_position_usdc=5.0,
    )

    by_token = {order["token_id"]: order for order in refreshed["orders"]}
    assert by_token["active"]["mtm_usdc"] == pytest.approx(7.678571, rel=1e-6)
    assert by_token["active"]["pnl_usdc"] == pytest.approx(2.678571, rel=1e-6)
    assert by_token["active"]["exit_policy"]["action"] == "HOLD"
    assert by_token["active"]["exit_policy"]["reason"] == "no_exit_trigger"
    assert by_token["active"]["operator_action"] == "TAKE_PROFIT_REVIEW_PAPER"
    assert by_token["winner"]["status"] == "settled_win"
    assert by_token["winner"]["pnl_usdc"] == pytest.approx(12.857142, rel=1e-6)
    assert by_token["loser"]["status"] == "settled_loss"
    assert by_token["loser"]["pnl_usdc"] == -5.0
    assert summarize_paper_ledger(refreshed)["orders"] == 3
