from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any


def build_profitable_accounts_operator_summary(
    *,
    classified_accounts_csv: str | Path,
    reverse_engineering_json: str | Path,
    operator_report_json: str | Path,
    priority_limit: int = 10,
) -> dict[str, Any]:
    """Bridge profitable weather traders to the current operator watchlist.

    This is intentionally compact: it turns the large classified leaderboard and
    reverse-engineering report into the small handoff artifact an operator needs
    before deciding whether a live Polymarket weather row deserves paper/live
    attention.
    """

    reverse_path = Path(reverse_engineering_json)
    operator_path = Path(operator_report_json)
    reverse_payload = _load_json_object(reverse_path)
    raw_operator_payload = _load_json_object(operator_path)
    operator_payload = _operator_payload(raw_operator_payload)
    accounts = _merge_csv_classification(
        [account for account in reverse_payload.get("accounts", []) if isinstance(account, dict)],
        Path(classified_accounts_csv),
    )
    watchlist = [row for row in operator_payload.get("watchlist", []) if isinstance(row, dict)]

    priority_accounts = _priority_accounts(accounts, limit=priority_limit)
    handle_lookup = {str(account.get("handle") or ""): account for account in accounts}
    enriched_watchlist = [_watchlist_row(row, handle_lookup=handle_lookup) for row in watchlist]
    live_matched_accounts = _live_matched_accounts(enriched_watchlist)

    live_match_summary = _live_matched_accounts_summary(
        live_matched_accounts,
        enriched_watchlist=enriched_watchlist,
    )
    live_market_signal_cards = _live_market_signal_cards(enriched_watchlist)
    return {
        "generated_from": {
            "classified_accounts_csv": str(classified_accounts_csv),
            "reverse_engineering_json": str(reverse_engineering_json),
            "operator_report_json": str(operator_report_json),
        },
        "classified_account_counts": _classified_counts(accounts),
        "priority_weather_accounts": priority_accounts,
        "live_operator_summary": operator_payload.get("summary", {}),
        "live_operator_focus": list(operator_payload.get("operator_focus") or []),
        "live_watchlist": enriched_watchlist,
        "live_matched_profitable_weather_summary": live_match_summary,
        "live_market_signal_cards": live_market_signal_cards,
        "live_matched_profitable_weather_accounts": live_matched_accounts,
        "discord_operator_brief": _discord_operator_brief(
            live_market_signal_cards,
            live_match_summary=live_match_summary,
        ),
    }




def write_profitable_accounts_operator_summary(
    *,
    classified_accounts_csv: str | Path,
    reverse_engineering_json: str | Path,
    operator_report_json: str | Path,
    output_json: str | Path,
    priority_limit: int = 10,
) -> dict[str, Any]:
    payload = build_profitable_accounts_operator_summary(
        classified_accounts_csv=classified_accounts_csv,
        reverse_engineering_json=reverse_engineering_json,
        operator_report_json=operator_report_json,
        priority_limit=priority_limit,
    )
    output_path = Path(output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True))
    return _compact_summary(payload, output_path=output_path)


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _operator_payload(payload: dict[str, Any]) -> dict[str, Any]:
    nested = payload.get("operator")
    if isinstance(nested, dict) and isinstance(nested.get("watchlist"), list):
        return nested
    return payload


def _merge_csv_classification(accounts: list[dict[str, Any]], classified_accounts_csv: Path) -> list[dict[str, Any]]:
    csv_accounts = _classified_accounts_by_handle(classified_accounts_csv)
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for account in accounts:
        handle = _account_handle(account)
        csv_account = csv_accounts.get(handle)
        if csv_account:
            merged_account = {**csv_account, **account}
            for key, value in csv_account.items():
                if _is_missing_account_value(merged_account.get(key)):
                    merged_account[key] = value
            merged.append(merged_account)
            seen.add(handle)
        else:
            merged.append(account)
            if handle:
                seen.add(handle)
    for handle, account in csv_accounts.items():
        if handle not in seen:
            merged.append(account)
    return merged


