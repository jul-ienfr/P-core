from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any


def resolution_check_schedule_from_gamma_event(
    event: dict[str, Any],
    *,
    check_delay_seconds: int = 60,
) -> dict[str, Any]:
    """Return exact planned resolution timestamp and when automation should check it."""
    scheduled = _first_present(event, "resolutionTime", "resolution_time", "endDate", "endDateIso")
    out = {
        "resolution_scheduled_at": scheduled,
        "auto_check_after_seconds": int(check_delay_seconds),
        "auto_check_at": None,
    }
    dt = _parse_zulu_datetime(scheduled)
    if dt is not None:
        out["auto_check_at"] = _format_zulu(dt + timedelta(seconds=int(check_delay_seconds)))
    return out


def enrich_exited_position_with_official_outcome(position: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    """Annotate an EXIT_PAPER row with official final outcome without changing exit PnL.

    `EXIT_PAPER` is bookkeeping: the paper position was virtually closed earlier. The
    official result is still useful for postmortem, but must not overwrite the exit
    action or the realized PnL captured at exit time.
    """
    enriched = dict(position)
    current_exit_pnl = position.get("paper_realized_pnl_usdc")
    settlement = resolve_position_from_gamma_event(position, event)
    enriched.update(
        {
            "official_settlement_status": settlement.get("settlement_status"),
            "official_winning_outcome": settlement.get("winning_outcome"),
            "official_paper_settlement_value_usdc": settlement.get("paper_settlement_value_usdc"),
            "official_hold_to_settlement_pnl_usdc": settlement.get("paper_realized_pnl_usdc"),
            "official_settlement_source": settlement.get("settlement_source"),
            "resolution_scheduled_at": settlement.get("resolution_scheduled_at"),
            "resolution_checked_at": settlement.get("resolution_checked_at"),
        }
    )
    enriched["action"] = position.get("action")
    enriched["paper_realized_pnl_usdc"] = current_exit_pnl
    return enriched



def resolve_position_from_gamma_event(position: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    """Resolve a YES/NO paper position from a closed Polymarket/Gamma event payload.

    Gamma sometimes leaves winner/result null after close, while outcomePrices are already
    final 0/1. For paper settlement, closed + a unique 1.0 outcome is enough.
    """
    result = {
        "settlement_status": "UNSETTLED",
        "winning_outcome": None,
        "paper_settlement_value_usdc": None,
        "paper_realized_pnl_usdc": None,
        "settlement_source": "polymarket_not_final",
        "resolution_scheduled_at": _first_present(event, "resolutionTime", "resolution_time", "endDate", "endDateIso"),
        "resolution_checked_at": _first_present(event, "closedTime", "closed_time", "closedAt", "updatedAt", "updated_at"),
    }
    if not bool(event.get("closed")):
        return result

    market = _matching_market(position, event.get("markets") or [])
    if market is None or not bool(market.get("closed", event.get("closed"))):
        return result

    outcomes = _parse_jsonish_list(market.get("outcomes"))
    prices = [_safe_float(x) for x in _parse_jsonish_list(market.get("outcomePrices"))]
    if not outcomes or len(outcomes) != len(prices):
        return result

    winner_indices = [i for i, price in enumerate(prices) if price is not None and price >= 0.999]
    loser_indices = [i for i, price in enumerate(prices) if price is not None and price <= 0.001]
    if len(winner_indices) != 1 or len(loser_indices) < 1:
        return result

    winning_outcome = str(outcomes[winner_indices[0]])
    side = str(position.get("side") or "").strip().lower()
    shares = _safe_float(position.get("shares")) or 0.0
    spend = _safe_float(position.get("filled_usdc", position.get("spend_usdc"))) or 0.0
    won = side == winning_outcome.lower()
    settlement_value = round(shares if won else 0.0, 6)
    pnl = round(settlement_value - spend, 6)
    result.update(
        {
            "settlement_status": "SETTLED_WON" if won else "SETTLED_LOST",
            "winning_outcome": winning_outcome,
            "paper_settlement_value_usdc": settlement_value,
            "paper_realized_pnl_usdc": pnl,
            "settlement_source": "polymarket_closed_outcome_prices",
        }
    )
    return result


def _matching_market(position: dict[str, Any], markets: list[Any]) -> dict[str, Any] | None:
    question = str(position.get("question") or "").strip()
    token_id = str(position.get("token_id") or "").strip()
    for market in markets:
        if not isinstance(market, dict):
            continue
        if question and str(market.get("question") or "").strip() == question:
            return market
        if token_id:
            token_ids = [str(x) for x in _parse_jsonish_list(market.get("clobTokenIds"))]
            if token_id in token_ids:
                return market
    return None


def _parse_jsonish_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def _first_present(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, ""):
            return value
    return None


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_zulu_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text).astimezone(timezone.utc)
    except ValueError:
        return None


def _format_zulu(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
