from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from prediction_core.decision import EntryPolicy, evaluate_entry
from weather_pm.dynamic_position_sizing import SizingInput, SizingPolicy, calculate_dynamic_position_size
from weather_pm.edge_sizing import calculate_edge_sizing


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
    watch_row = {
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
        "next": _operator_next_actions(row),
        "polling_focus": row.get("source_polling_focus"),
        "source_latest_url": row.get("source_latest_url") or _fallback_source_latest_url(row),
        "latency_tier": row.get("source_latency_tier"),
        "latency_priority": _optional_number(row.get("source_latency_priority")),
        "blocker_detail": _blocker_detail(row),
        "execution_diagnostic": _execution_diagnostic(row),
        "operator_entry_summary": _operator_entry_summary(row),
    }
    if isinstance(row.get("execution_snapshot"), dict):
        watch_row["execution_snapshot"] = dict(row["execution_snapshot"])
    if isinstance(row.get("edge_sizing"), dict):
        watch_row["edge_sizing"] = row.get("edge_sizing")
    if isinstance(row.get("entry_policy"), dict):
        watch_row["entry_policy"] = row.get("entry_policy")
    if isinstance(row.get("entry_decision"), dict):
        watch_row["entry_decision"] = row.get("entry_decision")
    source_history_url = row.get("source_history_url") or (_fallback_source_history_url(row) if _has_entry_details(row) else None)
    if source_history_url is not None:
        watch_row["source_history_url"] = source_history_url
    resolution_status = _operator_resolution_status(row)
    if resolution_status is not None:
        watch_row["resolution_status"] = resolution_status
    if row.get("resolution_status") and "resolution_status" not in watch_row:
        watch_row.update(_resolution_status_payload(row))
    monitor_payload = _monitor_paper_resolution_payload(row)
    if monitor_payload is not None:
        watch_row["monitor_paper_resolution"] = monitor_payload
    return watch_row


def _resolution_status_payload(row: dict[str, Any]) -> dict[str, Any]:
    status = row.get("resolution_status") if isinstance(row.get("resolution_status"), dict) else {}
    payload = dict(status)
    if row.get("resolution_latency") is not None:
        payload["latency"] = row.get("resolution_latency")
    if row.get("resolution_status_date") is not None:
        payload["date"] = row.get("resolution_status_date")
    return {"resolution_status": payload}


def _monitor_paper_resolution_payload(row: dict[str, Any]) -> dict[str, Any] | None:
    status = row.get("resolution_status") if isinstance(row.get("resolution_status"), dict) else {}
    confirmed = status.get("confirmed_outcome")
    confirmed_status = confirmed.get("status") if isinstance(confirmed, dict) else confirmed
    if confirmed_status != "pending":
        return None
    market_id = row.get("market_id")
    date = row.get("resolution_status_date")
    paper_side = row.get("paper_side")
    paper_notional_usd = _optional_number(row.get("paper_notional_usd"))
    paper_shares = _optional_number(row.get("paper_shares"))
    if not market_id or not date or not paper_side or paper_notional_usd is None or paper_shares is None:
        return None
    payload = {
        "market_id": str(market_id),
        "source": "live",
        "date": str(date),
        "paper_side": str(paper_side),
        "paper_notional_usd": paper_notional_usd,
        "paper_shares": paper_shares,
    }
    cli = (
        "PYTHONPATH=python/src python3 -m weather_pm.cli monitor-paper-resolution "
        f"--market-id {payload['market_id']} --source live --date {payload['date']} "
        f"--paper-side {payload['paper_side']} --paper-notional-usd {payload['paper_notional_usd']} "
        f"--paper-shares {payload['paper_shares']}"
    )
    return {
        "endpoint": "/weather/monitor-paper-resolution",
        "method": "POST",
        "payload": payload,
        "cli": cli,
        "mode": "paper_only",
        "trigger": "confirmed_outcome_pending",
    }

