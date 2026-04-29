from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from weather_pm.capturability import score_trade_capturability

LIMITATIONS = "\n".join(
    [
        "- PMXT hourly L2 archive candidate.",
        "- Telonex full-depth candidate.",
        "- evan-kolberg/prediction-market-backtesting is donor/reference, not framework replacement.",
    ]
)


def enrich_trade_with_orderbook_context(
    trade: dict[str, Any],
    snapshots: Iterable[dict[str, Any]] | dict[str, Any],
    *,
    max_staleness_seconds: int = 3600,
) -> dict[str, Any]:
    base = dict(trade)
    latest = _latest_snapshot_for_trade(trade, snapshots)
    if latest is not None:
        features = compute_orderbook_features(latest, trade=trade)
        return {
            **base,
            "paper_only": True,
            "live_order_allowed": False,
            "orderbook_context_available": True,
            "missing_reason": None,
            "snapshot_timestamp": _snapshot_timestamp(latest) or "latest",
            "staleness_seconds": 0,
            **features,
        }
    nearest = find_nearest_snapshot(trade, snapshots)
    if nearest is None:
        return {**base, **_missing_context("no_snapshot_within_max_staleness")}
    snapshot, staleness = nearest
    if staleness > max_staleness_seconds:
        return {**base, **_missing_context("no_snapshot_within_max_staleness")}

    features = compute_orderbook_features(snapshot, trade=trade)
    context = {
        "paper_only": True,
        "live_order_allowed": False,
        "orderbook_context_available": True,
        "missing_reason": None,
        "snapshot_timestamp": _snapshot_timestamp(snapshot),
        "staleness_seconds": int(staleness),
        **features,
    }
    return {**base, **context}


def find_nearest_snapshot(trade: dict[str, Any], snapshots: Iterable[dict[str, Any]] | dict[str, Any]) -> tuple[dict[str, Any], int] | None:
    trade_ts = _parse_timestamp(trade.get("timestamp") or trade.get("created_at") or trade.get("createdAt"))
    if trade_ts is None:
        return None
    candidates: list[tuple[int, int, dict[str, Any]]] = []
    for index, snapshot in enumerate(_snapshot_rows(snapshots)):
        if not isinstance(snapshot, dict) or not _snapshot_matches_trade(trade, snapshot):
            continue
        snapshot_ts = _parse_timestamp(_snapshot_timestamp(snapshot))
        if snapshot_ts is None:
            continue
        staleness = int(abs((trade_ts - snapshot_ts).total_seconds()))
        candidates.append((staleness, index, snapshot))
    if not candidates:
        return None
    staleness, _index, snapshot = min(candidates, key=lambda item: (item[0], item[1]))
    return snapshot, staleness


def compute_orderbook_features(snapshot: dict[str, Any], *, trade: dict[str, Any] | None = None) -> dict[str, Any]:
    bids = _levels(snapshot, "bids")
    asks = _levels(snapshot, "asks")
    best_bid = bids[0][0] if bids else _to_float(snapshot.get("best_bid"))
    best_ask = asks[0][0] if asks else _to_float(snapshot.get("best_ask"))
    mid = (best_bid + best_ask) / 2.0 if best_bid is not None and best_ask is not None else None
    spread = best_ask - best_bid if best_bid is not None and best_ask is not None else None

    near_touch_bps = _to_float(snapshot.get("near_touch_bps")) or 100.0
    depth_near_touch = _depth_near_touch(bids, asks, best_bid, best_ask, near_touch_bps=near_touch_bps)
    if depth_near_touch is None:
        depth_near_touch = _to_float(snapshot.get("depth_usd") or snapshot.get("depth") or snapshot.get("liquidity"))
    side = str((trade or {}).get("side") or "BUY").upper()
    trade_price = _to_float((trade or {}).get("price"))
    available = _available_at_or_better(side, trade_price, bids, asks)
    entry_5, slippage_5 = _estimate_entry_and_slippage(side, 5.0, trade_price, bids, asks)
    entry_20, slippage_20 = _estimate_entry_and_slippage(side, 20.0, trade_price, bids, asks)
    bid_size = bids[0][1] if bids else None
    ask_size = asks[0][1] if asks else None
    imbalance = None
    microprice = None
    if bid_size is not None and ask_size is not None and (bid_size + ask_size) > 0:
        imbalance = (bid_size - ask_size) / (bid_size + ask_size)
        if best_bid is not None and best_ask is not None:
            microprice = ((best_bid * ask_size) + (best_ask * bid_size)) / (bid_size + ask_size)

    estimated_entry_price = None
    estimated_slippage_bps = None
    trade_size = _trade_size(trade or {})
    if trade_size is not None:
        estimated_entry_price, estimated_slippage_bps = _estimate_entry_and_slippage(side, trade_size, trade_price, bids, asks)

    return {
        "best_bid": _round_price(best_bid),
        "best_ask": _round_price(best_ask),
        "mid": _round_price(mid),
        "spread": _round_price(spread),
        "depth_near_touch": _round_size(depth_near_touch),
        "available_size_at_or_better_price": _round_size(available),
        "estimated_entry_price": _round_price(estimated_entry_price),
        "estimated_slippage_bps": _round_bps(estimated_slippage_bps),
        "estimated_slippage_for_5_usdc": _round_bps(slippage_5),
        "estimated_slippage_for_20_usdc": _round_bps(slippage_20),
        "imbalance": None if imbalance is None else round(imbalance, 6),
        "microprice": _round_price(microprice),
    }


