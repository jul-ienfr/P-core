from datetime import UTC, datetime, timedelta, timezone

from prediction_core.analytics.events import (
    DebugDecisionEvent,
    ExecutionEvent,
    PaperOrderEvent,
    PaperPnlSnapshotEvent,
    PaperPositionEvent,
    ProfileDecisionEvent,
    ProfileMetricEvent,
    StrategyMetricEvent,
    serialize_event,
)


def test_profile_decision_event_serializes_required_fields() -> None:
    event = ProfileDecisionEvent(
        run_id="run-1",
        strategy_id="weather_baseline",
        profile_id="strict_micro",
        market_id="m1",
        observed_at=datetime(2026, 4, 27, tzinfo=UTC),
        mode="paper",
        decision_status="skip",
        skip_reason="edge_below_threshold",
        edge=0.02,
        limit_price=0.41,
        source_ok=True,
        orderbook_ok=True,
        risk_ok=False,
        raw={"hello": "world"},
    )

    row = serialize_event(event)

    assert row["run_id"] == "run-1"
    assert row["strategy_id"] == "weather_baseline"
    assert row["profile_id"] == "strict_micro"
    assert row["market_id"] == "m1"
    assert row["observed_at"] == "2026-04-27 00:00:00.000"
    assert row["raw"] == '{"hello":"world"}'


def test_event_serialization_uses_utc_milliseconds_and_sorted_compact_raw() -> None:
    event = ProfileDecisionEvent(
        run_id="run-1",
        strategy_id="strategy",
        profile_id="profile",
        market_id="market",
        observed_at=datetime(2026, 4, 27, 5, 6, 7, 987654, tzinfo=timezone(timedelta(hours=2))),
        mode="paper",
        decision_status="trade_small",
        raw={"z": 1, "a": {"b": True}},
    )

    row = serialize_event(event)

    assert row["observed_at"] == "2026-04-27 03:06:07.987"
    assert row["raw"] == '{"a":{"b":true},"z":1}'
    assert "table" not in row


def test_all_phase6_event_types_expose_tables_and_serialize() -> None:
    observed_at = datetime(2026, 4, 27, 12, tzinfo=UTC)
    events = [
        DebugDecisionEvent(
            run_id="run-1",
            strategy_id="s1",
            profile_id="p1",
            market_id="m1",
            observed_at=observed_at,
            mode="paper",
            decision_status="skip",
        ),
        PaperOrderEvent(
            run_id="run-1",
            strategy_id="s1",
            profile_id="p1",
            market_id="m1",
            observed_at=observed_at,
            mode="paper",
            paper_order_id="o1",
            side="YES",
            status="filled",
        ),
        PaperPositionEvent(
            run_id="run-1",
            strategy_id="s1",
            profile_id="p1",
            market_id="m1",
            observed_at=observed_at,
            mode="paper",
            paper_position_id="pos1",
            quantity=1.0,
            status="filled",
        ),
        PaperPnlSnapshotEvent(
            run_id="run-1",
            strategy_id="s1",
            profile_id="p1",
            market_id="",
            observed_at=observed_at,
            mode="paper",
            gross_pnl_usdc=1.2,
            net_pnl_usdc=1.0,
            costs_usdc=0.2,
            exposure_usdc=5.0,
            roi=0.2,
            raw={"summary": {"orders": 1}},
        ),
        ProfileMetricEvent(
            run_id="run-1",
            strategy_id="s1",
            profile_id="p1",
            observed_at=observed_at,
            mode="paper",
            decision_count=1,
            trade_count=0,
            skip_count=1,
        ),
        StrategyMetricEvent(
            run_id="run-1",
            strategy_id="s1",
            observed_at=observed_at,
            mode="paper",
            signal_count=1,
            trade_count=0,
            skip_count=1,
        ),
        ExecutionEvent(
            run_id="run-1",
            strategy_id="s1",
            profile_id="p1",
            market_id="m1",
            token_id="t1",
            observed_at=observed_at,
            execution_event_id="exec-1",
            event_type="live_order_sent",
            mode="live",
            paper_only=False,
            live_order_allowed=True,
            raw={"price": 0.42},
        ),
    ]

    assert [event.table for event in events] == [
        "debug_decisions",
        "paper_orders",
        "paper_positions",
        "paper_pnl_snapshots",
        "profile_metrics",
        "strategy_metrics",
        "execution_events",
    ]
    assert [serialize_event(event)["observed_at"] for event in events] == ["2026-04-27 12:00:00.000"] * 7
    pnl_row = serialize_event(events[3])
    assert pnl_row["net_pnl_usdc"] == 1.0
    assert pnl_row["raw"] == '{"summary":{"orders":1}}'
