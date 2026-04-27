from __future__ import annotations

from collections import Counter
from typing import Any

from weather_pm.market_parser import parse_market_question

RECOMMENDATION_LABELS = {
    "paper_micro_strict_limit",
    "watch_or_paper_if_source_confirms",
    "priced_in",
    "source_missing_do_not_trade",
    "avoid_price_too_high",
    "confirm_source_first",
}


def evaluate_threshold_watch(
    market: dict[str, Any],
    *,
    hours_to_resolution: float | None = None,
    observed_value: float | None = None,
    near_resolution_hours: float = 12.0,
    strong_margin: float = 1.0,
    priced_in_ask: float = 0.9,
) -> dict[str, Any]:
    structure = parse_market_question(str(market.get("question") or ""))
    if not structure.is_threshold:
        raise ValueError("threshold watcher only supports threshold markets")

    hours = _number(hours_to_resolution if hours_to_resolution is not None else market.get("hours_to_resolution"))
    source_value = _source_value(market, observed_value)
    threshold = _number(structure.target_value) or 0.0
    direction = str(structure.threshold_direction or "")
    threshold_kind = "threshold_high" if direction == "higher" else "threshold_low" if direction == "below" else "threshold"
    source_status = str(market.get("source_status") or market.get("source", {}).get("status") if isinstance(market.get("source"), dict) else "")
    source_confirmed = _source_confirmed(market, source_status)
    top_ask = _top_ask(market)
    strict_limit = _strict_limit(market)

    favored_side = None
    margin = None
    if source_value is not None:
        if direction == "higher":
            margin = round(abs(source_value - threshold), 6)
            favored_side = "YES" if source_value >= threshold else "NO"
        elif direction == "below":
            margin = round(abs(threshold - source_value), 6)
            favored_side = "YES" if source_value <= threshold else "NO"

    candidate_side = str(market.get("candidate_side") or favored_side or "YES").upper()
    near_resolution = hours is not None and hours <= near_resolution_hours
    blocker = None
    reason = "near_resolution_threshold_source_edge" if near_resolution else "not_near_resolution"

    if not source_confirmed:
        if str(source_status).startswith("source_missing") or market.get("source_direct") is False:
            recommendation = "source_missing_do_not_trade"
            blocker = "source_missing"
        else:
            recommendation = "confirm_source_first"
            blocker = "source_unconfirmed"
    elif source_value is None:
        recommendation = "confirm_source_first"
        blocker = "source_value_missing"
    elif not near_resolution:
        recommendation = "watch_or_paper_if_source_confirms"
        blocker = "not_near_resolution"
    elif favored_side != candidate_side:
        recommendation = "watch_or_paper_if_source_confirms"
        blocker = "candidate_side_not_source_favored"
    elif top_ask is not None and strict_limit is not None and top_ask > strict_limit:
        recommendation = "avoid_price_too_high"
        blocker = "price_above_strict_limit"
    elif top_ask is not None and top_ask >= priced_in_ask:
        recommendation = "priced_in"
        blocker = "priced_in_high_certainty"
    elif margin is not None and margin >= strong_margin:
        recommendation = "paper_micro_strict_limit"
    else:
        recommendation = "watch_or_paper_if_source_confirms"
        blocker = "source_margin_not_strong"

    return {
        "market_id": str(market.get("market_id") or market.get("id") or ""),
        "question": str(market.get("question") or ""),
        "eligible": recommendation in {"paper_micro_strict_limit", "watch_or_paper_if_source_confirms", "priced_in"} and blocker not in {"source_missing", "price_above_strict_limit"},
        "threshold_kind": threshold_kind,
        "threshold_direction": direction,
        "threshold": threshold,
        "hours_to_resolution": hours,
        "source_status": source_status or ("source_confirmed" if source_confirmed else "source_missing"),
        "source_confirmed": source_confirmed,
        "source_value": source_value,
        "source_margin": margin,
        "favored_side": favored_side,
        "candidate_side": candidate_side,
        "top_ask": top_ask,
        "strict_limit": strict_limit,
        "recommendation": recommendation,
        "blocker": blocker,
        "reason": reason,
    }