def build_orderbook_context_report(
    trades_payload: dict[str, Any],
    snapshots_payload: dict[str, Any],
    *,
    max_staleness_seconds: int = 3600,
) -> dict[str, Any]:
    trades = _rows_from_payload(trades_payload, "trades")
    snapshots = _snapshots_payload_for_matching(snapshots_payload)
    enriched: list[dict[str, Any]] = []
    for trade in trades:
        row = enrich_trade_with_orderbook_context(trade, snapshots, max_staleness_seconds=max_staleness_seconds)
        row.update(score_trade_capturability(trade, row))
        enriched.append(row)
    with_context = sum(1 for row in enriched if row.get("orderbook_context_available") is True)
    missing = len(enriched) - with_context
    return {
        "paper_only": True,
        "live_order_allowed": False,
        "summary": {
            "paper_only": True,
            "live_order_allowed": False,
            "trades": len(enriched),
            "with_orderbook_context": with_context,
            "missing_orderbook_context": missing,
            "max_staleness_seconds": int(max_staleness_seconds),
        },
        "trades": enriched,
        "limitations": LIMITATIONS,
    }


def write_orderbook_context_report(
    trades_json: str | Path,
    orderbook_snapshots_json: str | Path,
    output_json: str | Path,
    *,
    max_staleness_seconds: int = 3600,
) -> dict[str, Any]:
    trades_payload = json.loads(Path(trades_json).read_text(encoding="utf-8"))
    snapshots_payload = json.loads(Path(orderbook_snapshots_json).read_text(encoding="utf-8"))
    if not isinstance(trades_payload, dict):
        raise ValueError("trades JSON must be an object")
    if not isinstance(snapshots_payload, dict):
        raise ValueError("orderbook snapshots JSON must be an object")
    artifact = build_orderbook_context_report(trades_payload, snapshots_payload, max_staleness_seconds=max_staleness_seconds)
    output_path = Path(output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")
    summary = artifact["summary"]
    return {
        "paper_only": True,
        "live_order_allowed": False,
        "trades": summary["trades"],
        "with_orderbook_context": summary["with_orderbook_context"],
        "missing_orderbook_context": summary["missing_orderbook_context"],
    }


def _latest_snapshot_for_trade(trade: dict[str, Any], snapshots: Iterable[dict[str, Any]] | dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(snapshots, dict):
        return None
    wanted = _trade_snapshot_keys(trade)
    for key in wanted:
        value = snapshots.get(key)
        if isinstance(value, dict):
            row = dict(value)
            row.setdefault("market_id", key)
            return row
    return None


def _trade_snapshot_keys(trade: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    for key in ("market_id", "id", "condition_id", "token_id", "asset", "slug"):
        value = trade.get(key)
        if value is not None:
            text = str(value).strip()
            if text and text not in keys:
                keys.append(text)
    resolution = trade.get("resolution")
    if isinstance(resolution, dict):
        for key in ("primary_key", "market_id", "marketId", "condition_id", "conditionId", "token_id", "tokenId", "matched_key", "slug"):
            value = resolution.get(key)
            if value is not None:
                text = str(value).strip()
                if text and text not in keys:
                    keys.append(text)
    return keys


def _missing_context(reason: str) -> dict[str, Any]:
    keys = (
        "snapshot_timestamp",
        "staleness_seconds",
        "best_bid",
        "best_ask",
        "mid",
        "spread",
        "depth_near_touch",
        "available_size_at_or_better_price",
        "estimated_entry_price",
        "estimated_slippage_bps",
        "estimated_slippage_for_5_usdc",
        "estimated_slippage_for_20_usdc",
        "imbalance",
        "microprice",
    )
    return {
        "paper_only": True,
        "live_order_allowed": False,
        "orderbook_context_available": False,
        "missing_reason": reason,
        **{key: None for key in keys},
    }


def _snapshot_matches_trade(trade: dict[str, Any], snapshot: dict[str, Any]) -> bool:
    for key in ("token_id", "asset", "market_id", "condition_id"):
        trade_value = trade.get(key)
        snap_value = snapshot.get(key)
        if trade_value is not None and snap_value is not None and str(trade_value) != str(snap_value):
            return False
    return True


def _snapshot_timestamp(snapshot: dict[str, Any]) -> Any:
    for key in ("timestamp", "snapshot_timestamp", "ts", "created_at", "createdAt"):
        if snapshot.get(key) is not None:
            return snapshot.get(key)
    return None


def _snapshots_payload_for_matching(payload: dict[str, Any]) -> list[dict[str, Any]] | dict[str, Any]:
    for key in ("snapshots", "orderbook_snapshots", "books", "orderbooks"):
        rows = payload.get(key)
        if isinstance(rows, dict):
            return rows
        if isinstance(rows, list):
            return [dict(row) for row in rows if isinstance(row, dict)]
    if payload and all(isinstance(value, dict) for value in payload.values()):
        return payload
    return []


def _rows_from_payload(payload: dict[str, Any], preferred_key: str) -> list[dict[str, Any]]:
    rows = payload.get(preferred_key)
    if rows is None and preferred_key == "snapshots":
        rows = payload.get("orderbook_snapshots") or payload.get("books")
    if rows is None and preferred_key == "trades":
        rows = payload.get("data")
    if isinstance(rows, list):
        return [dict(row) for row in rows if isinstance(row, dict)]
    if isinstance(rows, dict) and preferred_key == "snapshots":
        return _snapshot_rows(rows)
    return []


def _snapshot_rows(snapshots: Iterable[dict[str, Any]] | dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(snapshots, dict):
        rows: list[dict[str, Any]] = []
        for key, value in snapshots.items():
            if isinstance(value, dict):
                row = dict(value)
                row.setdefault("market_id", key)
                rows.append(row)
        return rows
    return [dict(row) for row in snapshots if isinstance(row, dict)]


def _levels(snapshot: dict[str, Any], key: str) -> list[tuple[float, float]]:
    raw = snapshot.get(key) or snapshot.get(key[:-1]) or []
    levels: list[tuple[float, float]] = []
    if not isinstance(raw, list):
        return levels
    for level in raw:
        price: Any = None
        size: Any = None
        if isinstance(level, dict):
            price = level.get("price") or level.get("p")
            size = level.get("size") or level.get("s") or level.get("quantity")
        elif isinstance(level, (list, tuple)) and len(level) >= 2:
            price, size = level[0], level[1]
        price_f = _to_float(price)
        size_f = _to_float(size)
        if price_f is not None and size_f is not None:
            levels.append((price_f, size_f))
    reverse = key == "bids"
    return sorted(levels, key=lambda item: item[0], reverse=reverse)


def _depth_near_touch(bids: list[tuple[float, float]], asks: list[tuple[float, float]], best_bid: float | None, best_ask: float | None, *, near_touch_bps: float) -> float | None:
    total = 0.0
    seen = False
    if best_bid is not None:
        min_bid = best_bid * (1.0 - near_touch_bps / 10_000.0)
        for price, size in bids:
            if price >= min_bid:
                total += size
                seen = True
    if best_ask is not None:
        max_ask = best_ask * (1.0 + near_touch_bps / 10_000.0)
        for price, size in asks:
            if price <= max_ask:
                total += size
                seen = True
    return total if seen else None


def _available_at_or_better(side: str, trade_price: float | None, bids: list[tuple[float, float]], asks: list[tuple[float, float]]) -> float | None:
    if trade_price is None:
        levels = bids if side in {"SELL", "S", "TAKER_SELL"} else asks
        return levels[0][1] if levels else None
    if side in {"SELL", "S", "TAKER_SELL"}:
        matching = [size for price, size in bids if price >= trade_price]
        return sum(matching) if matching else (bids[0][1] if bids else 0.0)
    matching = [size for price, size in asks if price <= trade_price]
    return sum(matching) if matching else (asks[0][1] if asks else 0.0)


def _estimate_entry_and_slippage(side: str, size: float, trade_price: float | None, bids: list[tuple[float, float]], asks: list[tuple[float, float]]) -> tuple[float | None, float | None]:
    levels = bids if side in {"SELL", "S", "TAKER_SELL"} else asks
    if size <= 0 or not levels:
        return None, None
    remaining = size
    notional = 0.0
    filled = 0.0
    for price, available in levels:
        take = min(remaining, available)
        notional += take * price
        filled += take
        remaining -= take
        if remaining <= 1e-12:
            break
    if filled <= 0:
        return None, None
    avg = notional / filled
    if remaining > 1e-12:
        return avg, None
    if trade_price in (None, 0):
        return avg, None
    if side in {"SELL", "S", "TAKER_SELL"}:
        slippage = max(0.0, (trade_price - avg) / trade_price * 10_000.0)
    else:
        slippage = max(0.0, (avg - trade_price) / trade_price * 10_000.0)
    return avg, slippage


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


def _parse_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _round_price(value: float | None) -> float | None:
    return None if value is None else round(float(value), 6)


def _round_size(value: float | None) -> float | None:
    return None if value is None else round(float(value), 6)


def _round_bps(value: float | None) -> float | None:
    return None if value is None else round(float(value), 2)
