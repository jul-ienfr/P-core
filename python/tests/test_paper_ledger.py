from __future__ import annotations

import json
from pathlib import Path
import sys
import types

import pytest

from prediction_core.paper import (
    PaperLedgerError,
    paper_ledger_place,
    paper_ledger_refresh,
    summarize_paper_ledger,
)
from prediction_core.paper.ledger import paper_ledger_summary_event, paper_order_events_from_ledger, simulate_orderbook_fill

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "orderbook_fill_parity.json"


def _parity_fixture():
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


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


def test_paper_ledger_simulate_orderbook_fill_matches_parity_fixture() -> None:
    payload = _parity_fixture()

    result = simulate_orderbook_fill(
        payload["polymarket_orderbook"],
        side="NO",
        spend_usd=payload["requests"]["spend_usdc"],
        strict_limit=payload["requests"]["strict_limit"],
    )

    expected = dict(payload["expected"]["spend_fill"])
    expected.pop("filled_quantity")

    assert result == expected


def test_paper_ledger_place_uses_parity_fixture_spend_fill() -> None:
    payload = _parity_fixture()
    expected = payload["expected"]["spend_fill"]

    ledger = paper_ledger_place(
        _candidate(
            orderbook=payload["polymarket_orderbook"],
            spend_usdc=payload["requests"]["spend_usdc"],
            strict_limit=payload["requests"]["strict_limit"],
            actual_refresh_price=expected["top_ask"],
        )
    )

    order = ledger["orders"][0]
    assert order["status"] == "filled"
    assert order["filled_usdc"] == expected["fillable_spend"]
    assert order["shares"] == pytest.approx(expected["fillable_spend"] / expected["avg_fill_price"], rel=1e-6)
    assert order["avg_fill_price"] == pytest.approx(expected["avg_fill_price"], rel=1e-6)
    assert order["simulated_fill"]["top_ask"] == expected["top_ask"]
    assert order["simulated_fill"]["levels_used"] == expected["levels_used"]
    assert order["simulated_fill"]["slippage_from_top_ask"] == pytest.approx(expected["slippage_from_top_ask"], rel=1e-6)
    assert order["simulated_fill"]["execution_blocker"] is None
    assert order["simulated_fill"]["fill_status"] == "filled"


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
    assert ledger["summary"]["paper_only"] is True
    assert ledger["summary"]["live_order_allowed"] is False
    assert ledger["summary"]["status_counts"] == {"filled": 1}
    assert ledger["summary"]["net_pnl_after_all_costs"] == -10.39


def test_paper_ledger_place_uses_rust_cost_state_when_enabled(monkeypatch) -> None:
    monkeypatch.setenv("PREDICTION_CORE_RUST_ORDERBOOK", "1")
    fake_module = types.ModuleType("prediction_core._rust_orderbook")

    def paper_opening_cost_state(**kwargs):
        assert kwargs["filled_usdc"] == 10.0
        assert kwargs["opening_fee_bps"] == 50.0
        return {
            "opening_trading_fee_usdc": 0.05,
            "opening_fixed_fee_usdc": 0.1,
            "opening_fee_usdc": 0.15,
            "slippage_usdc": 0.293349,
            "all_in_entry_cost_usdc": 10.15,
            "estimated_exit_fixed_fee_usdc": 0.2,
            "estimated_exit_fee_bps": 40.0,
            "estimated_exit_fee_usdc": 0.24,
            "paper_exit_value_usdc": 0.0,
        }

    def paper_fee_amount(**kwargs):
        return round(max(0.0, kwargs["fixed"]) + max(0.0, kwargs["notional"]) * max(0.0, kwargs["bps"]) / 10000.0, 6)

    fake_module.paper_opening_cost_state = paper_opening_cost_state
    fake_module.paper_fee_amount = paper_fee_amount
    monkeypatch.setitem(sys.modules, "prediction_core._rust_orderbook", fake_module)

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

    assert ledger["orders"][0]["all_in_entry_cost_usdc"] == 10.15
    assert ledger["orders"][0]["pnl_usdc"] == -10.39


