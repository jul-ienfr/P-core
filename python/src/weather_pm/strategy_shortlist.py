from __future__ import annotations

import re
from collections import defaultdict
from typing import Any


def build_strategy_shortlist(
    strategy_report: dict[str, Any],
    opportunity_report: dict[str, Any],
    event_surface: dict[str, Any] | None = None,
    *,
    limit: int = 25,
) -> dict[str, Any]:
    opportunities = [item for item in opportunity_report.get("opportunities", []) if isinstance(item, dict)]
    accounts = [item for item in strategy_report.get("accounts", []) if isinstance(item, dict)]
    surface_events = [item for item in (event_surface or {}).get("events", []) if isinstance(item, dict)]
    city_accounts = _accounts_by_city(accounts)
    surface_by_city_date = _surface_by_city_date(surface_events)

    rows = []
    for opportunity in opportunities:
        question = str(opportunity.get("question") or "")
        city, date = _parse_city_date(question)
        matched_accounts = city_accounts.get(city, []) if city else []
        surface_event = surface_by_city_date.get((city, date), {}) if city and date else {}
        row = _shortlist_row(opportunity, city=city, date=date, matched_accounts=matched_accounts, surface_event=surface_event)
        rows.append(row)

    ranked = sorted(rows, key=_shortlist_sort_key)[: max(int(limit), 0)]
    for index, row in enumerate(ranked, start=1):
        row["rank"] = index

    return {
        "summary": {
            "input_opportunities": len(opportunities),
            "strategy_accounts": len(accounts),
            "surface_events": len(surface_events),
            "shortlisted": len(ranked),
        },
        "shortlist": ranked,
    }


def _accounts_by_city(accounts: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for account in accounts:
        for item in account.get("top_cities") or []:
            if isinstance(item, dict) and item.get("city"):
                result[str(item["city"])].append(account)
    for city in result:
        result[city].sort(key=lambda account: float(account.get("weather_pnl_usd") or 0.0), reverse=True)
    return dict(result)


def _surface_by_city_date(events: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for event in events:
        key = str(event.get("event_key") or "")
        parts = key.split("|")
        if len(parts) >= 4:
            result[(parts[0], parts[3])] = event
    return result


def _shortlist_row(
    opportunity: dict[str, Any],
    *,
    city: str,
    date: str,
    matched_accounts: list[dict[str, Any]],
    surface_event: dict[str, Any],
) -> dict[str, Any]:
    inconsistencies = [item for item in surface_event.get("inconsistencies", []) if isinstance(item, dict)] if surface_event else []
    reasons = _reasons(opportunity, matched_accounts=matched_accounts, inconsistencies=inconsistencies)
    action = _action(opportunity, direct=bool(opportunity.get("source_direct")), inconsistencies=inconsistencies)
    return {
        "rank": 0,
        "market_id": str(opportunity.get("market_id") or ""),
        "question": str(opportunity.get("question") or ""),
        "city": city,
        "date": date,
        "decision_status": str(opportunity.get("decision_status") or "skipped"),
        "probability_edge": _optional_number(opportunity.get("probability_edge")),
        "all_in_cost_bps": _optional_number(opportunity.get("all_in_cost_bps")),
        "order_book_depth_usd": _optional_number(opportunity.get("order_book_depth_usd")),
        "source_direct": bool(opportunity.get("source_direct")),
        "source_latency_tier": opportunity.get("source_latency_tier"),
        "matched_traders": [str(account.get("handle") or "") for account in matched_accounts[:5] if account.get("handle")],
        "trader_archetype_match": _unique(str(account.get("primary_archetype") or "") for account in matched_accounts if account.get("primary_archetype")),
        "surface_inconsistency_count": len(inconsistencies),
        "surface_inconsistency_types": _unique(str(item.get("type") or "") for item in inconsistencies if item.get("type")),
        "action": action,
        "reasons": reasons,
    }


def _reasons(opportunity: dict[str, Any], *, matched_accounts: list[dict[str, Any]], inconsistencies: list[dict[str, Any]]) -> list[str]:
    reasons: list[str] = []
    if opportunity.get("decision_status") in {"trade", "trade_small"}:
        reasons.append("tradeable_decision")
    if inconsistencies:
        reasons.append("surface_anomaly")
    if matched_accounts:
        reasons.append("profitable_trader_city")
    if opportunity.get("source_direct"):
        reasons.append("direct_resolution_source")
    edge = _optional_number(opportunity.get("probability_edge")) or 0.0
    if edge > 0:
        reasons.append("positive_probability_edge")
    return reasons


def _action(opportunity: dict[str, Any], *, direct: bool, inconsistencies: list[dict[str, Any]]) -> str:
    if opportunity.get("decision_status") in {"trade", "trade_small"}:
        if direct:
            return "paper_trade_watch_direct_station"
        return "paper_trade_watch_fallback_source"
    if inconsistencies:
        return "review_surface_anomaly"
    return "watch_only"


def _shortlist_sort_key(row: dict[str, Any]) -> tuple[int, float, str]:
    tradeable = row.get("decision_status") in {"trade", "trade_small"}
    direct = bool(row.get("source_direct"))
    anomaly_count = int(row.get("surface_inconsistency_count") or 0)
    trader_count = len(row.get("matched_traders") or [])
    edge = _optional_number(row.get("probability_edge")) or 0.0
    cost = _optional_number(row.get("all_in_cost_bps")) or 0.0
    depth = _optional_number(row.get("order_book_depth_usd")) or 0.0
    score = (1000.0 if tradeable else 0.0) + (75.0 if direct else 0.0) + anomaly_count * 125.0 + trader_count * 80.0 + edge * 100.0 + min(depth / 100.0, 25.0) - cost / 100.0
    return (0 if tradeable else 1, -score, str(row.get("market_id") or ""))


def _parse_city_date(question: str) -> tuple[str, str]:
    dated_match = re.search(r"temperature in (?P<city>.+?) be .+? on (?P<date>.+?)\?", question, re.I)
    if dated_match:
        return dated_match.group("city"), dated_match.group("date")
    city_match = re.search(r"temperature in (?P<city>.+?) be ", question, re.I)
    if city_match:
        return city_match.group("city"), ""
    return "", ""


def _optional_number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), 6)
    except (TypeError, ValueError):
        return None


def _unique(values: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