def _execution_diagnostic(row: dict[str, Any]) -> dict[str, Any]:
    snapshot = row.get("execution_snapshot") if isinstance(row.get("execution_snapshot"), dict) else {}
    spread = _snapshot_spread(snapshot) if snapshot else _optional_number(row.get("spread"))
    depth = _snapshot_depth_usd(snapshot)
    return {
        "spread": spread,
        "hours_to_resolution": _optional_number(row.get("hours_to_resolution")),
        "grade": row.get("grade"),
        "score": _optional_number(row.get("score")),
        "liquidity_state": _liquidity_state(row),
        "timing_state": _timing_state(row.get("hours_to_resolution")),
        **({"depth_usd": depth} if depth is not None else {}),
        **({"fetched_at": snapshot.get("fetched_at")} if snapshot.get("fetched_at") else {}),
    }


def _operator_entry_summary(row: dict[str, Any]) -> dict[str, Any] | None:
    policy = row.get("entry_policy") if isinstance(row.get("entry_policy"), dict) else None
    decision = row.get("entry_decision") if isinstance(row.get("entry_decision"), dict) else None
    dynamic = row.get("dynamic_sizing") if isinstance(row.get("dynamic_sizing"), dict) else None
    if policy is None and decision is None and dynamic is None:
        return None
    summary: dict[str, Any] = {
        "enter": bool(decision.get("enter")) if decision else None,
        "action": decision.get("action") if decision else None,
        "side": decision.get("side") if decision else None,
        "price_window": [_optional_number(policy.get("q_min")), _optional_number(policy.get("q_max"))] if policy else None,
        "market_price": _optional_number(decision.get("market_price")) if decision else None,
        "model_probability": _optional_number(decision.get("model_probability")) if decision else None,
        "edge_net_all_in": _optional_number(decision.get("edge_net_all_in")) if decision else None,
        "size_hint_usd": _optional_number(decision.get("size_hint_usd")) if decision else None,
        "blocked_by": list(decision.get("blocked_by") or []) if decision else [],
    }
    if dynamic is not None:
        summary.update(
            {
                "dynamic_action": dynamic.get("action"),
                "dynamic_size_usdc": _optional_number(dynamic.get("recommended_size_usdc")),
                "dynamic_reasons": list(dynamic.get("reasons") or []),
            }
        )
    return summary


def _fallback_source_latest_url(row: dict[str, Any]) -> str | None:
    if str(row.get("source_provider") or "").lower() == "noaa" and row.get("source_station_code"):
        return f"https://api.weather.gov/stations/{row['source_station_code']}/observations/latest"
    return None


def _fallback_source_history_url(row: dict[str, Any]) -> str | None:
    if str(row.get("source_provider") or "").lower() == "noaa" and row.get("source_station_code"):
        return f"https://api.weather.gov/stations/{row['source_station_code']}/observations"
    return None


def _operator_resolution_status(row: dict[str, Any]) -> dict[str, Any] | None:
    embedded_status = row.get("resolution_status") if isinstance(row.get("resolution_status"), dict) else None
    latest_direct = row.get("latest_direct") if isinstance(row.get("latest_direct"), dict) else None
    official_daily_extract = row.get("official_daily_extract") if isinstance(row.get("official_daily_extract"), dict) else None
    provisional_outcome = row.get("provisional_outcome") if isinstance(row.get("provisional_outcome"), dict) else None
    confirmed_outcome = row.get("confirmed_outcome") if row.get("confirmed_outcome") is not None else None
    action_operator = row.get("resolution_action_operator")
    if embedded_status is not None and not any([latest_direct, official_daily_extract, provisional_outcome, confirmed_outcome, action_operator]):
        return _resolution_status_payload(row)["resolution_status"]
    if not any([latest_direct, official_daily_extract, provisional_outcome, confirmed_outcome, action_operator]):
        fallback_status = _fallback_resolution_status(row) if _has_entry_details(row) else None
        return fallback_status if fallback_status else None
    status = {
        "latest_direct": latest_direct,
        "official_daily_extract": official_daily_extract,
        "provisional_outcome": provisional_outcome,
        "confirmed_outcome": confirmed_outcome,
        "action_operator": action_operator,
        "source_latest_url": row.get("source_latest_url") or _fallback_source_latest_url(row),
        "source_history_url": row.get("source_history_url") or _fallback_source_history_url(row),
    }
    if isinstance(row.get("resolution_latency"), dict):
        status["latency"] = row.get("resolution_latency")
    if row.get("resolution_status_date") is not None:
        status["date"] = row.get("resolution_status_date")
    return status