def _classified_accounts_by_handle(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    with path.open(newline="") as handle:
        return {
            _account_handle(row): _csv_account_snapshot(row)
            for row in csv.DictReader(handle)
            if _account_handle(row)
        }


def _csv_account_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "handle": row.get("userName") or row.get("handle"),
        "rank": row.get("rank"),
        "weather_pnl_usd": row.get("weather_pnl_usd"),
        "weather_volume_usd": row.get("weather_volume_usd"),
        "pnl_over_volume_pct": row.get("pnl_over_volume_pct"),
        "classification": row.get("classification"),
        "active_weather_positions": row.get("active_weather_positions"),
        "recent_weather_activity": row.get("recent_weather_activity"),
        "recent_nonweather_activity": row.get("recent_nonweather_activity"),
        "recommended_use": row.get("recommended_use"),
        "profile_url": row.get("profile_url"),
        "sample_weather_titles": _split_sample_titles(row.get("sample_weather_titles")),
    }


def _account_handle(account: dict[str, Any]) -> str:
    return str(account.get("handle") or account.get("userName") or "")


def _split_sample_titles(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item]
    if not value:
        return []
    return [part.strip() for part in str(value).split(" | ") if part.strip()]


def _is_missing_account_value(value: Any) -> bool:
    return value is None or value == "" or value == "unknown" or value == []


