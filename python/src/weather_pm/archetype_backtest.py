from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from weather_pm.market_parser import parse_market_question
from weather_pm.orderbook_simulator import simulate_orderbook_fill

SCHEMA_VERSION = 1
DEFAULT_JSON_NAME = "weather_archetype_backtest_latest.json"
DEFAULT_MD_NAME = "weather_archetype_backtest_latest.md"
ARCHETYPES = (
    "event_surface_grid_specialist",
    "exact_bin_anomaly_hunter",
    "threshold_harvester",
    "weather_signal_generalist",
)
BUCKETS = ("lt_2h", "2h_to_12h", "12h_to_48h", "gt_48h", "unknown")


def build_archetype_backtest(
    rows: Iterable[dict[str, Any]],
    *,
    max_fillable_spend_usdc: float | None = None,
) -> dict[str, Any]:
    input_rows = [row for row in rows if isinstance(row, dict)]
    trades = [_replay_trade(row, max_fillable_spend_usdc=max_fillable_spend_usdc) for row in input_rows]
    equity_curve = _equity_curve(trades)
    report = {
        "schema_version": SCHEMA_VERSION,
        "summary": _metrics(trades) | {
            "input_trade_count": len(input_rows),
            "replayed_trade_count": len(trades),
            "archetype_count": len({trade["archetype"] for trade in trades}),
            "max_drawdown_usdc": _max_drawdown(equity_curve),
        },
        "archetypes": _aggregate_by(trades, "archetype", include_all_archetypes=True),
        "exposure": {
            "by_city": _exposure_by(trades, "city"),
            "by_station": _exposure_by(trades, "station"),
            "by_archetype": _exposure_by(trades, "archetype"),
        },
        "time_to_resolution_buckets": _bucket_aggregation(trades),
        "equity_curve": equity_curve,
        "trades": trades,
        "artifacts": {},
    }
    report["summary"] = _ordered_summary(report["summary"])
    return report


def write_archetype_backtest_artifacts(
    input_path: str | Path,
    *,
    output_dir: str | Path = "data/polymarket",
    max_fillable_spend_usdc: float | None = None,
) -> dict[str, Any]:
    source_path = Path(input_path)
    rows = load_backtest_rows(source_path)
    report = build_archetype_backtest(rows, max_fillable_spend_usdc=max_fillable_spend_usdc)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / DEFAULT_JSON_NAME
    md_path = output_path / DEFAULT_MD_NAME
    report["artifacts"] = {"source_input_json": str(source_path), "json_path": str(json_path), "md_path": str(md_path)}
    json_path.write_text(json.dumps(report, indent=2, sort_keys=False), encoding="utf-8")
    md_path.write_text(_markdown(report), encoding="utf-8")
    return {"json_path": str(json_path), "md_path": str(md_path), "summary": report["summary"]}


