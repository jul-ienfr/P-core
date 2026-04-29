from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def build_account_decision_dataset(
    trades_payload: dict[str, Any],
    markets_snapshots_payload: dict[str, Any],
    *,
    bucket_minutes: int = 60,
    no_trade_per_trade: int = 5,
) -> dict[str, Any]:
    trades = _rows_from_payload(trades_payload, "trades")
    markets = _rows_from_payload(markets_snapshots_payload, "markets")
    trade_examples = [_trade_example(row, bucket_minutes= bucket_minutes) for row in trades]
    traded_keys = {(row.get("account"), row.get("market_id")) for row in trade_examples}
    trade_counts: dict[tuple[Any, ...], int] = {}
    no_trade_counts: dict[tuple[Any, ...], int] = {}
    for row in trade_examples:
        key = _surface_key(row)
        trade_counts[key] = trade_counts.get(key, 0) + 1

    no_trade_examples: list[dict[str, Any]] = []
    observable_markets_considered = 0
    skipped_unobservable = 0
    accounts = sorted({str(row.get("account") or row.get("wallet") or "") for row in trade_examples if row.get("account") or row.get("wallet")})
    for market in markets:
        active_ts = _active_timestamp(market)
        if market.get("observable") is not True or not active_ts:
            skipped_unobservable += 1
            continue
        market_bucket = _timestamp_bucket(active_ts, bucket_minutes)
        if not market_bucket:
            skipped_unobservable += 1
            continue
        observable_markets_considered += 1
        for trade in trade_examples:
            if (trade.get("account"), market.get("market_id") or market.get("id")) in traded_keys:
                continue
            if not _same_surface(trade, market, market_bucket):
                continue
            surface_key = _surface_key(trade)
            cap = max(0, int(no_trade_per_trade)) * trade_counts.get(surface_key, 0)
            if no_trade_counts.get(surface_key, 0) >= cap:
                continue
            no_trade_counts[surface_key] = no_trade_counts.get(surface_key, 0) + 1
            no_trade_examples.append(_no_trade_example(trade, market, market_bucket))

    examples = trade_examples + no_trade_examples
    summary = {
        "paper_only": True,
        "live_order_allowed": False,
        "accounts": len(accounts),
        "trade_examples": len(trade_examples),
        "no_trade_examples": len(no_trade_examples),
        "observable_markets_considered": observable_markets_considered,
        "skipped_unobservable": skipped_unobservable,
        "bucket_minutes": int(bucket_minutes),
        "no_trade_per_trade": int(no_trade_per_trade),
    }
    return {"paper_only": True, "live_order_allowed": False, "summary": summary, "examples": examples}


def write_account_decision_dataset(
    trades_json: str | Path,
    markets_snapshots_json: str | Path,
    output_json: str | Path,
    *,
    bucket_minutes: int = 60,
    no_trade_per_trade: int = 5,
) -> dict[str, Any]:
    trades_payload = _load_object(trades_json, "trades JSON")
    markets_payload = _load_object(markets_snapshots_json, "markets snapshots JSON")
    artifact = build_account_decision_dataset(trades_payload, markets_payload, bucket_minutes=bucket_minutes, no_trade_per_trade=no_trade_per_trade)
    output_path = Path(output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")
    return dict(artifact["summary"])


def _trade_example(row: dict[str, Any], *, bucket_minutes: int) -> dict[str, Any]:
    timestamp = row.get("timestamp") or row.get("created_at") or row.get("createdAt") or row.get("trade_timestamp")
    return {
        "label": "trade",
        "account": row.get("account") or row.get("handle") or row.get("username") or row.get("wallet"),
        "wallet": row.get("wallet") or row.get("proxyWallet") or row.get("proxy_wallet"),
        "market_id": row.get("market_id") or row.get("marketId") or row.get("id"),
        "timestamp": timestamp,
        "timestamp_bucket": _timestamp_bucket(timestamp, bucket_minutes),
        "city": row.get("city"),
        "date": row.get("date") or row.get("resolution_date"),
        "market_type": row.get("market_type") or row.get("weather_market_type") or row.get("type"),
        "side": row.get("side") or row.get("outcome"),
        "price": _to_float(row.get("price")),
        **_copy_optional(row, ("threshold", "bin_center", "condition_id", "token_id", "slug")),
    }


def _no_trade_example(trade: dict[str, Any], market: dict[str, Any], market_bucket: str) -> dict[str, Any]:
    return {
        "label": "no_trade",
        "reason": "similar_surface_no_account_trade",
        "observable": True,
        "account": trade.get("account"),
        "wallet": trade.get("wallet"),
        "market_id": market.get("market_id") or market.get("marketId") or market.get("id"),
        "timestamp": _active_timestamp(market),
        "timestamp_bucket": market_bucket,
        "city": market.get("city") or trade.get("city"),
        "date": market.get("date") or market.get("resolution_date") or trade.get("date"),
        "market_type": market.get("market_type") or market.get("weather_market_type") or market.get("type") or trade.get("market_type"),
        "side": market.get("side") or market.get("outcome"),
        "price": _to_float(market.get("price") or market.get("yes_price")),
        **_copy_optional(market, ("threshold", "bin_center", "condition_id", "token_id", "slug")),
    }


def _same_surface(trade: dict[str, Any], market: dict[str, Any], market_bucket: str) -> bool:
    return (
        _norm(trade.get("city")) == _norm(market.get("city"))
        and str(trade.get("date") or "") == str(market.get("date") or market.get("resolution_date") or "")
        and _norm(trade.get("market_type")) == _norm(market.get("market_type") or market.get("weather_market_type") or market.get("type"))
        and trade.get("timestamp_bucket") == market_bucket
        and str(trade.get("market_id")) != str(market.get("market_id") or market.get("marketId") or market.get("id"))
    )


def _surface_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (row.get("account"), _norm(row.get("city")), row.get("date"), _norm(row.get("market_type")), row.get("timestamp_bucket"))


def _active_timestamp(row: dict[str, Any]) -> Any:
    for key in ("active_timestamp", "snapshot_timestamp", "timestamp", "observed_at", "created_at", "createdAt"):
        if row.get(key):
            return row.get(key)
    return None


def _timestamp_bucket(raw: Any, bucket_minutes: int) -> str | None:
    parsed = _parse_timestamp(raw)
    if parsed is None:
        return None
    minutes = max(1, int(bucket_minutes))
    total = parsed.hour * 60 + parsed.minute
    bucket_total = (total // minutes) * minutes
    bucket = parsed.replace(hour=bucket_total // 60, minute=bucket_total % 60, second=0, microsecond=0)
    return bucket.isoformat().replace("+00:00", "Z")


def _parse_timestamp(raw: Any) -> datetime | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _rows_from_payload(payload: dict[str, Any], preferred_key: str) -> list[dict[str, Any]]:
    rows = payload.get(preferred_key) or payload.get("examples") or payload.get("data")
    if preferred_key == "markets" and rows is None:
        rows = payload.get("market_snapshots") or payload.get("snapshots")
    if isinstance(rows, list):
        return [dict(row) for row in rows if isinstance(row, dict)]
    return []


def _load_object(path: str | Path, label: str) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be an object")
    return payload


def _copy_optional(row: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {key: row.get(key) for key in keys if key in row}


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()
