from datetime import UTC, datetime

from prediction_core.analytics.events import PaperOrderEvent, PaperPositionEvent, ProfileDecisionEvent, serialize_event
from prediction_core.analytics.metrics import build_profile_metric_events, build_strategy_metric_events


def _decision(profile_id: str, status: str, edge: float | None = None) -> ProfileDecisionEvent:
    return ProfileDecisionEvent(
        run_id="run-1",
        strategy_id="weather_bookmaker_v1",
        profile_id=profile_id,
        market_id="m1",
        observed_at=datetime(2026, 4, 27, 12, tzinfo=UTC),
        mode="paper",
        decision_status=status,
        edge=edge,
    )


def test_build_profile_metric_events_aggregates_decisions_orders_positions() -> None:
    decisions = [_decision("strict", "trade_small", 0.08), _decision("strict", "skip", 0.01)]
    orders = [
        PaperOrderEvent(
            run_id="run-1",
            strategy_id="weather_bookmaker_v1",
            profile_id="strict",
            market_id="m1",
            observed_at=datetime(2026, 4, 27, 12, 1, tzinfo=UTC),
            mode="paper",
            paper_order_id="o1",
            side="YES",
            status="filled",
            spend_usdc=5.0,
        )
    ]
    positions = [
        PaperPositionEvent(
            run_id="run-1",
            strategy_id="weather_bookmaker_v1",
            profile_id="strict",
            market_id="m1",
            observed_at=datetime(2026, 4, 27, 12, 2, tzinfo=UTC),
            mode="paper",
            paper_position_id="o1",
            quantity=10.0,
            status="filled",
            exposure_usdc=5.0,
            mtm_bid_usdc=6.0,
        )
    ]

    events = build_profile_metric_events(decisions, orders, positions)

    assert len(events) == 1
    event = events[0]
    assert event.table == "profile_metrics"
    assert event.decision_count == 2
    assert event.trade_count == 2
    assert event.skip_count == 1
    assert event.exposure_usdc == 5.0
    assert event.net_pnl_usdc == 6.0
    assert event.roi == 1.2
    assert serialize_event(event)["raw"] == '{"order_count":1,"position_count":1}'


def test_build_strategy_metric_events_aggregates_by_strategy() -> None:
    decisions = [_decision("strict", "trade_small", 0.08), _decision("loose", "skip", 0.02)]

    events = build_strategy_metric_events(decisions)

    assert len(events) == 1
    event = events[0]
    assert event.table == "strategy_metrics"
    assert event.strategy_id == "weather_bookmaker_v1"
    assert event.signal_count == 2
    assert event.trade_count == 1
    assert event.skip_count == 1
    assert event.avg_edge == 0.05
    assert serialize_event(event)["observed_at"] == "2026-04-27 12:00:00.000"
