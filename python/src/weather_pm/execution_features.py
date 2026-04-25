from __future__ import annotations

from typing import Any

from prediction_core.execution import BookLevel, OrderBookSnapshot, TradingFeeSchedule, TransferFeeSchedule, build_execution_cost_breakdown
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

    canonical_costs = _canonical_execution_costs(raw_market)
    expected_slippage_bps = round(_expected_slippage_bps(spread=spread, volume_usd=volume_usd, target_order_size_usd=fillable_size_usd, order_book_depth_usd=order_book_depth_usd), 2)
    spread_cost_bps = round(_spread_cost_bps(spread=spread, order_book_depth_usd=order_book_depth_usd), 2)
    all_in_cost_usd = round(fillable_size_usd * ((transaction_fee_bps + expected_slippage_bps + spread_cost_bps) / 10000.0) + deposit_fee_usd + withdrawal_fee_usd, 3)
    all_in_cost_bps = 0.0 if fillable_size_usd <= 0 else round((all_in_cost_usd / fillable_size_usd) * 10000.0, 2)
    if canonical_costs is not None:
        expected_slippage_bps = round(_cost_bps(canonical_costs.book_slippage_cost, canonical_costs), 2)
        transaction_fee_bps = round(_cost_bps(canonical_costs.trading_fee_cost, canonical_costs), 2)
        all_in_cost_usd = round(canonical_costs.total_all_in_cost, 3)
        all_in_cost_bps = round(_cost_bps(canonical_costs.total_all_in_cost, canonical_costs), 2)
    cost_risk = _cost_risk(all_in_cost_bps=all_in_cost_bps, all_in_cost_usd=all_in_cost_usd, fillable_size_usd=fillable_size_usd)
    tradeability_status = _tradeability_status(best_effort_reason=best_effort_reason, cost_risk=cost_risk)

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
        quoted_best_bid=canonical_costs.quoted_best_bid if canonical_costs is not None else (best_bid if best_bid > 0.0 else None),
        quoted_best_ask=canonical_costs.quoted_best_ask if canonical_costs is not None else (best_ask if best_ask > 0.0 else None),
        quoted_mid_price=canonical_costs.quoted_mid_price if canonical_costs is not None else (_mid_price(best_bid=best_bid, best_ask=best_ask)),
        estimated_avg_fill_price=canonical_costs.estimated_avg_fill_price if canonical_costs is not None else None,
        estimated_slippage_bps=round(_cost_bps(canonical_costs.book_slippage_cost, canonical_costs), 2) if canonical_costs is not None else expected_slippage_bps,
        estimated_trading_fee_bps=round(_cost_bps(canonical_costs.trading_fee_cost, canonical_costs), 2) if canonical_costs is not None else transaction_fee_bps,
        estimated_total_cost_bps=round(_cost_bps(canonical_costs.total_execution_cost, canonical_costs), 2) if canonical_costs is not None else all_in_cost_bps,
        edge_net_execution=canonical_costs.edge_net_execution if canonical_costs is not None else None,
        edge_net_all_in=canonical_costs.edge_net_all_in if canonical_costs is not None else None,
        best_effort_reason=best_effort_reason,
        tradeability_status=tradeability_status,
        cost_risk=cost_risk,
    )


def _resolve_target_order_size(raw_market: dict[str, Any], volume_usd: float) -> float:
    explicit = _optional_float(raw_market.get("target_order_size_usd"))
    if explicit is not None:
        return max(explicit, 0.0)
    quantity = _optional_float(raw_market.get("requested_quantity"))
    price = _optional_float(raw_market.get("best_ask")) or _optional_float(raw_market.get("yes_price"))
    if quantity is not None and price is not None:
        return max(round(quantity * price, 2), 0.0)
    return max(round(volume_usd * 0.01, 2), 0.0)


