from datetime import UTC, datetime

from prediction_core.analytics.events import serialize_event
from weather_pm.analytics_adapter import (
    debug_decision_events_from_shortlist,
    execution_events_from_payload,
    paper_order_events_from_ledger,
    paper_pnl_snapshot_events_from_ledger,
    paper_position_events_from_ledger,
    profile_decision_events_from_shortlist,
)


def test_shortlist_rows_convert_to_profile_decision_events() -> None:
    payload = {
        "run_id": "run-1",
        "generated_at": "2026-04-27T12:00:00+00:00",
        "rows": [
            {
                "market_id": "m1",
                "token_id": "t1",
                "strategy_id": "weather_bookmaker_v1",
                "strategy_profile_id": "surface_grid_trader",
                "decision_status": "trade_small",
                "execution_blocker": "",
                "edge": 0.08,
                "strict_limit_price": 0.42,
                "source_direct": True,
                "orderbook_ok": True,
                "profile_execution_mode": "paper_micro_strict_limit",
                "profile_risk_caps": {"max_order_usdc": 2.0},
            }
        ],
    }

    events = profile_decision_events_from_shortlist(payload, default_observed_at=datetime(2026, 4, 27, tzinfo=UTC))

    assert len(events) == 1
    event = events[0]
    assert event.run_id == "run-1"
    assert event.strategy_id == "weather_bookmaker_v1"
    assert event.profile_id == "surface_grid_trader"
    assert event.market_id == "m1"
    assert event.token_id == "t1"
    assert event.observed_at == datetime(2026, 4, 27, 12, tzinfo=UTC)
    assert event.decision_status == "trade_small"
    assert event.skip_reason == ""
    assert event.execution_mode == "paper_micro_strict_limit"
    assert event.edge == 0.08
    assert event.limit_price == 0.42
    assert event.capped_spend_usdc == 2.0
    assert event.source_ok is True
    assert event.orderbook_ok is True
    assert event.risk_ok is True


def test_shortlist_fallback_fields_and_serialization() -> None:
    payload = {
        "report_id": "report-1",
        "observed_at": "2026-04-27T15:30:01Z",
        "shortlist": [
            {
                "condition_id": "condition-1",
                "profile_id": "strict_micro",
                "strategy": "weather_pm_v2",
                "action": "watch",
                "skip_reason": "edge_below_threshold",
                "probability_edge": "0.0125",
                "limit_price": "0.51",
                "requested_spend_usdc": "1.5",
                "source_ok": True,
                "order_book_depth_usd": 20.0,
            }
        ],
    }

    events = profile_decision_events_from_shortlist(payload)
    event = events[0]

    assert event.run_id == "report-1"
    assert event.strategy_id == "weather_pm_v2"
    assert event.profile_id == "strict_micro"
    assert event.market_id == "condition-1"
    assert event.decision_status == "watch"
    assert event.skip_reason == "edge_below_threshold"
    assert event.edge == 0.0125
    assert event.limit_price == 0.51
    assert event.requested_spend_usdc == 1.5
    assert event.orderbook_ok is True
    assert event.risk_ok is False
    assert serialize_event(event)["observed_at"] == "2026-04-27 15:30:01.000"


def test_shortlist_rows_convert_to_debug_decision_events() -> None:
    payload = {
        "run_id": "run-1",
        "generated_at": "2026-04-27T12:00:00+00:00",
        "rows": [
            {
                "market_id": "m1",
                "token_id": "t1",
                "strategy_id": "weather_bookmaker_v1",
                "profile_id": "strict_micro",
                "decision_status": "skip",
                "skip_reason": "edge_below_threshold",
                "edge": 0.01,
                "limit_price": 0.42,
                "source_ok": True,
                "orderbook_ok": False,
            }
        ],
    }

    events = debug_decision_events_from_shortlist(payload)

    assert len(events) == 1
    event = events[0]
    assert event.table == "debug_decisions"
    assert event.run_id == "run-1"
    assert event.strategy_id == "weather_bookmaker_v1"
    assert event.profile_id == "strict_micro"
    assert event.market_id == "m1"
    assert event.blocker == "edge_below_threshold"
    assert event.edge == 0.01
    assert event.limit_price == 0.42
    assert serialize_event(event)["raw"].startswith('{"decision_status":"skip"')


def test_execution_events_payload_converts_live_orders() -> None:
    payload = {
        "run_id": "exec-run-1",
        "mode": "live",
        "live_orders": [
            {
                "order_id": "live-1",
                "created_at": "2026-04-27T12:00:00+00:00",
                "strategy_id": "weather_profile_surface_grid_trader_v1",
                "profile_id": "surface_grid_trader",
                "market_id": "m1",
                "token_id": "t1",
                "status": "submitted",
                "price": 0.42,
                "size": 10.0,
            }
        ],
    }

    events = execution_events_from_payload(payload)

    assert len(events) == 1
    event = events[0]
    assert event.table == "execution_events"
    assert event.run_id == "exec-run-1"
    assert event.strategy_id == "weather_profile_surface_grid_trader_v1"
    assert event.profile_id == "surface_grid_trader"
    assert event.execution_event_id == "live-1"
    assert event.event_type == "submitted"
    assert event.mode == "live"
    assert event.paper_only is False
    assert event.live_order_allowed is True
    assert serialize_event(event)["raw"] == '{"created_at":"2026-04-27T12:00:00+00:00","market_id":"m1","order_id":"live-1","price":0.42,"profile_id":"surface_grid_trader","size":10.0,"status":"submitted","strategy_id":"weather_profile_surface_grid_trader_v1","token_id":"t1"}'


