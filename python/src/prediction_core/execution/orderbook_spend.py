from __future__ import annotations

from typing import Any


def normalize_orderbook_asks(orderbook: dict[str, Any] | None, *, side: str) -> list[dict[str, float]]:
    if not isinstance(orderbook, dict):
        return []
    side_key = str(side or "YES").strip().lower()
    candidates = _side_levels(orderbook, side_key=side_key, suffix="asks", level_suffix="ask_levels")
    if not candidates and side_key == "yes":
        value = orderbook.get("asks") or orderbook.get("ask_levels")
        if isinstance(value, list):
            candidates = value
    return _normalize_levels(candidates, reverse=False)


def normalize_orderbook_bids(orderbook: dict[str, Any] | None, *, side: str) -> list[dict[str, float]]:
    if not isinstance(orderbook, dict):
        return []
    side_key = str(side or "YES").strip().lower()
    candidates = _side_levels(orderbook, side_key=side_key, suffix="bids", level_suffix="bid_levels")
    if not candidates and side_key == "yes":
        value = orderbook.get("bids") or orderbook.get("bid_levels")
        if isinstance(value, list):
            candidates = value
    return _normalize_levels(candidates, reverse=True)


def simulate_orderbook_fill(
    orderbook: dict[str, Any] | None,
    *,
    side: str,
    spend_usd: float,
    probability_edge: float | None = None,
    strict_limit: float | None = None,
) -> dict[str, Any]:
    side_label = str(side or "YES").upper()
    requested_spend = round(max(float(spend_usd or 0.0), 0.0), 6)
    asks = normalize_orderbook_asks(orderbook, side=side_label)
    if requested_spend <= 0.0 or not asks:
        return {
            "side": side_label,
            "requested_spend": requested_spend,
            "top_ask": None,
            "avg_fill_price": None,
            "fillable_spend": 0.0,
            "levels_used": 0,
            "slippage_from_top_ask": None,
            "edge_after_fill": None,
            "execution_blocker": "missing_tradeable_quote",
            "fill_status": "empty_book",
        }

    top_ask = asks[0]["price"]
    remaining = requested_spend
    filled_spend = 0.0
    filled_shares = 0.0
    levels_used = 0
    for level in asks:
        if remaining <= 1e-12:
            break
        spend_here = min(remaining, level["price"] * level["size"])
        if spend_here <= 0.0:
            continue
        filled_spend += spend_here
        filled_shares += spend_here / level["price"]
        remaining -= spend_here
        levels_used += 1

    if filled_spend <= 0.0 or filled_shares <= 0.0:
        avg_fill_price = None
        slippage = None
        edge_after_fill = None
    else:
        avg_fill_price = round(filled_spend / filled_shares, 6)
        slippage = round(avg_fill_price - top_ask, 6)
        edge_after_fill = None if probability_edge is None else round(float(probability_edge) - slippage, 6)

    fill_status = "filled" if filled_spend + 1e-9 >= requested_spend else "partial_fill"
    blocker = None
    if strict_limit is not None and top_ask > float(strict_limit):
        blocker = "strict_limit_price_exceeded"
    elif fill_status != "filled":
        blocker = "insufficient_executable_depth"
    elif edge_after_fill is not None and edge_after_fill <= 0.0:
        blocker = "edge_destroyed_by_fill"

    return {
        "side": side_label,
        "requested_spend": requested_spend,
        "top_ask": round(top_ask, 6),
        "avg_fill_price": avg_fill_price,
        "fillable_spend": round(filled_spend, 6),
        "levels_used": levels_used,
        "slippage_from_top_ask": slippage,
        "edge_after_fill": edge_after_fill,
        "execution_blocker": blocker,
        "fill_status": fill_status,
    }


def rust_compatible_orderbook_payload(orderbook: dict[str, Any] | None, *, side: str) -> dict[str, list[dict[str, float]]]:
    bids = normalize_orderbook_bids(orderbook, side=side)
    asks = normalize_orderbook_asks(orderbook, side=side)
    return {
        "bids": [{"price": level["price"], "quantity": level["size"]} for level in bids],
        "asks": [{"price": level["price"], "quantity": level["size"]} for level in asks],
    }


def _side_levels(orderbook: dict[str, Any], *, side_key: str, suffix: str, level_suffix: str) -> list[Any]:
    for key in (f"{side_key}_{suffix}", f"{side_key}{suffix.capitalize()}", f"{side_key}_{level_suffix}"):
        value = orderbook.get(key)
        if isinstance(value, list):
            return value
    nested = orderbook.get(side_key) or orderbook.get(side_key.upper())
    if isinstance(nested, dict):
        for key in (suffix, level_suffix):
            value = nested.get(key)
            if isinstance(value, list):
                return value
    return []


def _normalize_levels(candidates: list[Any], *, reverse: bool) -> list[dict[str, float]]:
    levels: list[dict[str, float]] = []
    for level in candidates:
        if not isinstance(level, dict):
            continue
        price = _optional_float(level.get("price"))
        size = _optional_float(level.get("size", level.get("quantity")))
        if price is None or size is None or price <= 0.0 or size <= 0.0:
            continue
        levels.append({"price": price, "size": size})
    return sorted(levels, key=lambda item: item["price"], reverse=reverse)


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
