from __future__ import annotations

from collections import Counter
from typing import Any

_READINESS_ACTIONS = ("WATCH", "PAPER_MICRO", "PAPER_STRICT", "BLOCKED")


def attach_live_readiness(report: dict[str, Any]) -> dict[str, Any]:
    rows = [row for row in report.get("shortlist", []) if isinstance(row, dict)]
    for row in rows:
        row["live_readiness"] = build_live_readiness(row)
    return report


def live_readiness_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    readiness_items = [row.get("live_readiness") for row in rows if isinstance(row.get("live_readiness"), dict)]
    counts = Counter(str(item.get("readiness_action") or "WATCH") for item in readiness_items)
    return {
        "live_readiness_counts": {action: counts[action] for action in _READINESS_ACTIONS if counts[action]},
        "normal_size_allowed_rows": sum(1 for item in readiness_items if item.get("normal_size_allowed") is True),
        "live_order_allowed": False,
    }


def build_live_readiness(row: dict[str, Any]) -> dict[str, Any]:
    blockers = _readiness_blockers(row)
    action = _readiness_action(row, blockers)
    return {
        "readiness_action": action,
        "paper_only": True,
        "live_order_allowed": False,
        "normal_size_allowed": False,
        "blockers": blockers,
    }


def _readiness_action(row: dict[str, Any], blockers: list[str]) -> str:
    hard_blockers = {"missing_quote", "missing_execution_snapshot", "wide_spread"}
    if any(blocker in hard_blockers for blocker in blockers):
        return "WATCH"
    if "extreme_price" in blockers:
        return "PAPER_MICRO"
    if str(row.get("decision_status") or "") in {"trade", "trade_small"} and not blockers:
        return "PAPER_STRICT"
    return "WATCH"


def _readiness_blockers(row: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    _append_if(blockers, _official_pending(row), "official_pending")
    execution_blocker = str(row.get("execution_blocker") or "").strip()
    if execution_blocker:
        _append_unique(blockers, execution_blocker)

    snapshot = row.get("execution_snapshot") if isinstance(row.get("execution_snapshot"), dict) else None
    if snapshot is None:
        _append_unique(blockers, "missing_execution_snapshot")
        return blockers

    spread = _snapshot_spread(snapshot)
    depth = _snapshot_depth(snapshot)
    if _snapshot_missing_quote(snapshot):
        _append_unique(blockers, "missing_quote")
    if spread is None:
        _append_unique(blockers, "missing_spread")
    elif spread > 0.08:
        _append_unique(blockers, "wide_spread")
    if depth is None or depth <= 0:
        _append_unique(blockers, "missing_depth")
    if _extreme_price(row, snapshot):
        _append_unique(blockers, "extreme_price")
    return blockers


def _official_pending(row: dict[str, Any]) -> bool:
    status = row.get("resolution_status") if isinstance(row.get("resolution_status"), dict) else {}
    confirmed = row.get("confirmed_outcome", status.get("confirmed_outcome"))
    if isinstance(confirmed, dict):
        confirmed = confirmed.get("status")
    official = row.get("official_daily_extract", status.get("official_daily_extract"))
    official_available = official.get("available") if isinstance(official, dict) else None
    return confirmed == "pending" or official_available is False


def _snapshot_missing_quote(snapshot: dict[str, Any]) -> bool:
    return all(_optional_number(snapshot.get(key)) is None for key in ("best_bid_yes", "best_ask_yes", "best_bid_no", "best_ask_no"))


def _snapshot_spread(snapshot: dict[str, Any]) -> float | None:
    values = [_optional_number(snapshot.get("spread_yes")), _optional_number(snapshot.get("spread_no"))]
    present = [value for value in values if value is not None]
    return min(present) if present else None


def _snapshot_depth(snapshot: dict[str, Any]) -> float | None:
    values = [
        _optional_number(snapshot.get(key))
        for key in ("yes_ask_depth_usd", "no_ask_depth_usd", "yes_bid_depth_usd", "no_bid_depth_usd")
    ]
    present = [value for value in values if value is not None]
    return max(present) if present else None


def _extreme_price(row: dict[str, Any], snapshot: dict[str, Any]) -> bool:
    edge_sizing = row.get("edge_sizing") if isinstance(row.get("edge_sizing"), dict) else {}
    candidates = [
        _optional_number(row.get("market_price")),
        _optional_number(row.get("yes_price")),
        _optional_number(edge_sizing.get("market_price")),
        _optional_number(snapshot.get("best_ask_yes")),
        _optional_number(snapshot.get("best_bid_yes")),
    ]
    return any(value is not None and (value <= 0.05 or value >= 0.95) for value in candidates)


def _append_if(values: list[str], condition: bool, value: str) -> None:
    if condition:
        _append_unique(values, value)


def _append_unique(values: list[str], value: str) -> None:
    if value and value not in values:
        values.append(value)


def _optional_number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
