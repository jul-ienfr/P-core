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
        surface_event = surface_by_city_date.get((city, date), {}) if city else {}
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
            "action_counts": _counts(row.get("action") for row in ranked),
            "execution_blocker_counts": _counts(row.get("execution_blocker") for row in ranked),
        },
        "shortlist": ranked,
    }


def build_operator_shortlist_report(payload: dict[str, Any], *, limit: int = 10) -> dict[str, Any]:
    shortlist = [item for item in payload.get("shortlist", []) if isinstance(item, dict)]
    action_counts = _dict_counts(payload.get("summary", {}).get("action_counts", {}))
    blocker_counts = _dict_counts(payload.get("summary", {}).get("execution_blocker_counts", {}))
    artifacts = payload.get("artifacts", {}) if isinstance(payload.get("artifacts"), dict) else {}
    return {
        "run_id": payload.get("run_id"),
        "source": payload.get("source"),
        "summary": {
            "shortlisted": int(payload.get("summary", {}).get("shortlisted") or len(shortlist)),
            "tradeable_count": sum(1 for row in shortlist if row.get("decision_status") in {"trade", "trade_small"}),
            "direct_source_count": sum(1 for row in shortlist if row.get("source_direct")),
            "surface_anomaly_count": sum(1 for row in shortlist if int(row.get("surface_inconsistency_count") or 0) > 0),
            "blocked_count": sum(1 for row in shortlist if row.get("execution_blocker")),
            "top_actions": list(action_counts),
            "top_blockers": list(blocker_counts),
        },
        "operator_focus": _operator_focus(action_counts, blocker_counts),
        "watchlist": [_operator_watch_row(row) for row in shortlist[: max(int(limit), 0)]],
        "artifacts": {"source_shortlist_json": artifacts.get("output_json")},
    }


def _operator_watch_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "rank": row.get("rank"),
        "market_id": row.get("market_id"),
        "city": row.get("city"),
        "date": row.get("date"),
        "action": row.get("action"),
        "decision_status": row.get("decision_status"),
        "edge": row.get("probability_edge"),
        "all_in_cost_bps": row.get("all_in_cost_bps"),
        "depth_usd": row.get("order_book_depth_usd"),
        "direct_source": _direct_source_label(row),
        "matched_traders": list(row.get("matched_traders") or []),
        "anomalies": list(row.get("surface_inconsistency_types") or []),
        "blocker": row.get("execution_blocker"),
        "next": list(row.get("next_actions") or []),
        "polling_focus": row.get("source_polling_focus"),
        "source_latest_url": row.get("source_latest_url"),
        "blocker_detail": _blocker_detail(row),
        "execution_diagnostic": _execution_diagnostic(row),
    }


def _execution_diagnostic(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "spread": _optional_number(row.get("spread")),
        "hours_to_resolution": _optional_number(row.get("hours_to_resolution")),
        "grade": row.get("grade"),
        "score": _optional_number(row.get("score")),
        "liquidity_state": _liquidity_state(row),
        "timing_state": _timing_state(row.get("hours_to_resolution")),
    }


def _liquidity_state(row: dict[str, Any]) -> str:
    blocker = row.get("execution_blocker")
    if blocker == "missing_tradeable_quote":
        return "missing_quote"
    if blocker in {"insufficient_executable_depth", "tiny_fillable_size"}:
        return "insufficient_depth"
    if blocker in {"high_slippage_risk", "wide_spread"}:
        return "costly_execution"
    if row.get("decision_status") in {"trade", "trade_small"}:
        return "executable"
    return "watch"


def _timing_state(value: Any) -> str:
    hours = _optional_number(value)
    if hours is None:
        return "unknown"
    if hours <= 12:
        return "near_resolution"
    if hours <= 36:
        return "next_day"
    return "later"


def _blocker_detail(row: dict[str, Any]) -> dict[str, Any] | None:
    blocker = row.get("execution_blocker")
    if not blocker:
        return None
    blocker_key = str(blocker)
    return {
        "kind": _blocker_kind(blocker_key),
        "severity": "blocking",
        "operator_action": _next_action_for_blocker(blocker_key),
        "polling_focus": row.get("source_polling_focus"),
        "source_latest_url": row.get("source_latest_url"),
    }


