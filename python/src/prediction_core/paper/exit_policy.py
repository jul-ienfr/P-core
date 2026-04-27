from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ExitPolicy:
    """Pure paper-exit recommendation thresholds.

    Values are fractional percentages, e.g. ``0.20`` means 20%. The policy only
    annotates paper positions with review recommendations; it never places,
    cancels, or mutates live orders.
    """

    stop_loss_pct: float = 0.20
    trailing_stop_pct: float = 0.25
    breakeven_after_profit_pct: float = 0.25


@dataclass(frozen=True)
class PaperPositionSnapshot:
    entry_price: float | None
    current_price: float | None
    highest_price: float | None = None
    filled_usdc: float = 0.0
    shares: float = 0.0
    status: str = "filled"


@dataclass(frozen=True)
class ExitDecision:
    action: str
    reason: str
    trigger_price: float | None
    current_price: float | None
    unrealized_return_pct: float | None


def evaluate_exit_policy(snapshot: PaperPositionSnapshot, policy: ExitPolicy | None = None) -> ExitDecision:
    """Return a pure paper exit recommendation for an open paper position."""

    policy = policy or ExitPolicy()
    entry_price = _positive_float(snapshot.entry_price)
    current_price = _positive_float(snapshot.current_price)
    filled_usdc = _positive_float(snapshot.filled_usdc) or 0.0
    shares = _positive_float(snapshot.shares) or 0.0
    status = str(snapshot.status or "").lower()

    if status not in {"filled", "partial"} or filled_usdc <= 0.0 or shares <= 0.0:
        return ExitDecision("HOLD", "not_open_position", None, current_price, None)
    if entry_price is None or current_price is None:
        return ExitDecision("HOLD", "missing_price", None, current_price, None)

    high = _positive_float(snapshot.highest_price) or max(entry_price, current_price)
    unrealized_return = round((current_price - entry_price) / entry_price, 6)

    stop_loss_price = round(entry_price * (1.0 - max(policy.stop_loss_pct, 0.0)), 6)
    if current_price <= stop_loss_price:
        return ExitDecision("EXIT_REVIEW_PAPER", "stop_loss", stop_loss_price, round(current_price, 6), unrealized_return)

    trailing_stop_pct = max(policy.trailing_stop_pct, 0.0)
    trailing_stop_price = round(high * (1.0 - trailing_stop_pct), 6)
    if high > entry_price and current_price <= trailing_stop_price:
        return ExitDecision("EXIT_REVIEW_PAPER", "trailing_stop", trailing_stop_price, round(current_price, 6), unrealized_return)

    profit_trigger = max(policy.breakeven_after_profit_pct, 0.0)
    breakeven_buffer = min(0.02, max(profit_trigger, 0.0) / 10.0)
    breakeven_floor = round(entry_price * (1.0 + breakeven_buffer), 6)
    if high >= entry_price * (1.0 + profit_trigger) and current_price <= breakeven_floor:
        return ExitDecision("EXIT_REVIEW_PAPER", "breakeven_after_profit", round(entry_price, 6), round(current_price, 6), unrealized_return)

    return ExitDecision("HOLD", "no_exit_trigger", None, round(current_price, 6), unrealized_return)


def annotate_order_with_exit_policy(order: dict[str, Any], policy: ExitPolicy | None = None) -> dict[str, Any]:
    """Return a shallow-copy order annotated with a paper exit-policy decision."""

    annotated = dict(order)
    decision = evaluate_exit_policy(position_snapshot_from_order(order), policy)
    annotated["exit_policy"] = asdict(decision)
    annotated.setdefault("operator_action", str(order.get("operator_action") or "HOLD"))
    return annotated


def position_snapshot_from_order(order: dict[str, Any]) -> PaperPositionSnapshot:
    entry_price = _positive_float(order.get("avg_fill_price"))
    if entry_price is None:
        entry_price = _entry_price_from_cost(order)
    current_price = _current_price_from_order(order)
    highest_price = _highest_price_from_order(order, current_price=current_price, entry_price=entry_price)
    return PaperPositionSnapshot(
        entry_price=entry_price,
        current_price=current_price,
        highest_price=highest_price,
        filled_usdc=_positive_float(order.get("filled_usdc")) or 0.0,
        shares=_positive_float(order.get("shares")) or 0.0,
        status=str(order.get("status") or ""),
    )


def _entry_price_from_cost(order: dict[str, Any]) -> float | None:
    shares = _positive_float(order.get("shares"))
    filled = _positive_float(order.get("filled_usdc"))
    if shares is None or filled is None:
        return None
    return round(filled / shares, 6)


def _current_price_from_order(order: dict[str, Any]) -> float | None:
    shares = _positive_float(order.get("shares"))
    mtm = _positive_float(order.get("mtm_usdc"))
    if shares is not None and mtm is not None:
        return round(mtm / shares, 6)
    for key in ("best_bid", "actual_refresh_price", "paper_exit_price"):
        value = _positive_float(order.get(key))
        if value is not None:
            return round(value, 6)
    return None


def _highest_price_from_order(order: dict[str, Any], *, current_price: float | None, entry_price: float | None) -> float | None:
    candidates = [value for value in (current_price, entry_price) if value is not None]
    history = order.get("refresh_history")
    if isinstance(history, list):
        for item in history:
            if not isinstance(item, dict):
                continue
            for key in ("best_bid", "actual_refresh_price", "paper_exit_price"):
                value = _positive_float(item.get(key))
                if value is not None:
                    candidates.append(value)
    return round(max(candidates), 6) if candidates else None


def _positive_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed <= 0.0:
        return None
    return parsed