def load_backtest_rows(path: str | Path) -> list[dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("trades", "positions", "signals", "activity", "markets"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    raise ValueError("archetype backtest input must be a JSON list/object containing trades")


def _replay_trade(row: dict[str, Any], *, max_fillable_spend_usdc: float | None) -> dict[str, Any]:
    question = str(row.get("question") or row.get("title") or row.get("market_title") or "")
    parsed: Any | None = None
    try:
        parsed = parse_market_question(question) if question else None
    except ValueError:
        parsed = None
    side = _side(row.get("side") or row.get("outcome") or "YES")
    stake = _float(row.get("stake_usdc") or row.get("notional_usdc") or row.get("size_usdc") or row.get("amount_usdc"))
    requested = stake
    cap = stake if max_fillable_spend_usdc is None else min(stake, max(float(max_fillable_spend_usdc), 0.0))
    orderbook = row.get("orderbook") if isinstance(row.get("orderbook"), dict) else None
    fill = simulate_orderbook_fill(orderbook, side=side, spend_usd=cap)
    filled_spend = float(fill["fillable_spend"] or 0.0)
    avg_price = fill.get("avg_fill_price")
    resolved_price = _resolved_price(row, side=side)
    shares = 0.0 if not avg_price else filled_spend / float(avg_price)
    payout = shares * resolved_price
    pnl = 0.0 if filled_spend <= 0.0 else payout - filled_spend
    hours = _optional_float(row.get("entered_at_hours_to_resolution") or row.get("hours_to_resolution") or row.get("time_to_resolution_hours"))
    market_id = str(row.get("market_id") or row.get("id") or "")
    city = str(row.get("city") or (parsed.city if parsed else "unknown"))
    station = str(row.get("source_station_code") or row.get("station_code") or row.get("station") or "unknown")
    archetype = _archetype(row.get("archetype") or row.get("strategy_archetype"))
    return {
        "market_id": market_id,
        "question": question,
        "archetype": archetype,
        "city": city,
        "station": station,
        "side": side,
        "stake_usdc": _round(stake),
        "requested_spend_usdc": _round(requested),
        "filled_spend_usdc": _round(filled_spend),
        "fillability_capped": stake > cap,
        "fill_status": fill["fill_status"],
        "execution_blocker": fill["execution_blocker"],
        "top_ask": fill["top_ask"],
        "avg_fill_price": avg_price,
        "slippage_from_top_ask": fill["slippage_from_top_ask"],
        "resolved_price": _round(resolved_price),
        "pnl_usdc": _round(pnl),
        "roi": _round(pnl / filled_spend) if filled_spend > 0 else 0.0,
        "hit": pnl > 0.0,
        "capturable_volume_usdc": _round(filled_spend),
        "hours_to_resolution": hours,
        "time_to_resolution_bucket": _bucket(hours),
    }


def _metrics(trades: list[dict[str, Any]]) -> dict[str, Any]:
    pnl = sum(float(trade["pnl_usdc"]) for trade in trades)
    filled = sum(float(trade["filled_spend_usdc"]) for trade in trades)
    requested = sum(float(trade["requested_spend_usdc"]) for trade in trades)
    slippages = [float(trade["slippage_from_top_ask"]) for trade in trades if trade.get("slippage_from_top_ask") is not None]
    return {
        "pnl_usdc": _round(pnl),
        "roi": _round(pnl / filled) if filled > 0 else 0.0,
        "hit_rate": _round(sum(1 for trade in trades if trade["hit"]) / len(trades)) if trades else 0.0,
        "fillability": _round(filled / requested) if requested > 0 else 0.0,
        "capturable_volume_usdc": _round(filled),
        "average_slippage": _round(sum(slippages) / len(slippages)) if slippages else 0.0,
    }


def _ordered_summary(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "input_trade_count": summary["input_trade_count"],
        "replayed_trade_count": summary["replayed_trade_count"],
        "archetype_count": summary["archetype_count"],
        "pnl_usdc": summary["pnl_usdc"],
        "roi": summary["roi"],
        "max_drawdown_usdc": summary["max_drawdown_usdc"],
        "hit_rate": summary["hit_rate"],
        "fillability": summary["fillability"],
        "capturable_volume_usdc": summary["capturable_volume_usdc"],
        "average_slippage": summary["average_slippage"],
    }


def _aggregate_by(trades: list[dict[str, Any]], key: str, *, include_all_archetypes: bool = False) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trade in trades:
        grouped[str(trade.get(key) or "unknown")].append(trade)
    keys = list(ARCHETYPES) if include_all_archetypes else sorted(grouped)
    if include_all_archetypes:
        keys.extend(sorted(set(grouped) - set(keys)))
    return {name: _group_payload(grouped.get(name, [])) for name in keys if grouped.get(name, []) or include_all_archetypes}


def _group_payload(rows: list[dict[str, Any]]) -> dict[str, Any]:
    metrics = _metrics(rows)
    return {
        "trade_count": len(rows),
        "pnl_usdc": metrics["pnl_usdc"],
        "roi": metrics["roi"],
        "hit_rate": metrics["hit_rate"],
        "fillability": metrics["fillability"],
        "average_slippage": metrics["average_slippage"],
        "capturable_volume_usdc": metrics["capturable_volume_usdc"],
    }


def _exposure_by(trades: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trade in trades:
        grouped[str(trade.get(key) or "unknown")].append(trade)
    return {
        name: {
            "trade_count": len(rows),
            "capturable_volume_usdc": _round(sum(float(row["capturable_volume_usdc"]) for row in rows)),
            "pnl_usdc": _round(sum(float(row["pnl_usdc"]) for row in rows)),
        }
        for name, rows in sorted(grouped.items())
    }


def _bucket_aggregation(trades: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped = {bucket: [] for bucket in BUCKETS}
    for trade in trades:
        grouped[str(trade["time_to_resolution_bucket"])].append(trade)
    return {
        bucket: {
            "trade_count": len(rows),
            "pnl_usdc": _round(sum(float(row["pnl_usdc"]) for row in rows)),
            "capturable_volume_usdc": _round(sum(float(row["capturable_volume_usdc"]) for row in rows)),
        }
        for bucket, rows in grouped.items()
    }


def _equity_curve(trades: list[dict[str, Any]]) -> list[float]:
    total = 0.0
    curve = []
    for trade in trades:
        total += float(trade["pnl_usdc"])
        curve.append(_round(total))
    return curve


def _max_drawdown(curve: list[float]) -> float:
    peak = 0.0
    max_dd = 0.0
    for value in curve:
        peak = max(peak, value)
        max_dd = max(max_dd, peak - value)
    return _round(max_dd)


def _resolved_price(row: dict[str, Any], *, side: str) -> float:
    if row.get("resolved_price") is not None:
        return _float(row.get("resolved_price"))
    outcome = str(row.get("resolved_side") or row.get("outcome_resolved") or row.get("winning_side") or "").upper()
    if outcome in {"YES", "NO"}:
        return 1.0 if outcome == side else 0.0
    return 0.0


def _bucket(hours: float | None) -> str:
    if hours is None:
        return "unknown"
    if hours < 2:
        return "lt_2h"
    if hours < 12:
        return "2h_to_12h"
    if hours < 48:
        return "12h_to_48h"
    return "gt_48h"


def _markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = ["# Weather Archetype Backtest", "", f"PnL: {summary['pnl_usdc']} | ROI: {summary['roi']} | Drawdown: {summary['max_drawdown_usdc']}", ""]
    lines.extend(["| Archetype | Trades | PnL | ROI | Hit Rate | Fillability | Volume |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"])
    for name, row in report["archetypes"].items():
        lines.append(f"| {name} | {row['trade_count']} | {row['pnl_usdc']} | {row['roi']} | {row['hit_rate']} | {row['fillability']} | {row['capturable_volume_usdc']} |")
    lines.append("")
    return "\n".join(lines)


def _archetype(value: Any) -> str:
    text = str(value or "weather_signal_generalist")
    return text if text in set(ARCHETYPES) else "weather_signal_generalist"


def _side(value: Any) -> str:
    text = str(value or "YES").upper()
    return "NO" if text in {"NO", "N", "BUY_NO", "LONG_NO"} else "YES"


def _float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _round(value: float) -> float:
    return round(float(value), 6)
