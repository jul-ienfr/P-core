from __future__ import annotations

from typing import Any


def score_trade_capturability(
    trade: dict[str, Any],
    orderbook_context: dict[str, Any] | None,
    *,
    price_tolerance: float = 0.01,
    max_spread: float = 0.10,
    max_tolerated_slippage_bps: float = 250.0,
) -> dict[str, Any]:
    """Score whether a historical trade was plausibly capturable from book evidence.

    This is evidence-only. It never recommends or authorizes an order.
    """
    context = orderbook_context or {}
    reasons: list[str] = []
    base = {"paper_only": True, "live_order_allowed": False}

    if context.get("orderbook_context_available") is False or not context:
        return {
            **base,
            "capturability": "unknown",
            "capturable_score": 0.0,
            "estimated_entry_price": None,
            "estimated_slippage_bps": None,
            "capturability_reasons": ["missing_orderbook_context"],
        }

    side = str(trade.get("side") or trade.get("taker_side") or "BUY").upper()
    trade_price = _to_float(trade.get("price"))
    trade_size = _trade_size(trade)
    spread = _to_float(context.get("spread"))
    best_ask = _to_float(context.get("best_ask"))
    best_bid = _to_float(context.get("best_bid"))
    depth = _to_float(context.get("available_size_at_or_better_price") or context.get("depth_near_touch"))

    if spread is None:
        reasons.append("missing_spread")
    elif spread > max_spread:
        return {
            **base,
            "capturability": "not_capturable",
            "capturable_score": 0.0,
            "estimated_entry_price": _entry_price(side, best_bid, best_ask),
            "estimated_slippage_bps": None,
            "capturability_reasons": ["spread_too_wide"],
        }
    else:
        reasons.append("spread_within_threshold")

    touch_price = _entry_price(side, best_bid, best_ask)
    if touch_price is None or trade_price is None:
        reasons.append("missing_price_evidence")
        capturability = "unknown"
        score = 0.0
        slippage_bps = None
    else:
        if side in {"BUY", "B", "TAKER_BUY"}:
            price_ok = touch_price <= trade_price + price_tolerance
            slippage_bps = max(0.0, (touch_price - trade_price) / trade_price * 10_000.0) if trade_price else None
        else:
            price_ok = touch_price >= trade_price - price_tolerance
            slippage_bps = max(0.0, (trade_price - touch_price) / trade_price * 10_000.0) if trade_price else None
        if price_ok:
            reasons.append("touch_price_within_trade_tolerance")
        else:
            reasons.append("touch_price_outside_trade_tolerance")

        context_slippage = _to_float(context.get("estimated_slippage_bps"))
        if context_slippage is not None:
            slippage_bps = context_slippage
        if slippage_bps is not None and slippage_bps <= max_tolerated_slippage_bps:
            reasons.append("slippage_within_tolerance")
        elif slippage_bps is not None:
            reasons.append("slippage_too_high")

        if depth is None:
            reasons.append("missing_depth")
            depth_ok = False
        else:
            depth_ok = trade_size is None or depth >= trade_size
            reasons.append("sufficient_depth" if depth_ok else "insufficient_depth")

        if price_ok and depth_ok and (slippage_bps is None or slippage_bps <= max_tolerated_slippage_bps):
            capturability = "capturable"
            score = 1.0
        elif price_ok or depth_ok:
            capturability = "maybe"
            score = 0.5
        else:
            capturability = "not_capturable"
            score = 0.0

    estimated_entry_price = _to_float(context.get("estimated_entry_price"))
    if estimated_entry_price is None:
        estimated_entry_price = touch_price

    return {
        **base,
        "capturability": capturability,
        "capturable_score": round(score, 4),
        "estimated_entry_price": _round_price(estimated_entry_price),
        "estimated_slippage_bps": _round_bps(slippage_bps),
        "capturability_reasons": reasons,
    }


def _trade_size(trade: dict[str, Any]) -> float | None:
    for key in ("size", "shares", "amount"):
        value = _to_float(trade.get(key))
        if value is not None:
            return value
    notional = _to_float(trade.get("notional_usd") or trade.get("notional_usdc") or trade.get("usdc"))
    price = _to_float(trade.get("price"))
    if notional is not None and price not in (None, 0):
        return notional / price
    return None


def _entry_price(side: str, best_bid: float | None, best_ask: float | None) -> float | None:
    if side in {"SELL", "S", "TAKER_SELL"}:
        return best_bid
    return best_ask


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _round_price(value: float | None) -> float | None:
    return None if value is None else round(float(value), 6)


def _round_bps(value: float | None) -> float | None:
    return None if value is None else round(float(value), 2)