def test_paper_ledger_place_records_planned_when_no_spend_is_requested() -> None:
    ledger = paper_ledger_place(_candidate(spend_usdc=0.0))

    order = ledger["orders"][0]
    assert order["paper_only"] is True
    assert order["live_order_allowed"] is False
    assert order["status"] == "planned"
    assert order["operator_action"] == "PENDING_LIMIT"
    assert ledger["summary"]["status_counts"] == {"planned": 1}


def test_paper_ledger_place_records_partial_without_market_fallback() -> None:
    ledger = paper_ledger_place(_candidate(orderbook={"no_asks": [{"price": 0.28, "size": 5.0}]}))

    order = ledger["orders"][0]
    assert order["paper_only"] is True
    assert order["live_order_allowed"] is False
    assert order["status"] == "partial"
    assert order["operator_action"] == "PENDING_LIMIT"
    assert order["simulated_fill"]["execution_blocker"] == "insufficient_executable_depth"


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


def test_paper_ledger_refresh_uses_parity_fixture_exit_orderbook() -> None:
    payload = _parity_fixture()
    ledger = paper_ledger_place(_candidate(orderbook=payload["polymarket_orderbook"]))
    order = ledger["orders"][0]
    order["shares"] = payload["requests"]["exit_quantity"]
    order["filled_usdc"] = 5.0
    order["all_in_entry_cost_usdc"] = 5.0
    order["estimated_exit_fee_bps"] = 0.0
    order["estimated_exit_fee_usdc"] = 0.0

    refreshed = paper_ledger_refresh(
        {"orders": [order]},
        refreshes={
            order["token_id"]: {
                "best_bid": payload["polymarket_orderbook"]["no_bids"][0]["price"],
                "exit_orderbook": {"no_bids": payload["polymarket_orderbook"]["no_bids"]},
            }
        },
    )

    refreshed_order = refreshed["orders"][0]
    expected = payload["expected"]["exit_value"]
    assert refreshed_order["exit_cost_basis"] == "live_bid_book"
    assert refreshed_order["paper_exit_value_usdc"] == pytest.approx(expected["value"], rel=1e-6)
    assert refreshed_order["mtm_usdc"] == pytest.approx(expected["value"], rel=1e-6)
    assert refreshed_order["realized_exit_fee_usdc"] == 0.0
    assert refreshed_order["pnl_usdc"] == pytest.approx(expected["value"] - 5.0, rel=1e-6)


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


def test_paper_ledger_refresh_does_not_update_already_settled_orders() -> None:
    order = paper_ledger_place(_candidate(token_id="settled", market_id="m1"))["orders"][0]
    order.update({"status": "settled_win", "mtm_usdc": 12.0, "pnl_usdc": 7.0, "net_pnl_after_all_costs": 7.0, "updated_at": "final"})

    refreshed = paper_ledger_refresh(
        {"orders": [order]},
        refreshes={"settled": {"best_bid": 0.0, "actual_refresh_price": 0.0}},
        settlements={"settled": "loss"},
    )

    assert refreshed["orders"][0] == order
    assert refreshed["summary"]["pnl_usdc"] == 7.0


def test_paper_order_events_are_deterministic_paper_only_and_chained() -> None:
    ledger = {
        "run_id": "ledger-run",
        "orders": [
            {
                "order_id": "o1",
                "updated_at": "2026-01-01T00:00:00+00:00",
                "status": "filled",
                "market_id": "m1",
                "token_id": "t1",
                "side": "YES",
                "filled_usdc": 5.0,
                "shares": 10.0,
                "pnl_usdc": 1.0,
                "net_pnl_after_all_costs": 0.9,
                "api_key": "secret",
            },
            {
                "order_id": "o2",
                "updated_at": "2026-01-01T00:00:01+00:00",
                "status": "planned",
                "market_id": "m2",
                "token_id": "t2",
                "side": "NO",
            },
        ],
    }

    events = paper_order_events_from_ledger(ledger, run_id="test-run")
    repeat = paper_order_events_from_ledger(ledger, run_id="test-run")

    assert events == repeat
    assert [event["event_type"] for event in events] == ["paper_order_filled", "paper_order_intent"]
    assert all(event["paper_only"] is True for event in events)
    assert all(event["live_order_allowed"] is False for event in events)
    assert all(event["payload"]["paper_only"] is True for event in events)
    assert all(event["payload"]["live_order_allowed"] is False for event in events)
    assert "api_key" not in events[0]["payload"]
    assert events[1]["previous_hash"] == events[0]["event_id"]
    assert events[0]["stream_id"] == "ledger-run"
    assert events[0]["correlation_id"] == "test-run"
    assert events[0]["causation_id"] == "t1"


