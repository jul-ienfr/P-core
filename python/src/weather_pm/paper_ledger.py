from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from prediction_core.paper.exit_policy import annotate_order_with_exit_policy
from weather_pm.orderbook_simulator import normalize_orderbook_asks, simulate_orderbook_fill

PAPER_LEDGER_STATUSES = {
    "planned",
    "filled",
    "partial",
    "skipped_price_moved",
    "cancelled",
    "settled_win",
    "settled_loss",
}

PAPER_LEDGER_ACTIONS = {
    "HOLD",
    "HOLD_CAPPED",
    "PENDING_LIMIT",
    "TAKE_PROFIT_REVIEW_PAPER",
    "RED_FLAG_RECHECK_SOURCE",
    "NO_ADD_PRICE_MOVED",
}


class PaperLedgerError(ValueError):
    """Raised when a paper ledger operation would violate strict-limit paper rules."""


def paper_ledger_place(candidate: dict[str, Any], *, ledger: dict[str, Any] | None = None) -> dict[str, Any]:
    """Record a limit-only paper order from a candidate and refreshed orderbook.

    The ledger intentionally never creates live/market orders. If no refresh orderbook is
    provided, placement fails instead of inventing a market-buy fill.
    """
    if not isinstance(candidate, dict):
        raise PaperLedgerError("paper ledger candidate must be an object")
    orderbook = candidate.get("orderbook")
    if not isinstance(orderbook, dict):
        raise PaperLedgerError("paper ledger requires a refresh orderbook; no market buy fallback is allowed")

    side = str(candidate.get("side") or "YES").upper()
    strict_limit = _required_float(candidate, "strict_limit")
    spend_usdc = _required_float(candidate, "spend_usdc")
    actual_refresh_price = _actual_refresh_price(candidate, orderbook, side)
    fill = simulate_orderbook_fill(
        orderbook,
        side=side,
        spend_usd=spend_usdc,
        probability_edge=_optional_float(candidate.get("probability_edge")),
        strict_limit=strict_limit,
    )
    filled_usdc = float(fill.get("fillable_spend") or 0.0)
    avg_fill_price = _optional_float(fill.get("avg_fill_price"))
    shares = round(filled_usdc / avg_fill_price, 6) if avg_fill_price and filled_usdc > 0 else 0.0

    if actual_refresh_price is not None and actual_refresh_price > strict_limit:
        status = "skipped_price_moved"
        filled_usdc = 0.0
        shares = 0.0
    elif fill.get("fill_status") == "filled" and not fill.get("execution_blocker"):
        status = "filled"
    elif filled_usdc > 0.0:
        status = "partial"
    else:
        status = "planned"

    cost_state = _paper_cost_state(candidate, fill=fill, filled_usdc=filled_usdc, shares=shares, mtm_usdc=0.0)
    paper_pnl = round(-cost_state["all_in_entry_cost_usdc"] - cost_state["estimated_exit_fee_usdc"], 6) if filled_usdc else 0.0

    order = {
        "order_id": str(candidate.get("order_id") or _default_order_id(candidate)),
        "created_at": str(candidate.get("created_at") or _utc_now()),
        "updated_at": str(candidate.get("updated_at") or _utc_now()),
        "run_id": candidate.get("run_id"),
        "strategy_id": candidate.get("strategy_id"),
        "profile_id": candidate.get("profile_id") or candidate.get("strategy_profile_id"),
        "order_type": "limit_only_paper",
        "paper_only": True,
        "live_order_allowed": False,
        "status": status,
        "surface_id": candidate.get("surface_id"),
        "market_id": candidate.get("market_id"),
        "token_id": candidate.get("token_id"),
        "side": side,
        "strict_limit": strict_limit,
        "requested_spend_usdc": spend_usdc,
        "filled_usdc": round(filled_usdc, 6),
        "unfilled_usdc": round(max(spend_usdc - filled_usdc, 0.0), 6),
        "shares": shares,
        "avg_fill_price": avg_fill_price,
        "actual_refresh_price": actual_refresh_price,
        "source_status": candidate.get("source_status"),
        "station_status": candidate.get("station_status"),
        "station": candidate.get("station"),
        "source_url": candidate.get("source_url"),
        "account_consensus": candidate.get("account_consensus", {}),
        "model_reason": candidate.get("model_reason"),
        "inconsistency_reason": candidate.get("inconsistency_reason"),
        "simulated_fill": fill,
        **cost_state,
        "refresh_history": [],
        "operator_action": _operator_action_for(status=status, order=None, refresh_price=actual_refresh_price, strict_limit=strict_limit),
        "mtm_usdc": 0.0,
        "pnl_usdc": paper_pnl,
        "net_pnl_after_all_costs": paper_pnl,
    }
    result = _copy_ledger(ledger)
    result.setdefault("orders", []).append(order)
    return _with_summary(result)