def build_threshold_watch_report(
    surface_or_report: dict[str, Any],
    *,
    hours_to_resolution: float | None = None,
    observed_value: float | None = None,
    limit: int = 25,
) -> dict[str, Any]:
    raw_markets = _extract_markets(surface_or_report)
    source = surface_or_report.get("source") if isinstance(surface_or_report.get("source"), dict) else {}
    threshold_rows = []
    for market in raw_markets:
        normalized = _normalize_market(market, source=source, hours_to_resolution=hours_to_resolution, observed_value=observed_value)
        try:
            row = evaluate_threshold_watch(normalized, hours_to_resolution=hours_to_resolution, observed_value=observed_value)
        except ValueError:
            continue
        threshold_rows.append(row)

    threshold_rows.sort(key=_watch_sort_key)
    threshold_rows = threshold_rows[: max(int(limit), 0)]
    counts = Counter(str(row.get("recommendation")) for row in threshold_rows if row.get("recommendation"))
    return {
        "summary": {
            "input_markets": len(raw_markets),
            "threshold_markets": len(threshold_rows),
            "near_resolution_thresholds": sum(1 for row in threshold_rows if row.get("hours_to_resolution") is not None and float(row["hours_to_resolution"]) <= 12.0),
            "recommendation_counts": dict(sorted(counts.items())),
        },
        "threshold_watch": threshold_rows,
    }


def _extract_markets(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("markets", "shortlist", "opportunities", "threshold_watch"):
        value = payload.get(key)
        if isinstance(value, list):
            return [dict(item) for item in value if isinstance(item, dict)]
    return []


def _normalize_market(market: dict[str, Any], *, source: dict[str, Any], hours_to_resolution: float | None, observed_value: float | None) -> dict[str, Any]:
    normalized = dict(market)
    normalized.setdefault("market_id", market.get("id"))
    if source:
        status = str(source.get("status") or "")
        normalized.setdefault("source_status", "source_confirmed" if status == "source_confirmed_fixture" else status)
        normalized.setdefault("source_provider", source.get("provider"))
        normalized.setdefault("source_station_code", source.get("station_code"))
        if source.get("station_code"):
            normalized.setdefault("source_direct", True)
    if hours_to_resolution is not None:
        normalized.setdefault("hours_to_resolution", hours_to_resolution)
    if observed_value is not None:
        normalized.setdefault("latest_direct", {"available": True, "value": observed_value})
    orderbook = normalized.get("orderbook") if isinstance(normalized.get("orderbook"), dict) else {}
    if orderbook:
        normalized.setdefault("top_ask", orderbook.get("best_ask"))
    if str(normalized.get("contract_kind") or "") == "threshold_high":
        normalized.setdefault("candidate_side", "YES")
    elif str(normalized.get("contract_kind") or "") == "threshold_low":
        normalized.setdefault("candidate_side", "NO")
    return normalized


def _source_confirmed(market: dict[str, Any], source_status: str) -> bool:
    if source_status in {"source_confirmed", "source_confirmed_fixture"}:
        return True
    if market.get("source_direct") and (market.get("source_station_code") or market.get("source_provider")):
        return True
    return False


def _source_value(market: dict[str, Any], observed_value: float | None) -> float | None:
    explicit = _number(observed_value)
    if explicit is not None:
        return explicit
    for key in ("latest_direct", "official_daily_extract"):
        payload = market.get(key)
        if isinstance(payload, dict) and payload.get("available", True):
            value = _number(payload.get("value"))
            if value is not None:
                return value
    return _number(market.get("source_value") or market.get("observed_value"))


def _top_ask(market: dict[str, Any]) -> float | None:
    for key in ("top_ask", "market_price", "yes_price"):
        value = _number(market.get(key))
        if value is not None:
            return value
    orderbook = market.get("orderbook")
    if isinstance(orderbook, dict):
        return _number(orderbook.get("best_ask"))
    return None


def _strict_limit(market: dict[str, Any]) -> float | None:
    for key in ("strict_limit_no_market_buy", "strict_limit"):
        value = _number(market.get(key))
        if value is not None:
            return value
    return None


def _watch_sort_key(row: dict[str, Any]) -> tuple[int, float, str]:
    priority = {
        "paper_micro_strict_limit": 0,
        "watch_or_paper_if_source_confirms": 1,
        "priced_in": 2,
        "avoid_price_too_high": 3,
        "confirm_source_first": 4,
        "source_missing_do_not_trade": 5,
    }.get(str(row.get("recommendation")), 9)
    margin = abs(float(row.get("source_margin") or 0.0))
    return (priority, -margin, str(row.get("market_id") or ""))


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), 6)
    except (TypeError, ValueError):
        return None