def test_paper_ledger_rows_convert_to_order_and_position_events() -> None:
    ledger = {
        "run_id": "ledger-run-1",
        "strategy_id": "weather_bookmaker_v1",
        "profile_id": "strict_micro",
        "mode": "paper",
        "orders": [
            {
                "order_id": "order-1",
                "created_at": "2026-04-27T12:00:00+00:00",
                "updated_at": "2026-04-27T12:05:00+00:00",
                "market_id": "m1",
                "token_id": "t1",
                "side": "NO",
                "status": "filled",
                "strict_limit": 0.3,
                "filled_usdc": 5.0,
                "shares": 17.5,
                "avg_fill_price": 0.285714,
                "opening_fee_usdc": 0.05,
                "slippage_usdc": 0.01,
                "estimated_exit_fee_usdc": 0.02,
                "mtm_usdc": 6.0,
                "paper_only": True,
                "live_order_allowed": False,
            },
            {
                "order_id": "order-2",
                "created_at": "2026-04-27T12:10:00+00:00",
                "market_id": "m2",
                "status": "skipped_price_moved",
                "shares": 0.0,
            },
        ],
    }

    orders = paper_order_events_from_ledger(ledger)
    positions = paper_position_events_from_ledger(ledger)

    assert [event.table for event in orders] == ["paper_orders", "paper_orders"]
    assert orders[0].run_id == "ledger-run-1"
    assert orders[0].paper_order_id == "order-1"
    assert orders[0].price == 0.285714
    assert orders[0].size == 17.5
    assert orders[0].spend_usdc == 5.0
    assert orders[0].opening_slippage_usdc == 0.01
    assert orders[0].estimated_exit_cost_usdc == 0.02
    assert len(positions) == 1
    assert positions[0].table == "paper_positions"
    assert positions[0].paper_position_id == "order-1"
    assert positions[0].quantity == 17.5
    assert positions[0].exposure_usdc == 5.0
    assert positions[0].mtm_bid_usdc == 6.0
    assert serialize_event(positions[0])["observed_at"] == "2026-04-27 12:05:00.000"


def test_operator_report_candidates_preserve_paper_order_context() -> None:
    ledger = {
        "run_id": "operator-run-1",
        "generated_at": "2026-04-27T12:00:00+00:00",
        "top_current_candidates": [
            {
                "rank": 3,
                "market_id": "m1",
                "token_id": "t1",
                "question": "Will it rain?",
                "side": "YES",
                "strict_limit": 0.5,
                "strategy_id": "weather_profile_threshold_resolution_harvester_v1",
                "profile_id": "threshold_resolution_harvester",
                "profile_label": "Threshold resolution harvester",
                "profile_execution_mode": "paper_micro_strict_limit",
                "execution_blocker": "",
                "source_status": "direct_latest",
                "source_latency_tier": "direct_latest",
                "primary_archetype": "threshold_harvester",
                "execution": {"fill_status": "filled", "avg_fill_price": 0.5, "fillable_spend": 5.0},
            }
        ],
    }

    orders = paper_order_events_from_ledger(ledger)

    assert len(orders) == 1
    event = orders[0]
    assert event.strategy_id == "weather_profile_threshold_resolution_harvester_v1"
    assert event.profile_id == "threshold_resolution_harvester"
    assert event.raw["candidate_rank"] == 3
    assert event.raw["question"] == "Will it rain?"
    assert event.raw["source_latency_tier"] == "direct_latest"
    assert event.raw["profile_execution_mode"] == "paper_micro_strict_limit"
    assert event.raw["execution"]["fill_status"] == "filled"


    ledger = {
        "run_id": "ledger-run-1",
        "generated_at": "2026-04-27T12:00:00+00:00",
        "strategy_id": "weather_bookmaker_v1",
        "profile_id": "strict_micro",
        "mode": "paper",
        "summary": {
            "orders": 2,
            "filled_usdc": 10.0,
            "pnl_usdc": 3.0,
            "opening_fee_usdc": 0.1,
            "estimated_exit_fee_usdc": 0.2,
            "realized_exit_fee_usdc": 0.3,
            "net_pnl_after_all_costs": 2.4,
        },
        "orders": [
            {"order_id": "win", "status": "settled_win", "filled_usdc": 5.0, "pnl_usdc": 2.0, "net_pnl_after_all_costs": 1.8},
            {"order_id": "loss", "status": "settled_loss", "filled_usdc": 5.0, "pnl_usdc": 1.0, "net_pnl_after_all_costs": 0.6},
        ],
    }

    events = paper_pnl_snapshot_events_from_ledger(ledger)

    assert len(events) == 1
    event = events[0]
    assert event.table == "paper_pnl_snapshots"
    assert event.run_id == "ledger-run-1"
    assert event.strategy_id == "weather_bookmaker_v1"
    assert event.profile_id == "strict_micro"
    assert event.market_id == ""
    assert event.gross_pnl_usdc == 3.0
    assert event.net_pnl_usdc == 2.4
    assert event.costs_usdc == 0.6
    assert event.exposure_usdc == 10.0
    assert event.roi == 0.24
    assert event.winrate == 0.5
    row = serialize_event(event)
    assert row["observed_at"] == "2026-04-27 12:00:00.000"
    assert '"orders":2' in row["raw"]