def _canonical_execution_costs(raw_market: dict[str, Any]):
    requested_quantity = _optional_float(raw_market.get("requested_quantity"))
    fair_probability = _optional_float(raw_market.get("fair_probability"))
    if requested_quantity is None or fair_probability is None:
        return None
    book = _order_book_snapshot(raw_market)
    if not book.bids and not book.asks:
        return None
    return build_execution_cost_breakdown(
        book=book,
        requested_quantity=requested_quantity,
        side=str(raw_market.get("execution_side") or "buy"),
        fair_probability=fair_probability,
        trading_fees=_trading_fee_schedule(raw_market.get("trading_fees"), raw_market),
        transfer_fees=_transfer_fee_schedule(raw_market.get("transfer_fees"), raw_market),
        liquidity_role=str(raw_market.get("liquidity_role") or "taker"),
    )


def _order_book_snapshot(raw_market: dict[str, Any]) -> OrderBookSnapshot:
    bids = [_book_level(level) for level in _normalized_levels(raw_market.get("bid_levels") or raw_market.get("bids"))]
    asks = [_book_level(level) for level in _normalized_levels(raw_market.get("ask_levels") or raw_market.get("asks"))]
    return OrderBookSnapshot(bids=bids, asks=asks)


def _book_level(level: dict[str, float]) -> BookLevel:
    return BookLevel(price=level["price"], quantity=level["size"])


def _trading_fee_schedule(value: Any, raw_market: dict[str, Any]) -> TradingFeeSchedule | None:
    if isinstance(value, TradingFeeSchedule):
        return value
    if isinstance(value, dict):
        return TradingFeeSchedule(
            maker_bps=_as_float(value.get("maker_bps")),
            taker_bps=_as_float(value.get("taker_bps")),
            min_fee=_as_float(value.get("min_fee")),
        )
    taker_bps = _as_float(raw_market.get("taker_fee_bps", raw_market.get("transaction_fee_bps")))
    if taker_bps <= 0.0:
        return None
    return TradingFeeSchedule(maker_bps=_as_float(raw_market.get("maker_fee_bps")), taker_bps=taker_bps)


def _transfer_fee_schedule(value: Any, raw_market: dict[str, Any]) -> TransferFeeSchedule | None:
    if isinstance(value, TransferFeeSchedule):
        return value
    if isinstance(value, dict):
        return TransferFeeSchedule(
            deposit_fixed=_as_float(value.get("deposit_fixed", value.get("deposit_fee_usd"))),
            deposit_bps=_as_float(value.get("deposit_bps")),
            withdrawal_fixed=_as_float(value.get("withdrawal_fixed", value.get("withdrawal_fee_usd"))),
            withdrawal_bps=_as_float(value.get("withdrawal_bps")),
        )
    if not any(raw_market.get(key) is not None for key in ("deposit_fee_usd", "deposit_fee_bps", "withdrawal_fee_usd", "withdrawal_fee_bps")):
        return None
    return TransferFeeSchedule(
        deposit_fixed=_as_float(raw_market.get("deposit_fee_usd")),
        deposit_bps=_as_float(raw_market.get("deposit_fee_bps")),
        withdrawal_fixed=_as_float(raw_market.get("withdrawal_fee_usd")),
        withdrawal_bps=_as_float(raw_market.get("withdrawal_fee_bps")),
    )


def _cost_bps(cost: float, costs: Any) -> float:
    if costs.estimated_filled_quantity <= 0 or costs.estimated_avg_fill_price is None:
        return 0.0
    notional = costs.estimated_filled_quantity * costs.estimated_avg_fill_price
    if notional <= 0.0:
        return 0.0
    return (float(cost) / notional) * 10000.0


def _mid_price(*, best_bid: float, best_ask: float) -> float | None:
    if best_bid <= 0.0 or best_ask <= 0.0:
        return None
    return round((best_bid + best_ask) / 2.0, 6)


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


def _tradeability_status(*, best_effort_reason: str | None, cost_risk: str) -> str:
    if best_effort_reason is not None:
        return "untradeable"
    if cost_risk == "high":
        return "degraded"
    return "tradeable"


def _cost_risk(*, all_in_cost_bps: float, all_in_cost_usd: float, fillable_size_usd: float) -> str:
    if fillable_size_usd <= 0.0 or all_in_cost_usd <= 0.0:
        return "none"
    if all_in_cost_bps >= 300.0:
        return "high"
    if all_in_cost_bps >= 100.0:
        return "medium"
    return "low"


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