def test_paper_order_event_statuses_map_to_stable_event_types() -> None:
    ledger = {
        "orders": [
            {"status": "filled", "updated_at": "2026-01-01T00:00:00+00:00"},
            {"status": "partial", "updated_at": "2026-01-01T00:00:00+00:00"},
            {"status": "pending", "updated_at": "2026-01-01T00:00:00+00:00"},
            {"status": "settled_win", "updated_at": "2026-01-01T00:00:00+00:00"},
            {"status": "settled_loss", "updated_at": "2026-01-01T00:00:00+00:00"},
            {"status": "skipped_price_moved", "updated_at": "2026-01-01T00:00:00+00:00"},
            {"status": "cancelled", "updated_at": "2026-01-01T00:00:00+00:00"},
        ],
    }

    assert [event["event_type"] for event in paper_order_events_from_ledger(ledger)] == [
        "paper_order_filled",
        "paper_order_partial",
        "paper_order_intent",
        "paper_position_settled",
        "paper_position_settled",
        "paper_order_skipped",
        "paper_order_skipped",
    ]


def test_paper_ledger_summary_event_includes_summary_payload() -> None:
    ledger = {
        "summary": {
            "filled_usdc": 5.0,
            "net_pnl_after_all_costs": 1.25,
            "paper_only": True,
            "live_order_allowed": False,
        }
    }

    event = paper_ledger_summary_event(ledger, run_id="summary-run", previous_hash="previous-event")

    assert event["event_type"] == "paper_ledger_summary"
    assert event["previous_hash"] == "previous-event"
    assert event["payload"]["filled_usdc"] == 5.0
    assert event["payload"]["net_pnl_after_all_costs"] == 1.25
    assert event["paper_only"] is True
    assert event["live_order_allowed"] is False


def test_paper_ledger_refresh_uses_rust_pnl_when_enabled(monkeypatch) -> None:
    monkeypatch.setenv("PREDICTION_CORE_RUST_ORDERBOOK", "1")
    fake_module = types.ModuleType("prediction_core._rust_orderbook")

    def paper_refresh_pnl(**kwargs):
        assert kwargs["mtm_usdc"] == pytest.approx(7.678571, rel=1e-6)
        return 2.678571

    def paper_settlement_pnl(**kwargs):
        return {
            "status": "settled_win" if kwargs["won"] else "settled_loss",
            "mtm_usdc": round(kwargs["shares"], 6) if kwargs["won"] else 0.0,
            "pnl_usdc": 12.857142 if kwargs["won"] else -5.0,
            "net_pnl_after_all_costs": 12.857142 if kwargs["won"] else -5.0,
        }

    fake_module.paper_refresh_pnl = paper_refresh_pnl
    fake_module.paper_settlement_pnl = paper_settlement_pnl
    monkeypatch.setitem(sys.modules, "prediction_core._rust_orderbook", fake_module)
    ledger = {
        "orders": [
            paper_ledger_place(_candidate(token_id="active", market_id="m1"))["orders"][0],
            paper_ledger_place(_candidate(token_id="winner", market_id="m2"))["orders"][0],
        ]
    }

    refreshed = paper_ledger_refresh(
        ledger,
        refreshes={"active": {"best_bid": 0.43, "actual_refresh_price": 0.44}},
        settlements={"winner": "win"},
    )

    by_token = {order["token_id"]: order for order in refreshed["orders"]}
    assert by_token["active"]["pnl_usdc"] == 2.678571
    assert by_token["winner"]["status"] == "settled_win"
    assert by_token["winner"]["pnl_usdc"] == 12.857142
