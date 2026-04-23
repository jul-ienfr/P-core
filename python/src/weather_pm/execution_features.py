from __future__ import annotations

from typing import Any

from weather_pm.models import ExecutionFeatures


def build_execution_features(raw_market: dict[str, Any]) -> ExecutionFeatures:
    best_bid = _as_float(raw_market.get("best_bid"))
    best_ask = _as_float(raw_market.get("best_ask"))
    spread = round(max(best_ask - best_bid, 0.0), 2)
    volume_usd = _as_float(raw_market.get("volume", raw_market.get("volume_usd")))
    hours_to_resolution = _optional_float(raw_market.get("hours_to_resolution"))
    target_order_size_usd = _resolve_target_order_size(raw_market, volume_usd)
    order_book_depth_usd = round(_order_book_depth_usd(raw_market), 2)
    fillable_size_usd = round(min(target_order_size_usd, order_book_depth_usd), 2) if order_book_depth_usd > 0 else round(target_order_size_usd, 2)
    transaction_fee_bps = round(_as_float(raw_market.get("taker_fee_bps", raw_market.get("transaction_fee_bps"))), 2)
    deposit_fee_usd = round(_as_float(raw_market.get("deposit_fee_usd")), 2)
    withdrawal_fee_usd = round(_as_float(raw_market.get("withdrawal_fee_usd")), 2)
    expected_slippage_bps = round(_expected_slippage_bps(spread=spread, volume_usd=volume_usd, target_order_size_usd=fillable_size_usd, order_book_depth_usd=order_book_depth_usd), 2)
    spread_cost_bps = round(_spread_cost_bps(spread=spread, order_book_depth_usd=order_book_depth_usd), 2)
    all_in_cost_usd = round(fillable_size_usd * ((transaction_fee_bps + expected_slippage_bps + spread_cost_bps) / 10000.0) + deposit_fee_usd + withdrawal_fee_usd, 3)
    all_in_cost_bps = 0.0 if fillable_size_usd <= 0 else round((all_in_cost_usd / fillable_size_usd) * 10000.0, 2)

    execution_speed_required = "high" if hours_to_resolution is not None and hours_to_resolution <= 6 else "low"
    if spread >= 0.06 or volume_usd < 1500:
        slippage_risk = "high"
    elif spread >= 0.04 or volume_usd < 5000 or transaction_fee_bps > 0 or deposit_fee_usd > 0 or withdrawal_fee_usd > 0:
        slippage_risk = "medium"
    else:
        slippage_risk = "low"

    return ExecutionFeatures(
        spread=spread,
        hours_to_resolution=hours_to_resolution,
        volume_usd=volume_usd,
        fillable_size_usd=fillable_size_usd,
        execution_speed_required=execution_speed_required,
        slippage_risk=slippage_risk,
        transaction_fee_bps=transaction_fee_bps,
        deposit_fee_usd=deposit_fee_usd,
        withdrawal_fee_usd=withdrawal_fee_usd,
        order_book_depth_usd=order_book_depth_usd,
        expected_slippage_bps=expected_slippage_bps,
        all_in_cost_bps=all_in_cost_bps,
        all_in_cost_usd=all_in_cost_usd,
    )


def _resolve_target_order_size(raw_market: dict[str, Any], volume_usd: float) -> float:
    explicit = _optional_float(raw_market.get("target_order_size_usd"))
    if explicit is not None:
        return max(explicit, 0.0)
    return max(round(volume_usd * 0.01, 2), 0.0)


def _order_book_depth_usd(raw_market: dict[str, Any]) -> float:
    asks = raw_market.get("asks")
    return _book_side_depth_usd(asks)

def _book_side_depth_usd(levels: Any) -> float:
    if not isinstance(levels, list):
        return 0.0
    total = 0.0
    for level in levels:
        if not isinstance(level, dict):
            continue
        price = _as_float(level.get("price"))
        size = _as_float(level.get("size"))
        total += price * size
    return total


def _spread_cost_bps(*, spread: float, order_book_depth_usd: float) -> float:
    if order_book_depth_usd > 0:
        return spread * 2500.0
    return spread * 5000.0


def _expected_slippage_bps(*, spread: float, volume_usd: float, target_order_size_usd: float, order_book_depth_usd: float) -> float:
    if target_order_size_usd <= 0:
        return 0.0
    if order_book_depth_usd > 0 and target_order_size_usd <= order_book_depth_usd:
        return 0.0
    spread_component = spread * 2000.0
    liquidity_component = 0.0 if volume_usd <= 0 else min(target_order_size_usd / volume_usd, 1.0) * 0.0
    return spread_component + liquidity_component


def _as_float(value: Any) -> float:
    if value is None:
        return 0.0
    return float(value)


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)
