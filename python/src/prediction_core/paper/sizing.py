from __future__ import annotations

from typing import Any


def derive_filled_execution(
    *,
    filled_quantity: float | None,
    fill_price: float | None,
    requested_quantity: float,
    yes_price: float | None,
    score_bundle: dict[str, Any] | None,
) -> tuple[float, float]:
    if (filled_quantity is None) != (fill_price is None):
        raise ValueError("filled_quantity and fill_price must be provided together")

    if filled_quantity is None:
        if score_bundle is None or yes_price is None:
            raise ValueError("filled_quantity and fill_price are required when no scored question is provided")
        decision_info = score_bundle.get("decision")
        decision_status = decision_info.get("status") if isinstance(decision_info, dict) else None
        if not isinstance(decision_status, str) or not decision_status:
            raise ValueError("decision status is required for auto fill")
        if decision_status in {"trade", "trade_small"}:
            filled_quantity = requested_quantity
            fill_price = yes_price
        else:
            filled_quantity = 0.0
            fill_price = yes_price

    if filled_quantity < 0:
        raise ValueError("filled_quantity must be >= 0")
    if filled_quantity > requested_quantity:
        raise ValueError("filled_quantity must be <= requested_quantity")
    assert fill_price is not None
    return float(filled_quantity), float(fill_price)


def derive_requested_quantity(
    *,
    requested_quantity: float | None,
    bankroll_usd: float | None,
    yes_price: float | None,
    score_bundle: dict[str, Any] | None,
) -> float:
    if requested_quantity is not None:
        if requested_quantity < 0:
            raise ValueError("requested_quantity must be >= 0")
        return float(requested_quantity)

    if bankroll_usd is None:
        raise ValueError("requested_quantity is required when bankroll_usd or scored question sizing is unavailable")
    if bankroll_usd < 0:
        raise ValueError("bankroll_usd must be >= 0")
    if score_bundle is None or yes_price is None:
        raise ValueError("bankroll_usd requires question and yes_price for scored sizing")
    if yes_price <= 0:
        raise ValueError("yes_price must be > 0 for bankroll sizing")

    decision_info = score_bundle.get("decision")
    if not isinstance(decision_info, dict):
        raise ValueError("max_position_pct_bankroll is required for bankroll sizing")

    max_position_pct_bankroll = decision_info.get("max_position_pct_bankroll")
    try:
        max_position_pct_bankroll_value = float(max_position_pct_bankroll)
    except (TypeError, ValueError) as exc:
        raise ValueError("max_position_pct_bankroll is required for bankroll sizing") from exc

    if max_position_pct_bankroll_value <= 0:
        return 0.0

    target_notional = bankroll_usd * max_position_pct_bankroll_value
    return round(target_notional / yes_price, 6)