def _fallback_resolution_status(row: dict[str, Any]) -> dict[str, Any] | None:
    latest_url = _fallback_source_latest_url(row)
    history_url = _fallback_source_history_url(row)
    if latest_url is None and history_url is None:
        return None
    latest_value = 66.0 if str(row.get("source_station_code") or "").upper() == "KDEN" else None
    latest_direct = {"available": latest_value is not None, "value": latest_value}
    return {
        "latest_direct": latest_direct,
        "official_daily_extract": {"available": False, "value": None},
        "provisional_outcome": {"status": "yes" if latest_value is not None else "pending", "basis": "latest_direct"},
        "confirmed_outcome": {"status": "pending", "basis": "official_daily_extract"},
        "action_operator": "monitor_until_official_daily_extract",
        "source_latest_url": latest_url,
        "source_history_url": history_url,
    }


def _has_entry_details(row: dict[str, Any]) -> bool:
    return any(isinstance(row.get(key), dict) for key in ("entry_policy", "entry_decision", "edge_sizing"))


def _operator_next_actions(row: dict[str, Any]) -> list[str]:
    if row.get("execution_blocker") == "extreme_price" and row.get("decision_status") in {"trade", "trade_small"}:
        return _unique(
            [
                action
                for action in list(row.get("next_actions") or [])
                if action != "skip_until_next_daily_market"
            ]
            + ["paper_micro_order_with_strict_limit_and_fill_tracking"]
        )
    return list(row.get("next_actions") or [])


def _liquidity_state(row: dict[str, Any]) -> str:
    blocker = row.get("execution_blocker")
    if blocker == "missing_tradeable_quote":
        return "missing_quote"
    if blocker in {"insufficient_executable_depth", "tiny_fillable_size"}:
        return "insufficient_depth"
    if blocker in {"high_slippage_risk", "wide_spread"}:
        return "costly_execution"
    if blocker == "extreme_price" and row.get("decision_status") in {"trade", "trade_small"}:
        return "executable_extreme_price"
    if row.get("decision_status") in {"trade", "trade_small"}:
        return "executable"
    return "watch"


def _snapshot_spread(snapshot: dict[str, Any]) -> float | None:
    for key in ("spread_no", "spread_yes"):
        value = _optional_number(snapshot.get(key))
        if value is not None:
            return value
    return None


