from __future__ import annotations

from typing import Any

from weather_pm.models import ExecutionFeatures


def build_execution_features(raw_market: dict[str, Any]) -> ExecutionFeatures:
    best_bid = _as_float(raw_market.get("best_bid"))
    best_ask = _as_float(raw_market.get("best_ask"))
    yes_price = _optional_float(raw_market.get("yes_price"))
    spread = round(_resolve_spread(best_bid=best_bid, best_ask=best_ask, yes_price=yes_price), 2)
    volume_usd = _as_float(raw_market.get("volume", raw_market.get("volume_usd")))
    hours_to_resolution = _optional_float(raw_market.get("hours_to_resolution"))
    target_order_size_usd = _resolve_target_order_size(raw_market, volume_usd)
    order_book_depth_usd = round(_order_book_depth_usd(raw_market, best_bid=best_bid, best_ask=best_ask), 2)
    fillable_size_usd = round(min(target_order_size_usd, order_book_depth_usd), 2) if order_book_depth_usd > 0 else round(target_order_size_usd, 2)
    max_impact_bps = round(_resolve_max_impact_bps(raw_market), 2)
    transaction_fee_bps = round(_as_float(raw_market.get("taker_fee_bps", raw_market.get("transaction_fee_bps"))), 2)
    deposit_fee_usd = round(_as_float(raw_market.get("deposit_fee_usd")), 2)
    withdrawal_fee_usd = round(_as_float(raw_market.get("withdrawal_fee_usd")), 2)

    best_effort_reason = _best_effort_reason(
        best_bid=best_bid,
        best_ask=best_ask,
        yes_price=_optional_float(raw_market.get("yes_price")),
        hours_to_resolution=hours_to_resolution,
        fillable_size_usd=fillable_size_usd,
    )
    if best_effort_reason == "missing_tradeable_quote":
        fillable_size_usd = 0.0

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
        max_impact_bps=max_impact_bps,
        transaction_fee_bps=transaction_fee_bps,
        deposit_fee_usd=deposit_fee_usd,
        withdrawal_fee_usd=withdrawal_fee_usd,
        order_book_depth_usd=order_book_depth_usd,
        expected_slippage_bps=expected_slippage_bps,
        all_in_cost_bps=all_in_cost_bps,
        all_in_cost_usd=all_in_cost_usd,
        best_effort_reason=best_effort_reason,
    )


def _resolve_target_order_size(raw_market: dict[str, Any], volume_usd: float) -> float:
    explicit = _optional_float(raw_market.get("target_order_size_usd"))
    if explicit is not None:
        return max(explicit, 0.0)
    return max(round(volume_usd * 0.01, 2), 0.0)


def _resolve_spread(*, best_bid: float, best_ask: float, yes_price: float | None) -> float:
    if best_bid > 0.0 and best_ask > 0.0:
        return max(best_ask - best_bid, 0.0)
    if best_bid <= 0.0 and best_ask > 0.0 and yes_price is not None and yes_price > 0.0:
        return max(best_ask - yes_price, 0.0)
    if best_ask <= 0.0 and best_bid > 0.0 and yes_price is not None and yes_price > 0.0:
        return max(yes_price - best_bid, 0.0)
    return 0.0


def _order_book_depth_usd(raw_market: dict[str, Any], *, best_bid: float, best_ask: float) -> float:
    max_impact_bps = _resolve_max_impact_bps(raw_market)

    ask_depth = _optional_float(raw_market.get("ask_depth_usd"))
    bid_depth = _optional_float(raw_market.get("bid_depth_usd"))
    if ask_depth is not None or bid_depth is not None:
        capped_ask_depth = _impact_capped_side_depth_usd(
            raw_market.get("asks"),
            reference_price=best_ask,
            side="ask",
            max_impact_bps=max_impact_bps,
            fallback_depth_usd=ask_depth or 0.0,
        )
        capped_bid_depth = _impact_capped_side_depth_usd(
            raw_market.get("bids"),
            reference_price=best_bid,
            side="bid",
            max_impact_bps=max_impact_bps,
            fallback_depth_usd=bid_depth or 0.0,
        )
        return _two_sided_depth_usd(capped_ask_depth, capped_bid_depth)

    asks = raw_market.get("asks")
    bids = raw_market.get("bids")
    capped_ask_depth = _impact_capped_side_depth_usd(asks, reference_price=best_ask, side="ask", max_impact_bps=max_impact_bps)
    capped_bid_depth = _impact_capped_side_depth_usd(bids, reference_price=best_bid, side="bid", max_impact_bps=max_impact_bps)
    return _two_sided_depth_usd(capped_ask_depth, capped_bid_depth)


def _resolve_max_impact_bps(raw_market: dict[str, Any]) -> float:
    explicit = _optional_float(raw_market.get("max_impact_bps"))
    if explicit is not None and explicit > 0.0:
        return explicit
    return 150.0


def _impact_capped_side_depth_usd(
    levels: Any,
    *,
    reference_price: float,
    side: str,
    max_impact_bps: float,
    fallback_depth_usd: float = 0.0,
) -> float:
    normalized_levels = _normalized_levels(levels)
    if not normalized_levels:
        return max(fallback_depth_usd, 0.0)

    if reference_price <= 0.0:
        return 0.0

    max_fraction = max_impact_bps / 10000.0
    total = 0.0
    for level in normalized_levels:
        price = level["price"]
        if side == "ask":
            impact_fraction = (price - reference_price) / reference_price
        else:
            impact_fraction = (reference_price - price) / reference_price
        if impact_fraction > max_fraction:
            break
        total += price * level["size"]
    return round(total, 2)


def _two_sided_depth_usd(ask_depth_usd: float, bid_depth_usd: float) -> float:
    positive_depths = [depth for depth in (ask_depth_usd, bid_depth_usd) if depth > 0.0]
    if not positive_depths:
        return 0.0
    if len(positive_depths) == 1:
        return positive_depths[0]
    return min(positive_depths)


def _normalized_levels(levels: Any) -> list[dict[str, float]]:
    if not isinstance(levels, list):
        return []

    normalized: list[dict[str, float]] = []
    for level in levels:
        if not isinstance(level, dict):
            continue
        price = _as_float(level.get("price"))
        size = _as_float(level.get("size"))
        if price <= 0.0 or size <= 0.0:
            continue
        normalized.append({"price": price, "size": size})
    return normalized


def _book_side_depth_usd(levels: Any) -> float:
    total = 0.0
    for level in _normalized_levels(levels):
        total += level["price"] * level["size"]
    return total


def _spread_cost_bps(*, spread: float, order_book_depth_usd: float) -> float:
    if order_book_depth_usd > 0:
        return spread * 2500.0
    return spread * 5000.0


def _best_effort_reason(*, best_bid: float, best_ask: float, yes_price: float | None, hours_to_resolution: float | None, fillable_size_usd: float) -> str | None:
    if hours_to_resolution is not None and hours_to_resolution <= 0:
        return "market_already_resolving_or_resolved"
    if fillable_size_usd < 25.0:
        return "missing_tradeable_quote"
    if best_bid <= 0.0 and best_ask <= 0.0 and (yes_price is None or yes_price <= 0.0):
        return "missing_tradeable_quote"
    return None


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