def paper_ledger_refresh(
    ledger: dict[str, Any],
    *,
    refreshes: dict[str, Any] | None = None,
    settlements: dict[str, str] | None = None,
    max_position_usdc: float = 10.0,
) -> dict[str, Any]:
    if not isinstance(ledger, dict):
        raise PaperLedgerError("paper ledger must be an object")
    result = _copy_ledger(ledger)
    refreshes = refreshes or {}
    settlements = settlements or {}
    orders = result.get("orders") if isinstance(result.get("orders"), list) else []
    refreshed_orders = []
    for raw in orders:
        if not isinstance(raw, dict):
            continue
        order = dict(raw)
        token = str(order.get("token_id") or "")
        market = str(order.get("market_id") or "")
        refresh = refreshes.get(token) or refreshes.get(market) or {}
        if not isinstance(refresh, dict):
            refresh = {}

        if token in settlements or market in settlements:
            outcome = str(settlements.get(token, settlements.get(market, ""))).lower()
            _apply_settlement(order, outcome)
        else:
            _apply_refresh(order, refresh, max_position_usdc=max_position_usdc)
            order = annotate_order_with_exit_policy(order)
        order["updated_at"] = _utc_now()
        refreshed_orders.append(order)
    result["orders"] = refreshed_orders
    return _with_summary(result)


def write_paper_ledger_artifacts(ledger: dict[str, Any], *, output_dir: str | Path = "data/polymarket") -> dict[str, Any]:
    payload = _with_summary(_copy_ledger(ledger))
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "weather_paper_ledger_latest.json"
    csv_path = output / "weather_paper_ledger_latest.csv"
    md_path = output / "weather_paper_ledger_latest.md"
    payload.setdefault("artifacts", {})["json"] = str(json_path)
    payload.setdefault("artifacts", {})["csv"] = str(csv_path)
    payload.setdefault("artifacts", {})["markdown"] = str(md_path)
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    _write_csv(payload, csv_path)
    md_path.write_text(render_paper_ledger_markdown(payload), encoding="utf-8")
    return payload


