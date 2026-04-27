from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Iterable

from prediction_core.analytics.events import (
    PaperOrderEvent,
    PaperPositionEvent,
    ProfileDecisionEvent,
    ProfileMetricEvent,
    StrategyMetricEvent,
)

_TRADE_STATUSES = {"trade", "trade_small", "filled", "partial"}
_SKIP_STATUSES = {"skip", "skipped", "skipped_price_moved", "cancelled", "watch"}


def _observed_at(default: datetime | None, decisions: list[ProfileDecisionEvent], orders: list[PaperOrderEvent], positions: list[PaperPositionEvent]) -> datetime:
    if default is not None:
        return default
    timestamps = [event.observed_at for event in [*decisions, *orders, *positions]]
    return max(timestamps) if timestamps else datetime.now(UTC)


def _sum_optional(values: Iterable[float | None]) -> float | None:
    numbers = [float(value) for value in values if value is not None]
    if not numbers:
        return None
    return round(sum(numbers), 6)


def _avg_optional(values: Iterable[float | None]) -> float | None:
    numbers = [float(value) for value in values if value is not None]
    if not numbers:
        return None
    return round(sum(numbers) / len(numbers), 6)


def _is_trade_status(status: str) -> bool:
    normalized = status.lower()
    return normalized in _TRADE_STATUSES or normalized.startswith("trade")


def _is_skip_status(status: str) -> bool:
    normalized = status.lower()
    return normalized in _SKIP_STATUSES or normalized.startswith("skip")


def build_profile_metric_events(
    decisions: Iterable[ProfileDecisionEvent],
    orders: Iterable[PaperOrderEvent] = (),
    positions: Iterable[PaperPositionEvent] = (),
    *,
    observed_at: datetime | None = None,
) -> list[ProfileMetricEvent]:
    """Aggregate deterministic profile_metrics from emitted decision/order/position events."""
    decision_list = list(decisions)
    order_list = list(orders)
    position_list = list(positions)
    grouped: dict[tuple[str, str, str, str], dict[str, list]] = defaultdict(lambda: {"decisions": [], "orders": [], "positions": []})
    for event in decision_list:
        grouped[(event.run_id, event.strategy_id, event.profile_id, event.mode)]["decisions"].append(event)
    for event in order_list:
        grouped[(event.run_id, event.strategy_id, event.profile_id, event.mode)]["orders"].append(event)
    for event in position_list:
        grouped[(event.run_id, event.strategy_id, event.profile_id, event.mode)]["positions"].append(event)

    events: list[ProfileMetricEvent] = []
    for (run_id, strategy_id, profile_id, mode), group in sorted(grouped.items()):
        group_decisions = group["decisions"]
        group_orders = group["orders"]
        group_positions = group["positions"]
        exposure = _sum_optional(position.exposure_usdc for position in group_positions)
        net_pnl = _sum_optional(position.mtm_bid_usdc for position in group_positions)
        roi = round(net_pnl / exposure, 6) if exposure and net_pnl is not None else None
        trade_count = sum(1 for decision in group_decisions if _is_trade_status(decision.decision_status)) + sum(
            1 for order in group_orders if _is_trade_status(order.status)
        )
        skip_count = sum(1 for decision in group_decisions if _is_skip_status(decision.decision_status)) + sum(
            1 for order in group_orders if _is_skip_status(order.status)
        )
        events.append(
            ProfileMetricEvent(
                run_id=run_id,
                strategy_id=strategy_id,
                profile_id=profile_id,
                observed_at=_observed_at(observed_at, group_decisions, group_orders, group_positions),
                mode=mode,
                decision_count=len(group_decisions),
                trade_count=trade_count,
                skip_count=skip_count,
                exposure_usdc=exposure,
                gross_pnl_usdc=net_pnl,
                net_pnl_usdc=net_pnl,
                roi=roi,
                raw={"order_count": len(group_orders), "position_count": len(group_positions)},
            )
        )
    return events


def build_strategy_metric_events(
    decisions: Iterable[ProfileDecisionEvent],
    orders: Iterable[PaperOrderEvent] = (),
    positions: Iterable[PaperPositionEvent] = (),
    *,
    observed_at: datetime | None = None,
) -> list[StrategyMetricEvent]:
    """Aggregate deterministic strategy_metrics from emitted decision/order/position events."""
    decision_list = list(decisions)
    order_list = list(orders)
    position_list = list(positions)
    grouped: dict[tuple[str, str, str], dict[str, list]] = defaultdict(lambda: {"decisions": [], "orders": [], "positions": []})
    for event in decision_list:
        grouped[(event.run_id, event.strategy_id, event.mode)]["decisions"].append(event)
    for event in order_list:
        grouped[(event.run_id, event.strategy_id, event.mode)]["orders"].append(event)
    for event in position_list:
        grouped[(event.run_id, event.strategy_id, event.mode)]["positions"].append(event)

    events: list[StrategyMetricEvent] = []
    for (run_id, strategy_id, mode), group in sorted(grouped.items()):
        group_decisions = group["decisions"]
        group_orders = group["orders"]
        group_positions = group["positions"]
        exposure = _sum_optional(position.exposure_usdc for position in group_positions)
        net_pnl = _sum_optional(position.mtm_bid_usdc for position in group_positions)
        trade_count = sum(1 for decision in group_decisions if _is_trade_status(decision.decision_status)) + sum(
            1 for order in group_orders if _is_trade_status(order.status)
        )
        skip_count = sum(1 for decision in group_decisions if _is_skip_status(decision.decision_status)) + sum(
            1 for order in group_orders if _is_skip_status(order.status)
        )
        events.append(
            StrategyMetricEvent(
                run_id=run_id,
                strategy_id=strategy_id,
                observed_at=_observed_at(observed_at, group_decisions, group_orders, group_positions),
                mode=mode,
                signal_count=len(group_decisions),
                trade_count=trade_count,
                skip_count=skip_count,
                avg_edge=_avg_optional(decision.edge for decision in group_decisions),
                gross_pnl_usdc=net_pnl,
                net_pnl_usdc=net_pnl,
                exposure_usdc=exposure,
                raw={"order_count": len(group_orders), "position_count": len(group_positions)},
            )
        )
    return events
