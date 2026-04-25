from __future__ import annotations

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
    operator_payload = _load_json_object(operator_path)
    accounts = [account for account in reverse_payload.get("accounts", []) if isinstance(account, dict)]
    watchlist = [row for row in operator_payload.get("watchlist", []) if isinstance(row, dict)]

    priority_accounts = _priority_accounts(accounts, limit=priority_limit)
    handle_lookup = {str(account.get("handle") or ""): account for account in accounts}
    enriched_watchlist = [_watchlist_row(row, handle_lookup=handle_lookup) for row in watchlist]

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
    matched_count = len([handle for handle in matched if handle in handle_lookup])
    enriched = {
        **row,
        "matched_weather_heavy_traders": matched_weather_heavy,
        "matched_signal_only_traders": matched_signal_only,
        "matched_profitable_weather_count": matched_count,
    }
    enriched["operator_verdict"] = _operator_verdict(enriched)
    return enriched


def _operator_verdict(row: dict[str, Any]) -> dict[str, str]:
    blocker = row.get("blocker") or row.get("execution_blocker")
    matched_count = _to_int(row.get("matched_profitable_weather_count"))
    if blocker == "extreme_price" and matched_count > 0:
        return {
            "status": "paper_micro",
            "confidence": "high_signal_cautious_execution",
            "reason": "profitable_weather_accounts_match_but_extreme_price_requires_micro_paper",
            "recommended_size": "micro_paper_only",
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


def _compact_summary(payload: dict[str, Any], *, output_path: Path) -> dict[str, Any]:
    live_watchlist = [row for row in payload.get("live_watchlist", []) if isinstance(row, dict)]
    return {
        "output_json": str(output_path),
        "classified_account_counts": payload.get("classified_account_counts", {}),
        "priority_account_count": len(payload.get("priority_weather_accounts") or []),
        "live_watchlist_count": len(live_watchlist),
        "live_matched_profitable_weather_count": sum(int(row.get("matched_profitable_weather_count") or 0) for row in live_watchlist),
        "live_top_blockers": payload.get("live_operator_summary", {}).get("top_blockers", []),
        "live_top_actions": payload.get("live_operator_summary", {}).get("top_actions", []),
    }


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