def _classified_counts(accounts: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(str(account.get("classification") or "unknown") for account in accounts)
    return dict(sorted(counts.items()))


def _priority_accounts(accounts: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    weather_heavy = [account for account in accounts if _is_weather_heavy(account)]
    ranked = sorted(
        weather_heavy,
        key=lambda account: (
            _to_float(account.get("active_weather_positions")) + _to_float(account.get("recent_weather_activity")),
            _to_float(account.get("weather_pnl_usd")),
        ),
        reverse=True,
    )[: max(int(limit), 0)]
    return [_priority_account(account) for account in ranked]


def _priority_account(account: dict[str, Any]) -> dict[str, Any]:
    return {
        "handle": account.get("handle"),
        "rank": _to_int(account.get("rank")),
        "weather_pnl_usd": round(_to_float(account.get("weather_pnl_usd")), 2),
        "weather_volume_usd": round(_to_float(account.get("weather_volume_usd")), 2),
        "pnl_over_volume_pct": round(_to_float(account.get("pnl_over_volume_pct")), 3),
        "classification": account.get("classification"),
        "active_weather_positions": _to_int(account.get("active_weather_positions")),
        "recent_weather_activity": _to_int(account.get("recent_weather_activity")),
        "recent_nonweather_activity": _to_int(account.get("recent_nonweather_activity")),
        "recommended_use": account.get("recommended_use"),
        "profile_url": account.get("profile_url"),
        "sample_weather_titles": list(account.get("sample_weather_titles") or [])[:4],
    }


def _watchlist_row(row: dict[str, Any], *, handle_lookup: dict[str, dict[str, Any]]) -> dict[str, Any]:
    matched = [str(handle) for handle in row.get("matched_traders") or [] if handle]
    matched_weather_heavy = [handle for handle in matched if _is_weather_heavy(handle_lookup.get(handle, {}))]
    matched_signal_only = [handle for handle in matched if handle in handle_lookup and handle not in matched_weather_heavy]
    matched_accounts = [_matched_account_snapshot(handle_lookup[handle]) for handle in matched if handle in handle_lookup]
    enriched = {
        **row,
        "matched_weather_heavy_traders": matched_weather_heavy,
        "matched_signal_only_traders": matched_signal_only,
        "matched_profitable_weather_count": len(matched_accounts),
        "matched_profitable_weather_accounts": matched_accounts,
    }
    enriched["normal_size_gate"] = _normal_size_gate(enriched)
    enriched["operator_verdict"] = _operator_verdict(enriched)
    return enriched


def _matched_account_snapshot(account: dict[str, Any]) -> dict[str, Any]:
    return {
        "handle": account.get("handle"),
        "rank": _to_int(account.get("rank")),
        "classification": account.get("classification"),
        "weather_pnl_usd": round(_to_float(account.get("weather_pnl_usd")), 2),
        "weather_volume_usd": round(_to_float(account.get("weather_volume_usd")), 2),
        "pnl_over_volume_pct": round(_to_float(account.get("pnl_over_volume_pct")), 3),
        "active_weather_positions": _to_int(account.get("active_weather_positions")),
        "recent_weather_activity": _to_int(account.get("recent_weather_activity")),
        "recommended_use": account.get("recommended_use"),
        "profile_url": account.get("profile_url"),
    }


def _live_market_signal_cards(watchlist: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for row in watchlist:
        matched_accounts = [account for account in row.get("matched_profitable_weather_accounts") or [] if isinstance(account, dict)]
        if not matched_accounts:
            continue
        top_accounts = sorted(matched_accounts, key=lambda account: _to_float(account.get("weather_pnl_usd")), reverse=True)[:5]
        card = {
            "market_id": row.get("market_id"),
            "city": row.get("city"),
            "date": row.get("date"),
            "action": row.get("action"),
            "blocker": row.get("blocker") or row.get("execution_blocker"),
            "matched_profitable_weather_count": len(matched_accounts),
            "weather_heavy_count": len(row.get("matched_weather_heavy_traders") or []),
            "signal_only_count": len(row.get("matched_signal_only_traders") or []),
            "top_matched_accounts": [
                {
                    "handle": account.get("handle"),
                    "weather_pnl_usd": round(_to_float(account.get("weather_pnl_usd")), 2),
                    "pnl_over_volume_pct": round(_to_float(account.get("pnl_over_volume_pct")), 3),
                }
                for account in top_accounts
            ],
            "operator_verdict": row.get("operator_verdict"),
            "next": list(row.get("next") or row.get("next_actions") or []),
            "source_latest_url": row.get("source_latest_url"),
        }
        if isinstance(row.get("edge_sizing"), dict):
            card["edge_sizing"] = row.get("edge_sizing")
        if isinstance(row.get("entry_policy"), dict):
            card["entry_policy"] = row.get("entry_policy")
        if isinstance(row.get("entry_decision"), dict):
            card["entry_decision"] = row.get("entry_decision")
        if isinstance(row.get("operator_entry_summary"), dict):
            card["operator_entry_summary"] = row.get("operator_entry_summary")
        if row.get("source_history_url") is not None:
            card["source_history_url"] = row.get("source_history_url")
        if row.get("polling_focus") is not None:
            card["polling_focus"] = row.get("polling_focus")
        if row.get("latency_tier") is not None:
            card["latency_tier"] = row.get("latency_tier")
        if row.get("latency_priority") is not None:
            card["latency_priority"] = row.get("latency_priority")
        if row.get("resolution_status") is not None:
            card["resolution_status"] = row.get("resolution_status")
        cards.append(card)
    return cards


def _live_matched_accounts(watchlist: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_handle: dict[str, dict[str, Any]] = {}
    for row in watchlist:
        market_id = str(row.get("market_id") or "")
        city = str(row.get("city") or "")
        for account in row.get("matched_profitable_weather_accounts") or []:
            if not isinstance(account, dict):
                continue
            handle = str(account.get("handle") or "")
            if not handle:
                continue
            entry = by_handle.setdefault(handle, {**account, "matched_market_ids": [], "matched_cities": []})
            if market_id and market_id not in entry["matched_market_ids"]:
                entry["matched_market_ids"].append(market_id)
            if city and city not in entry["matched_cities"]:
                entry["matched_cities"].append(city)
    ranked = sorted(by_handle.values(), key=lambda account: _to_float(account.get("weather_pnl_usd")), reverse=True)
    return [{**account, "matched_market_count": len(account.get("matched_market_ids") or [])} for account in ranked]


def _live_matched_accounts_summary(
    accounts: list[dict[str, Any]],
    *,
    enriched_watchlist: list[dict[str, Any]],
) -> dict[str, Any]:
    matched_market_ids: list[str] = []
    matched_cities: list[str] = []
    row_level_match_count = 0
    for row in enriched_watchlist:
        row_level_match_count += _to_int(row.get("matched_profitable_weather_count"))
        market_id = str(row.get("market_id") or "")
        city = str(row.get("city") or "")
        if market_id and any(account.get("handle") for account in row.get("matched_profitable_weather_accounts") or []):
            matched_market_ids.append(market_id)
        if city and any(account.get("handle") for account in row.get("matched_profitable_weather_accounts") or []):
            matched_cities.append(city)
    return {
        "unique_account_count": len(accounts),
        "row_level_match_count": row_level_match_count,
        "weather_heavy_unique_count": len([account for account in accounts if _is_weather_heavy(account)]),
        "signal_only_unique_count": len([account for account in accounts if not _is_weather_heavy(account)]),
        "top_account_handles_by_pnl": [str(account.get("handle")) for account in accounts[:10] if account.get("handle")],
        "matched_market_ids": _unique(matched_market_ids),
        "matched_cities": _unique(matched_cities),
        "operator_recommendation": _summary_operator_recommendation(
            accounts,
            enriched_watchlist=enriched_watchlist,
        ),
    }


def _summary_operator_recommendation(
    accounts: list[dict[str, Any]],
    *,
    enriched_watchlist: list[dict[str, Any]],
) -> dict[str, Any]:
    matched_rows = [row for row in enriched_watchlist if _to_int(row.get("matched_profitable_weather_count")) > 0]
    tradeable_matched_rows = [row for row in matched_rows if row.get("decision_status") in {"trade", "trade_small"}]
    blockers = {str(row.get("blocker") or row.get("execution_blocker") or "") for row in matched_rows}
    if accounts and "extreme_price" in blockers:
        return {
            "status": "paper_micro_only",
            "confidence": "profitable_weather_signal_with_execution_caution",
            "reason": "unique_profitable_weather_accounts_match_live_markets_but_extreme_price_blocks_normal_sizing",
            "next_actions": [
                "poll_direct_resolution_source",
                "paper_micro_order_with_strict_limit_and_fill_tracking",
                "do_not_use_normal_size_until_extreme_price_clears",
            ],
        }
    if accounts and not tradeable_matched_rows:
        return {
            "status": "watch_only",
            "confidence": "profitable_weather_signal_but_no_executable_market",
            "reason": "profitable_weather_accounts_match_live_markets_but_all_rows_are_execution_blocked",
            "next_actions": ["wait_for_executable_depth", "keep_polling_direct_resolution_sources"],
        }
    if accounts:
        return {
            "status": "watch_or_paper",
            "confidence": "profitable_weather_signal",
            "reason": "unique_profitable_weather_accounts_match_live_markets",
            "next_actions": ["validate_execution_depth", "paper_trade_until_fill_quality_confirmed"],
        }
    return {
        "status": "watch_only",
        "confidence": "no_profitable_account_signal",
        "reason": "no_unique_profitable_weather_accounts_match_live_markets",
        "next_actions": ["wait_for_profitable_weather_account_match"],
    }


def _operator_verdict(row: dict[str, Any]) -> dict[str, str]:
    blocker = row.get("blocker") or row.get("execution_blocker")
    matched_count = _to_int(row.get("matched_profitable_weather_count"))
    normal_size_gate = row.get("normal_size_gate") if isinstance(row.get("normal_size_gate"), dict) else {}
    if blocker == "extreme_price" and matched_count > 0:
        return {
            "status": "paper_micro",
            "confidence": "high_signal_cautious_execution",
            "reason": "profitable_weather_accounts_match_but_extreme_price_requires_micro_paper",
            "recommended_size": "micro_paper_only",
        }
    if matched_count > 0 and normal_size_gate.get("recommended_action") == "paper_strict_limit_only":
        return {
            "status": "paper_micro",
            "confidence": "high_signal_cautious_execution",
            "reason": "profitable_weather_accounts_match_but_normal_size_gate_blocks_live_or_normal_sizing",
            "recommended_size": "paper_strict_limit_only",
        }
    if matched_count > 0:
        return {
            "status": "watch_or_paper",
            "confidence": "profitable_account_match",
            "reason": "profitable_weather_accounts_match_live_watchlist",
            "recommended_size": "paper_until_execution_validated",
        }
    return {
        "status": "watch_only",
        "confidence": "no_profitable_account_match",
        "reason": "live_watchlist_row_has_no_matched_profitable_weather_account",
        "recommended_size": "none",
    }


def _normal_size_gate(row: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    blocker = row.get("blocker") or row.get("execution_blocker")
    if blocker in {"extreme_price", "high_slippage_risk", "missing_tradeable_quote"}:
        reasons.append(str(blocker))
    resolution_status = row.get("resolution_status") if isinstance(row.get("resolution_status"), dict) else {}
    official_extract = resolution_status.get("official_daily_extract") if isinstance(resolution_status.get("official_daily_extract"), dict) else {}
    if official_extract.get("available") is False:
        reasons.append("official_resolution_unavailable")
    execution_snapshot = row.get("execution_snapshot") if isinstance(row.get("execution_snapshot"), dict) else {}
    ask_yes = _first_present(execution_snapshot, ["best_ask_yes", "ask_yes", "askY", "yes_ask"])
    bid_yes = _first_present(execution_snapshot, ["best_bid_yes", "bid_yes", "bidY", "yes_bid"])
    if _is_extreme_quote(ask_yes) or _is_extreme_quote(bid_yes):
        reasons.append("extreme_quote")
    depth = _first_present(execution_snapshot, ["yes_ask_depth_usd", "order_book_depth_usd", "depth_usd", "depth"])
    if depth is not None and _to_float(depth) < 50.0:
        reasons.append("insufficient_depth")
    unique_reasons = _unique(reasons)
    return {
        "normal_size_allowed": not unique_reasons,
        "live_ready": not unique_reasons,
        "paper_candidate": _to_int(row.get("matched_profitable_weather_count")) > 0,
        "reasons": unique_reasons,
        "recommended_action": "paper_strict_limit_only" if unique_reasons else "normal_size_possible_after_operator_review",
    }


def _first_present(payload: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        if key in payload and payload.get(key) is not None:
            return payload.get(key)
    return None


def _is_extreme_quote(value: Any) -> bool:
    if value is None:
        return False
    quote = _to_float(value)
    return quote <= 0.01 or quote >= 0.99


def _discord_operator_brief(cards: list[dict[str, Any]], *, live_match_summary: dict[str, Any]) -> str:
    recommendation = live_match_summary.get("operator_recommendation") or {}
    status = str(recommendation.get("status") or "watch_only")
    lines = [f"Météo Polymarket: {len(cards)} marché live avec comptes météo rentables. Reco globale: {status}."]
    for card in cards[:5]:
        market_id = str(card.get("market_id") or "n/a")
        city = str(card.get("city") or "n/a")
        matched_count = _to_int(card.get("matched_profitable_weather_count"))
        heavy_count = _to_int(card.get("weather_heavy_count"))
        blocker = str(card.get("blocker") or "none")
        verdict = card.get("operator_verdict") or {}
        verdict_status = str(verdict.get("status") or "watch_only")
        top = _brief_top_accounts(card.get("top_matched_accounts") or [])
        lines.append(
            f"- {market_id} — {city} — {matched_count} comptes ({heavy_count} heavy), "
            f"blocker={blocker}, verdict={verdict_status}, top={top}"
        )
    return "\n".join(lines)


def _brief_top_accounts(accounts: list[Any]) -> str:
    chunks: list[str] = []
    for account in accounts[:3]:
        if not isinstance(account, dict):
            continue
        handle = str(account.get("handle") or "n/a")
        chunks.append(f"{handle} ${_to_float(account.get('weather_pnl_usd')):,.2f}")
    return " / ".join(chunks) if chunks else "n/a"


def _compact_summary(payload: dict[str, Any], *, output_path: Path) -> dict[str, Any]:
    live_watchlist = [row for row in payload.get("live_watchlist", []) if isinstance(row, dict)]
    live_market_signal_cards = [row for row in payload.get("live_market_signal_cards", []) if isinstance(row, dict)]
    live_match_summary = payload.get("live_matched_profitable_weather_summary") or {}
    live_recommendation = live_match_summary.get("operator_recommendation") or {}
    return {
        "output_json": str(output_path),
        "classified_account_counts": payload.get("classified_account_counts", {}),
        "priority_account_count": len(payload.get("priority_weather_accounts") or []),
        "live_watchlist_count": len(live_watchlist),
        "live_matched_profitable_weather_count": sum(int(row.get("matched_profitable_weather_count") or 0) for row in live_watchlist),
        "live_unique_matched_profitable_weather_count": _to_int(live_match_summary.get("unique_account_count")),
        "live_weather_heavy_unique_count": _to_int(live_match_summary.get("weather_heavy_unique_count")),
        "live_signal_only_unique_count": _to_int(live_match_summary.get("signal_only_unique_count")),
        "live_top_account_handles_by_pnl": list(live_match_summary.get("top_account_handles_by_pnl") or []),
        "live_matched_market_ids": list(live_match_summary.get("matched_market_ids") or []),
        "live_operator_recommendation_status": live_recommendation.get("status"),
        "live_operator_recommendation_next_actions": list(live_recommendation.get("next_actions") or []),
        "live_market_signal_card_count": len(live_market_signal_cards),
        "live_market_signal_cards": live_market_signal_cards[:5],
        "discord_operator_brief": payload.get("discord_operator_brief"),
        "live_top_blockers": payload.get("live_operator_summary", {}).get("top_blockers", []),
        "live_top_actions": payload.get("live_operator_summary", {}).get("top_actions", []),
    }


def _unique(values: list[str]) -> list[str]:
    unique_values: list[str] = []
    for value in values:
        if value not in unique_values:
            unique_values.append(value)
    return unique_values


def _is_weather_heavy(account: dict[str, Any]) -> bool:
    classification = str(account.get("classification") or "")
    return "weather-heavy" in classification or "specialist" in classification


def _to_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _to_int(value: Any) -> int:
    return int(_to_float(value))