def render_paper_ledger_markdown(ledger: dict[str, Any]) -> str:
    payload = _with_summary(_copy_ledger(ledger))
    summary = payload.get("summary", {})
    lines = [
        "# Polymarket weather paper ledger",
        "",
        f"Orders: {summary.get('orders', 0)}",
        f"Filled spend: {float(summary.get('filled_usdc') or 0.0):.2f} USDC",
        f"PnL: {float(summary.get('pnl_usdc') or 0.0):.2f} USDC",
        "Actions: " + ", ".join(f"{key}: {value}" for key, value in sorted(summary.get("action_counts", {}).items())),
        "",
        "| Status | Action | Market | Token | Side | Limit | Refresh | Filled | PnL | Source | Reason |",
        "|---|---|---|---|---|---:|---:|---:|---:|---|---|",
    ]
    for order in payload.get("orders", []):
        if not isinstance(order, dict):
            continue
        reason = order.get("model_reason") or order.get("inconsistency_reason") or ""
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(order.get("status")),
                    _cell(order.get("operator_action")),
                    _cell(order.get("market_id")),
                    _cell(order.get("token_id")),
                    _cell(order.get("side")),
                    _fmt(order.get("strict_limit")),
                    _fmt(order.get("actual_refresh_price")),
                    _fmt(order.get("filled_usdc")),
                    _fmt(order.get("pnl_usdc")),
                    _cell(order.get("source_status")),
                    _cell(reason),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def load_paper_ledger(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PaperLedgerError("paper ledger JSON must be an object")
    return payload


def load_candidate(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PaperLedgerError("paper ledger candidate JSON must be an object")
    return payload


def load_refresh_payload(path: str | Path) -> tuple[dict[str, Any], dict[str, str]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PaperLedgerError("paper ledger refresh JSON must be an object")
    refreshes = payload.get("refreshes", payload)
    settlements = payload.get("settlements", {})
    return (refreshes if isinstance(refreshes, dict) else {}, settlements if isinstance(settlements, dict) else {})


def _apply_refresh(order: dict[str, Any], refresh: dict[str, Any], *, max_position_usdc: float) -> None:
    if refresh:
        for key in ("source_status", "station_status", "station", "source_url", "actual_refresh_price"):
            if key in refresh:
                order[key] = refresh[key]
        if "orderbook" in refresh and isinstance(refresh.get("orderbook"), dict):
            fill = simulate_orderbook_fill(
                refresh.get("orderbook"),
                side=str(order.get("side") or "YES"),
                spend_usd=float(order.get("requested_spend_usdc") or 0.0),
                strict_limit=_optional_float(order.get("strict_limit")),
            )
            order["simulated_fill"] = fill
            if order.get("actual_refresh_price") is None and fill.get("top_ask") is not None:
                order["actual_refresh_price"] = fill.get("top_ask")
        if order.get("actual_refresh_price") is None and refresh.get("best_ask") is not None:
            order["actual_refresh_price"] = _optional_float(refresh.get("best_ask"))
    best_bid = _optional_float(refresh.get("best_bid", refresh.get("actual_refresh_price")))
    if best_bid is None:
        best_bid = _optional_float(order.get("actual_refresh_price"))
    shares = float(order.get("shares") or 0.0)
    mtm = shares * best_bid if best_bid is not None else 0.0
    if isinstance(refresh.get("exit_orderbook"), dict):
        mtm = _simulate_exit_value(refresh.get("exit_orderbook"), side=str(order.get("side") or "YES"), shares=shares)
        order["exit_cost_basis"] = "live_bid_book"
    order["mtm_usdc"] = round(mtm, 6)
    realized_exit_fee = _fee_amount(
        mtm,
        bps=_fee_bps(order, "exit"),
        fixed=0.0,
    ) if shares > 0 and order.get("exit_cost_basis") == "live_bid_book" else None
    if realized_exit_fee is not None:
        order["paper_exit_value_usdc"] = round(mtm, 6)
        order["realized_exit_fee_usdc"] = realized_exit_fee
    exit_fee = realized_exit_fee if realized_exit_fee is not None else float(order.get("estimated_exit_fee_usdc") or 0.0)
    pnl = round(mtm - float(order.get("all_in_entry_cost_usdc") or order.get("filled_usdc") or 0.0) - exit_fee, 6)
    order["pnl_usdc"] = pnl
    order["net_pnl_after_all_costs"] = pnl
    order.setdefault("refresh_history", []).append(
        {
            "refreshed_at": _utc_now(),
            "actual_refresh_price": order.get("actual_refresh_price"),
            "best_bid": best_bid,
            "source_status": order.get("source_status"),
            "station_status": order.get("station_status"),
            "mtm_usdc": order["mtm_usdc"],
            "pnl_usdc": order["pnl_usdc"],
        }
    )
    order["operator_action"] = _operator_action_for(
        status=str(order.get("status") or "planned"),
        order=order,
        refresh_price=_optional_float(order.get("actual_refresh_price")),
        strict_limit=_optional_float(order.get("strict_limit")),
        max_position_usdc=max_position_usdc,
    )


def _apply_settlement(order: dict[str, Any], outcome: str) -> None:
    shares = float(order.get("shares") or 0.0)
    filled = float(order.get("filled_usdc") or 0.0)
    if outcome in {"win", "won", "settled_win", "true", "1"}:
        order["status"] = "settled_win"
        order["mtm_usdc"] = round(shares, 6)
        pnl = round(shares - float(order.get("all_in_entry_cost_usdc") or filled), 6)
        order["pnl_usdc"] = pnl
        order["net_pnl_after_all_costs"] = pnl
        order["operator_action"] = "HOLD"
    elif outcome in {"loss", "lost", "settled_loss", "false", "0"}:
        order["status"] = "settled_loss"
        order["mtm_usdc"] = 0.0
        pnl = round(-float(order.get("all_in_entry_cost_usdc") or filled), 6)
        order["pnl_usdc"] = pnl
        order["net_pnl_after_all_costs"] = pnl
        order["operator_action"] = "HOLD"
    else:
        raise PaperLedgerError(f"unknown settlement outcome: {outcome}")


def _paper_cost_state(candidate: dict[str, Any], *, fill: dict[str, Any], filled_usdc: float, shares: float, mtm_usdc: float) -> dict[str, Any]:
    opening_trading_fee = _fee_amount(filled_usdc, bps=_fee_bps(candidate, "open"), fixed=0.0)
    opening_fixed_fee = _optional_float(candidate.get("opening_fee_usdc", candidate.get("deposit_fee_usd"))) or 0.0
    opening_fee = round(opening_trading_fee + opening_fixed_fee, 6)
    top_ask = _optional_float(fill.get("top_ask"))
    avg_fill_price = _optional_float(fill.get("avg_fill_price"))
    slippage_usdc = 0.0
    if top_ask is not None and avg_fill_price is not None and shares > 0:
        slippage_usdc = round(max(avg_fill_price - top_ask, 0.0) * shares, 6)
    estimated_exit_fixed = _optional_float(candidate.get("estimated_exit_fee_usdc", candidate.get("withdrawal_fee_usd")))
    if estimated_exit_fixed is None:
        estimated_exit_fixed = _optional_float(candidate.get("closing_fee_usdc")) or 0.0
    estimated_exit_fee = _fee_amount(filled_usdc, bps=_estimated_exit_fee_bps(candidate), fixed=estimated_exit_fixed)
    return {
        "opening_trading_fee_usdc": opening_trading_fee,
        "opening_fixed_fee_usdc": round(opening_fixed_fee, 6),
        "opening_fee_usdc": opening_fee,
        "slippage_usdc": slippage_usdc,
        "all_in_entry_cost_usdc": round(filled_usdc + opening_fee, 6),
        "estimated_exit_fixed_fee_usdc": round(estimated_exit_fixed, 6),
        "estimated_exit_fee_bps": _estimated_exit_fee_bps(candidate),
        "estimated_exit_fee_usdc": estimated_exit_fee,
        "exit_cost_basis": "estimate_until_live_exit_book" if filled_usdc > 0 else "no_fill",
        "realized_exit_fee_usdc": None,
        "paper_exit_value_usdc": round(mtm_usdc, 6),
    }


def _fee_bps(payload: dict[str, Any], phase: str) -> float:
    if phase == "open":
        for key in ("taker_base_fee", "taker_fee", "taker_fee_rate"):
            value = _optional_float(payload.get(key))
            if value is not None:
                return value * 10000.0 if 0.0 < value < 1.0 else value
        return _optional_float(payload.get("taker_fee_bps", payload.get("transaction_fee_bps"))) or 0.0
    explicit = _optional_float(payload.get("estimated_exit_fee_bps"))
    if explicit is not None:
        return explicit
    for key in ("exit_taker_base_fee", "taker_base_fee", "taker_fee", "taker_fee_rate"):
        value = _optional_float(payload.get(key))
        if value is not None:
            return value * 10000.0 if 0.0 < value < 1.0 else value
    return _estimated_exit_fee_bps(payload)


def _estimated_exit_fee_bps(payload: dict[str, Any]) -> float:
    return _optional_float(payload.get("estimated_exit_fee_bps", payload.get("closing_fee_bps"))) or 0.0


def _fee_amount(notional: float, *, bps: float, fixed: float) -> float:
    return round(max(0.0, fixed) + max(0.0, notional) * max(0.0, bps) / 10000.0, 6)


def _simulate_exit_value(orderbook: dict[str, Any], *, side: str, shares: float) -> float:
    levels = _normalize_orderbook_bids(orderbook, side=side)
    remaining = max(float(shares or 0.0), 0.0)
    value = 0.0
    for level in levels:
        if remaining <= 1e-12:
            break
        shares_here = min(remaining, level["size"])
        value += shares_here * level["price"]
        remaining -= shares_here
    return round(value, 6)


def _normalize_orderbook_bids(orderbook: dict[str, Any] | None, *, side: str) -> list[dict[str, float]]:
    if not isinstance(orderbook, dict):
        return []
    side_key = str(side or "YES").strip().lower()
    candidates: list[Any] = []
    for key in (f"{side_key}_bids", f"{side_key}Bids", f"{side_key}_bid_levels"):
        value = orderbook.get(key)
        if isinstance(value, list):
            candidates = value
            break
    if not candidates:
        nested = orderbook.get(side_key) or orderbook.get(side_key.upper())
        if isinstance(nested, dict):
            for key in ("bids", "bid_levels"):
                value = nested.get(key)
                if isinstance(value, list):
                    candidates = value
                    break
    if not candidates and side_key == "yes":
        value = orderbook.get("bids") or orderbook.get("bid_levels")
        if isinstance(value, list):
            candidates = value
    levels: list[dict[str, float]] = []
    for level in candidates:
        if not isinstance(level, dict):
            continue
        price = _optional_float(level.get("price"))
        size = _optional_float(level.get("size", level.get("quantity")))
        if price is None or size is None or price <= 0.0 or size <= 0.0:
            continue
        levels.append({"price": price, "size": size})
    return sorted(levels, key=lambda item: item["price"], reverse=True)


def _operator_action_for(
    *,
    status: str,
    order: dict[str, Any] | None,
    refresh_price: float | None,
    strict_limit: float | None,
    max_position_usdc: float = 10.0,
) -> str:
    if status == "skipped_price_moved":
        return "NO_ADD_PRICE_MOVED"
    if status in {"planned", "partial"}:
        return "PENDING_LIMIT"
    if status not in {"filled", "settled_win", "settled_loss"} and refresh_price is not None and strict_limit is not None and refresh_price > strict_limit:
        return "NO_ADD_PRICE_MOVED"
    if order:
        source = str(order.get("source_status") or "")
        station = str(order.get("station_status") or "")
        if source != "source_confirmed" or (station and station != "station_confirmed"):
            return "RED_FLAG_RECHECK_SOURCE"
        filled = float(order.get("filled_usdc") or 0.0)
        pnl = float(order.get("pnl_usdc") or 0.0)
        if filled > 0.0 and pnl / filled >= 0.25:
            return "TAKE_PROFIT_REVIEW_PAPER"
        if filled >= max_position_usdc:
            return "HOLD_CAPPED"
    return "HOLD"


def _with_summary(ledger: dict[str, Any]) -> dict[str, Any]:
    orders = [order for order in ledger.get("orders", []) if isinstance(order, dict)] if isinstance(ledger.get("orders"), list) else []
    ledger["orders"] = orders
    ledger["summary"] = {
        "orders": len(orders),
        "status_counts": dict(Counter(str(order.get("status")) for order in orders)),
        "action_counts": dict(Counter(str(order.get("operator_action")) for order in orders)),
        "filled_usdc": round(sum(float(order.get("filled_usdc") or 0.0) for order in orders), 6),
        "mtm_usdc": round(sum(float(order.get("mtm_usdc") or 0.0) for order in orders), 6),
        "pnl_usdc": round(sum(float(order.get("pnl_usdc") or 0.0) for order in orders), 6),
        "opening_fee_usdc": round(sum(float(order.get("opening_fee_usdc") or 0.0) for order in orders), 6),
        "estimated_exit_fee_usdc": round(sum(float(order.get("estimated_exit_fee_usdc") or 0.0) for order in orders), 6),
        "realized_exit_fee_usdc": round(sum(float(order.get("realized_exit_fee_usdc") or 0.0) for order in orders), 6),
        "net_pnl_after_all_costs": round(sum(float(order.get("net_pnl_after_all_costs", order.get("pnl_usdc")) or 0.0) for order in orders), 6),
        "paper_only": True,
        "live_order_allowed": False,
    }
    return ledger


def _write_csv(ledger: dict[str, Any], path: Path) -> None:
    fields = ["order_id", "status", "operator_action", "surface_id", "market_id", "token_id", "side", "strict_limit", "actual_refresh_price", "filled_usdc", "shares", "mtm_usdc", "pnl_usdc", "source_status", "station_status", "model_reason", "inconsistency_reason"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for order in ledger.get("orders", []):
            if isinstance(order, dict):
                writer.writerow({field: order.get(field) for field in fields})


def _actual_refresh_price(candidate: dict[str, Any], orderbook: dict[str, Any], side: str) -> float | None:
    explicit = _optional_float(candidate.get("actual_refresh_price", candidate.get("best_ask")))
    if explicit is not None:
        return explicit
    asks = normalize_orderbook_asks(orderbook, side=side)
    return round(asks[0]["price"], 6) if asks else None


def _copy_ledger(ledger: dict[str, Any] | None) -> dict[str, Any]:
    if not ledger:
        return {"orders": []}
    return json.loads(json.dumps(ledger))


def _default_order_id(candidate: dict[str, Any]) -> str:
    pieces = [candidate.get("run_id"), candidate.get("strategy_id"), candidate.get("profile_id"), candidate.get("surface_id"), candidate.get("market_id"), candidate.get("token_id"), candidate.get("side")]
    return ":".join(str(piece) for piece in pieces if piece is not None)


def _required_float(payload: dict[str, Any], key: str) -> float:
    value = _optional_float(payload.get(key))
    if value is None:
        raise PaperLedgerError(f"paper ledger candidate requires {key}")
    return value


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _cell(value: Any) -> str:
    return "" if value is None else str(value).replace("|", "\\|")


def _fmt(value: Any) -> str:
    if value is None:
        return ""
    return f"{float(value):.4f}"