def _blocker_kind(blocker: str) -> str:
    if blocker in {"missing_tradeable_quote", "insufficient_executable_depth", "tiny_fillable_size"}:
        return "quote_missing" if blocker == "missing_tradeable_quote" else "depth_insufficient"
    if blocker in {"high_slippage_risk", "wide_spread"}:
        return "execution_cost"
    if blocker in {"market_already_resolving_or_resolved", "extreme_price"}:
        return "market_state"
    if blocker == "decision_not_tradeable":
        return "edge_insufficient"
    return "execution_blocker"


def _direct_source_label(row: dict[str, Any]) -> str | None:
    if not row.get("source_direct"):
        return None
    provider = row.get("source_provider") or "direct"
    station = row.get("source_station_code")
    return f"{provider}:{station}" if station else str(provider)


def _operator_focus(action_counts: dict[str, int], blocker_counts: dict[str, int]) -> list[str]:
    focus: list[str] = []
    for key, value in action_counts.items():
        if key.startswith("paper_trade"):
            focus.append(f"{key}: {value}")
    for key, value in blocker_counts.items():
        focus.append(f"{key}: {value}")
    return focus


def _dict_counts(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {str(key): int(count) for key, count in value.items() if key and int(count or 0) > 0}


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
        "source_provider": opportunity.get("source_provider"),
        "source_station_code": opportunity.get("source_station_code"),
        "source_latency_tier": opportunity.get("source_latency_tier"),
        "source_latency_priority": opportunity.get("source_latency_priority"),
        "source_polling_focus": opportunity.get("source_polling_focus"),
        "source_latest_url": opportunity.get("source_latest_url"),
        "matched_traders": [str(account.get("handle") or "") for account in matched_accounts[:5] if account.get("handle")],
        "trader_archetype_match": _unique(str(account.get("primary_archetype") or "") for account in matched_accounts if account.get("primary_archetype")),
        "surface_inconsistency_count": len(inconsistencies),
        "surface_inconsistency_types": _unique(str(item.get("type") or "") for item in inconsistencies if item.get("type")),
        "execution_blocker": _execution_blocker(opportunity),
        "action": action,
        "next_actions": _next_actions(opportunity, action=action, direct=bool(opportunity.get("source_direct")), inconsistencies=inconsistencies),
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


def _execution_blocker(opportunity: dict[str, Any]) -> str | None:
    skip_reason = opportunity.get("skip_reason")
    if isinstance(skip_reason, str) and skip_reason:
        return skip_reason
    status = str(opportunity.get("decision_status") or "")
    if status and status not in {"trade", "trade_small"}:
        return status
    return None


def _next_actions(opportunity: dict[str, Any], *, action: str, direct: bool, inconsistencies: list[dict[str, Any]]) -> list[str]:
    actions: list[str] = []
    if direct:
        actions.append("poll_direct_resolution_source")
    if inconsistencies:
        actions.append("inspect_event_surface_prices")
    blocker = _execution_blocker(opportunity)
    if blocker:
        actions.append(_next_action_for_blocker(blocker))
    elif action.startswith("paper_trade"):
        actions.append("paper_order_with_limit_and_fill_tracking")
    else:
        actions.append("keep_on_watchlist")
    return _unique(actions)


def _next_action_for_blocker(blocker: str) -> str:
    if blocker in {"missing_tradeable_quote", "insufficient_executable_depth", "tiny_fillable_size"}:
        return "wait_for_executable_depth"
    if blocker in {"high_slippage_risk", "wide_spread"}:
        return "wait_for_tighter_spread"
    if blocker in {"market_already_resolving_or_resolved", "extreme_price"}:
        return "skip_until_next_daily_market"
    if blocker == "decision_not_tradeable":
        return "watch_for_edge_or_execution_improvement"
    return "review_execution_blocker"


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


def _counts(values: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        if not value:
            continue
        key = str(value)
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _unique(values: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