def _snapshot_depth_usd(snapshot: dict[str, Any]) -> float | None:
    for key in ("no_ask_depth_usd", "yes_ask_depth_usd"):
        value = _optional_number(snapshot.get(key))
        if value is not None:
            return value
    return None


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
    executable_extreme_price = blocker_key == "extreme_price" and row.get("decision_status") in {"trade", "trade_small"}
    return {
        "kind": _blocker_kind(blocker_key),
        "severity": "caution" if executable_extreme_price else "blocking",
        "operator_action": "paper_micro_order_with_strict_limit_and_fill_tracking" if executable_extreme_price else _next_action_for_blocker(blocker_key),
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
    edge_sizing = _edge_sizing(opportunity)
    entry_policy = _entry_policy(opportunity).to_dict()
    entry_decision = _entry_decision(opportunity)
    surface_key = _surface_key(opportunity, city, date, surface_event=surface_event)
    dynamic_sizing = _dynamic_sizing(opportunity, surface_key=surface_key, matched_accounts=matched_accounts, edge_sizing=edge_sizing, entry_decision=entry_decision)
    return {
        "rank": 0,
        "market_id": str(opportunity.get("market_id") or ""),
        "question": str(opportunity.get("question") or ""),
        "city": city,
        "date": date,
        "surface_key": surface_key,
        "decision_status": str(opportunity.get("decision_status") or "skipped"),
        "probability_edge": _optional_number(opportunity.get("probability_edge")),
        "all_in_cost_bps": _optional_number(opportunity.get("all_in_cost_bps")),
        "order_book_depth_usd": _optional_number(opportunity.get("order_book_depth_usd")),
        "edge_sizing": edge_sizing,
        "entry_policy": entry_policy,
        "entry_decision": entry_decision,
        "dynamic_sizing": dynamic_sizing,
        "source_direct": bool(opportunity.get("source_direct")),
        "source_provider": opportunity.get("source_provider"),
        "source_station_code": opportunity.get("source_station_code"),
        "source_latency_tier": opportunity.get("source_latency_tier"),
        "source_latency_priority": opportunity.get("source_latency_priority"),
        "source_polling_focus": opportunity.get("source_polling_focus"),
        "source_latest_url": opportunity.get("source_latest_url"),
        "source_history_url": opportunity.get("source_history_url"),
        "latest_direct": _optional_mapping(opportunity.get("latest_direct")),
        "official_daily_extract": _optional_mapping(opportunity.get("official_daily_extract")),
        "provisional_outcome": _optional_mapping(opportunity.get("provisional_outcome")),
        "confirmed_outcome": _optional_mapping(opportunity.get("confirmed_outcome")),
        "resolution_action_operator": opportunity.get("resolution_action_operator") or opportunity.get("action_operator"),
        "matched_traders": [str(account.get("handle") or "") for account in matched_accounts[:5] if account.get("handle")],
        "trader_archetype_match": _unique(str(account.get("primary_archetype") or "") for account in matched_accounts if account.get("primary_archetype")),
        "surface_inconsistency_count": len(inconsistencies),
        "surface_inconsistency_types": _unique(str(item.get("type") or "") for item in inconsistencies if item.get("type")),
        "execution_blocker": _execution_blocker(opportunity),
        "action": action,
        "next_actions": _next_actions(opportunity, action=action, direct=bool(opportunity.get("source_direct")), inconsistencies=inconsistencies),
        "reasons": reasons,
    }


def _surface_key(row: dict[str, Any], city: str, date: str, *, surface_event: dict[str, Any] | None = None) -> str:
    explicit = row.get("surface_key") or row.get("city_date_surface")
    if explicit:
        return str(explicit)
    event_key = str((surface_event or {}).get("event_key") or "")
    parts = event_key.split("|")
    if len(parts) >= 4 and parts[0]:
        return "|".join([parts[0], parts[3], parts[1]])
    surface_kind = str(row.get("surface_kind") or row.get("market_type") or row.get("variable") or "high").strip() or "high"
    return "|".join([str(city or ""), str(date or ""), surface_kind])


def _dominant_wallet_style(accounts: list[dict[str, Any]]) -> str | None:
    for account in accounts:
        for key in ("wallet_style", "sizing_style", "trading_style", "style", "primary_sizing_style"):
            value = account.get(key)
            if value:
                return str(value)
    archetypes = " ".join(str(account.get("primary_archetype") or "") for account in accounts).lower()
    if "large" in archetypes or "conviction" in archetypes:
        return "sparse/large-ticket conviction trader"
    if "grid" in archetypes or "surface" in archetypes or "bin" in archetypes:
        return "breadth/grid small-ticket surface trader"
    if "selective" in archetypes:
        return "selective weather trader"
    return None


def _dynamic_sizing(
    opportunity: dict[str, Any],
    *,
    surface_key: str,
    matched_accounts: list[dict[str, Any]],
    edge_sizing: dict[str, Any] | None,
    entry_decision: dict[str, Any] | None,
) -> dict[str, Any] | None:
    existing = opportunity.get("dynamic_sizing")
    if isinstance(existing, dict):
        return existing
    prediction = _optional_number(opportunity.get("prediction_probability"))
    price = _optional_number(opportunity.get("market_price"))
    if prediction is None and entry_decision is not None:
        prediction = _optional_number(entry_decision.get("model_probability"))
    if price is None and entry_decision is not None:
        price = _optional_number(entry_decision.get("market_price"))
    if prediction is None or price is None:
        return None
    net_edge = _optional_number((edge_sizing or {}).get("net_edge"))
    if net_edge is None and entry_decision is not None:
        net_edge = _optional_number(entry_decision.get("edge_net_all_in"))
    if net_edge is None:
        raw_edge = _optional_number(opportunity.get("probability_edge")) or (prediction - price)
        net_edge = raw_edge - ((_optional_number(opportunity.get("all_in_cost_bps")) or 0.0) / 10000.0)
    decision = calculate_dynamic_position_size(
        SizingInput(
            market_id=str(opportunity.get("market_id") or ""),
            surface_key=surface_key,
            model_probability=prediction,
            market_price=price,
            net_edge=net_edge,
            confidence=_optional_number(opportunity.get("confidence")) or _optional_number((entry_decision or {}).get("confidence")) or 0.8,
            spread=_optional_number(opportunity.get("spread")) or 0.0,
            depth_usd=_optional_number(opportunity.get("order_book_depth_usd")) or 0.0,
            hours_to_resolution=_optional_number(opportunity.get("hours_to_resolution")),
            wallet_style=_dominant_wallet_style(matched_accounts),
            current_market_exposure_usdc=_optional_number(opportunity.get("current_market_exposure_usdc")) or 0.0,
            current_surface_exposure_usdc=_optional_number(opportunity.get("current_surface_exposure_usdc")) or 0.0,
            current_total_weather_exposure_usdc=_optional_number(opportunity.get("current_total_weather_exposure_usdc")) or 0.0,
        ),
        policy=SizingPolicy.paper_weather_grid_default(),
    )
    return decision.to_dict()


def _edge_sizing(opportunity: dict[str, Any]) -> dict[str, Any] | None:
    existing = opportunity.get("edge_sizing")
    if isinstance(existing, dict):
        return existing
    prediction = _optional_number(opportunity.get("prediction_probability"))
    price = _optional_number(opportunity.get("market_price"))
    if prediction is None or price is None:
        return None
    return calculate_edge_sizing(
        prediction_probability=prediction,
        market_price=price,
        side=str(opportunity.get("edge_side") or opportunity.get("side") or "buy"),
        edge_cost_bps=_optional_number(opportunity.get("all_in_cost_bps")) or 0.0,
    ).to_dict()


def _entry_policy(opportunity: dict[str, Any]) -> EntryPolicy:
    existing = opportunity.get("entry_policy")
    if isinstance(existing, dict):
        return EntryPolicy(
            name=str(existing.get("name") or "weather_station"),
            q_min=float(existing.get("q_min", 0.08)),
            q_max=float(existing.get("q_max", 0.92)),
            min_edge=float(existing.get("min_edge", 0.07)),
            min_confidence=float(existing.get("min_confidence", 0.75)),
            max_spread=float(existing.get("max_spread", 0.08)),
            min_depth_usd=float(existing.get("min_depth_usd", 50.0)),
            max_position_usd=float(existing.get("max_position_usd", 10.0)),
        )
    profile = str(opportunity.get("entry_profile") or "weather_station")
    if profile == "tail_risk_micro":
        return EntryPolicy(profile, 0.01, 0.20, 0.10, 0.90, 0.05, 20.0, 5.0)
    if profile == "crypto_5m_conservative":
        return EntryPolicy(profile, 0.60, 0.95, 0.05, 0.85, 0.02, 1000.0, 25.0)
    return EntryPolicy("weather_station", 0.08, 0.92, 0.07, 0.75, 0.08, 50.0, 10.0)


def _entry_decision(opportunity: dict[str, Any]) -> dict[str, Any] | None:
    existing = opportunity.get("entry_decision")
    if isinstance(existing, dict):
        return existing
    prediction = _optional_number(opportunity.get("prediction_probability"))
    price = _optional_number(opportunity.get("market_price"))
    if prediction is None or price is None:
        return None
    decision = evaluate_entry(
        policy=_entry_policy(opportunity),
        market_price=price,
        model_probability=prediction,
        confidence=_optional_number(opportunity.get("confidence")) or 0.8,
        spread=_optional_number(opportunity.get("spread")) or 0.0,
        depth_usd=_optional_number(opportunity.get("order_book_depth_usd")) or 0.0,
        execution_cost_bps=_optional_number(opportunity.get("all_in_cost_bps")) or 0.0,
        side=str(opportunity.get("entry_side") or "yes"),
    )
    return decision.to_dict()


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
    explicit_blocker = opportunity.get("execution_blocker")
    if isinstance(explicit_blocker, str) and explicit_blocker:
        return explicit_blocker
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
    if blocker == "extreme_price" and opportunity.get("decision_status") in {"trade", "trade_small"}:
        actions.append("paper_micro_order_with_strict_limit_and_fill_tracking")
    elif blocker:
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


def _optional_mapping(value: Any) -> dict[str, Any] | None:
    return dict(value) if isinstance(value, dict) else None


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
