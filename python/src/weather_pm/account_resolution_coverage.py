from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

GUARDRAILS = {"paper_only": True, "live_order_allowed": False}


def match_trade_resolution(trade: dict[str, Any], resolutions_payload: dict[str, Any] | list[Any]) -> dict[str, Any]:
    """Match one historical trade to a resolution row using strongest available keys."""
    rows = _resolution_rows(resolutions_payload)
    if not isinstance(trade, dict):
        return _unresolved("invalid_trade")
    embedded = _embedded_trade_resolution(trade)
    if embedded is not None:
        for match_key, trade_values, resolution_fields, normalized in _priority_specs(trade):
            values = [value for value in trade_values if value]
            if not values:
                continue
            matches = _matches_for_values(rows, values, resolution_fields, normalized=normalized)
            if len(matches) == 1:
                return _resolved_result(trade, {**matches[0], **embedded}, "embedded_trade_resolution")
        return _resolved_result(trade, embedded, "embedded_trade_resolution")
    if not rows:
        return _unresolved("no_resolutions_available")

    for match_key, trade_values, resolution_fields, normalized in _priority_specs(trade):
        values = [value for value in trade_values if value]
        if not values:
            continue
        matches = _matches_for_values(rows, values, resolution_fields, normalized=normalized)
        if len(matches) == 1:
            return _resolved_result(trade, matches[0], match_key)
        if len(matches) > 1:
            return _unresolved(f"ambiguous_{match_key}_match")

    event_slug = _normalized_slug(_first_value(trade, ("event_slug", "eventSlug", "event", "event_id")))
    side = _normalize_side(_first_value(trade, ("outcome", "outcome_side", "side_outcome", "position")))
    if event_slug and side:
        matches = []
        for row in rows:
            row_event = _normalized_slug(_first_value(row, ("event_slug", "eventSlug", "event", "event_id")))
            row_side = _normalize_side(_first_value(row, ("outcome_side", "side_outcome", "outcome", "token_outcome", "asset_outcome")))
            if row_event == event_slug and row_side == side:
                matches.append(row)
        if len(matches) == 1:
            return _resolved_result(trade, matches[0], "event_slug_outcome_side")
        if len(matches) > 1:
            return _unresolved("ambiguous_event_slug_outcome_side_match")

    return _unresolved("no_resolution_match")


def build_resolution_coverage_report(trades_payload: dict[str, Any] | list[Any], resolutions_payload: dict[str, Any] | list[Any]) -> dict[str, Any]:
    trades = _trade_rows(trades_payload)
    enriched: list[dict[str, Any]] = []
    match_key_counts: Counter[str] = Counter()
    unresolved_reason_counts: Counter[str] = Counter()
    resolved_count = 0
    for trade in trades:
        result = match_trade_resolution(trade, resolutions_payload)
        row = dict(trade)
        row["resolution_match"] = result
        row["paper_only"] = True
        row["live_order_allowed"] = False
        enriched.append(row)
        if result["resolved"]:
            resolved_count += 1
            match_key_counts[str(result.get("match_key") or "unknown")] += 1
        else:
            unresolved_reason_counts[str(result.get("unresolved_reason") or "unknown")] += 1
    total = len(enriched)
    unresolved = total - resolved_count
    summary = {
        "trades": total,
        "resolved": resolved_count,
        "unresolved": unresolved,
        "resolved_pct": round((resolved_count / total) * 100, 6) if total else 0.0,
        "match_key_counts": dict(sorted(match_key_counts.items())),
        "unresolved_reason_counts": dict(sorted(unresolved_reason_counts.items())),
        "paper_only": True,
        "live_order_allowed": False,
    }
    return {
        "source": "account_resolution_coverage",
        "paper_only": True,
        "live_order_allowed": False,
        "summary": summary,
        "trades": enriched,
    }


def write_resolution_coverage_report(trades_json: str | Path, resolutions_json: str | Path, output_json: str | Path) -> dict[str, Any]:
    trades_payload = json.loads(Path(trades_json).read_text(encoding="utf-8"))
    resolutions_payload = json.loads(Path(resolutions_json).read_text(encoding="utf-8"))
    report = build_resolution_coverage_report(trades_payload, resolutions_payload)
    output_path = Path(output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report.setdefault("artifacts", {})["output_json"] = str(output_path)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = report["summary"]
    return {
        "paper_only": True,
        "live_order_allowed": False,
        "trades": summary["trades"],
        "resolved": summary["resolved"],
        "unresolved": summary["unresolved"],
        "resolved_pct": summary["resolved_pct"],
        "output_json": str(output_path),
    }


def _priority_specs(trade: dict[str, Any]) -> list[tuple[str, list[str], tuple[str, ...], bool]]:
    return [
        ("token_id", _values(trade, ("token_id", "tokenId", "asset", "asset_id", "clobTokenId", "clob_token_id")), ("token_id", "tokenId", "asset", "asset_id", "clobTokenId", "clob_token_id", "token_ids", "tokenIds", "assets", "clobTokenIds"), False),
        ("condition_id", _values(trade, ("condition_id", "conditionId")), ("condition_id", "conditionId", "condition_ids", "conditionIds"), False),
        ("market_id", _values(trade, ("market_id", "marketId", "id")), ("market_id", "marketId", "id", "primary_key"), False),
        ("slug", [_normalized_slug(value) for value in _values(trade, ("slug", "market_slug"))], ("slug", "market_slug", "matched_key", "aliases"), True),
        ("question_title", [_normalized_text(value) for value in _values(trade, ("question", "title", "market", "marketTitle"))], ("question", "title", "market", "marketTitle", "aliases"), True),
    ]


def _matches_for_values(rows: list[dict[str, Any]], values: list[str], fields: tuple[str, ...], *, normalized: bool) -> list[dict[str, Any]]:
    wanted = {_normalize_lookup(value, normalized=normalized) for value in values if value}
    wanted.discard("")
    matches: list[dict[str, Any]] = []
    seen: set[int] = set()
    for row in rows:
        candidates: set[str] = set()
        for field in fields:
            for value in _row_values(row, field):
                candidates.add(_normalize_lookup(value, normalized=normalized))
        if wanted.intersection(candidates) and id(row) not in seen:
            matches.append(row)
            seen.add(id(row))
    return matches


def _resolved_result(trade: dict[str, Any], resolution: dict[str, Any], match_key: str) -> dict[str, Any]:
    winning_side = _winning_side(resolution)
    if winning_side not in {"Yes", "No"}:
        result = _unresolved("missing_winning_side")
        result["match_key"] = match_key
        return result
    effective = _effective_position(trade)
    outcome = "unresolved"
    pnl = 0.0
    if effective in {"Yes", "No"}:
        if effective == winning_side:
            outcome = "win"
            pnl = _win_pnl(trade)
        else:
            outcome = "loss"
            pnl = _loss_pnl(trade)
    else:
        result = _unresolved("missing_trade_outcome_side")
        result["match_key"] = match_key
        result["winning_side"] = winning_side
        return result
    return {
        "resolved": True,
        "outcome": outcome,
        "winning_side": winning_side,
        "pnl": round(pnl, 6),
        "match_key": match_key,
        "unresolved_reason": None,
        "resolution": _compact_resolution(resolution),
        **GUARDRAILS,
    }


def _unresolved(reason: str) -> dict[str, Any]:
    return {
        "resolved": False,
        "outcome": "unresolved",
        "winning_side": None,
        "pnl": 0.0,
        "match_key": None,
        "unresolved_reason": reason,
        **GUARDRAILS,
    }


def _embedded_trade_resolution(trade: dict[str, Any]) -> dict[str, Any] | None:
    resolution = trade.get("resolution")
    if not isinstance(resolution, dict):
        return None
    if resolution.get("available") is False:
        return None
    if not _winning_side(resolution):
        return None
    return dict(resolution)


def _resolution_rows(payload: dict[str, Any] | list[Any]) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        return []
    rows = payload.get("resolutions")
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
    if isinstance(rows, dict):
        out = []
        for key, value in rows.items():
            if isinstance(value, dict):
                row = dict(value)
                row.setdefault("matched_key", key)
                out.append(row)
        return out
    for key in ("markets", "data", "results"):
        rows = payload.get(key)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    if any(key in payload for key in ("winning_side", "resolved_outcome", "condition_id", "conditionId", "market_id", "slug")):
        return [payload]
    sparse: list[dict[str, Any]] = []
    for key, value in payload.items():
        if isinstance(value, dict):
            row = dict(value)
            row.setdefault("matched_key", key)
            if str(key).strip().isdigit():
                row.setdefault("primary_key", str(key).strip())
                row.setdefault("market_id", str(key).strip())
            sparse.append(row)
    return sparse


def _trade_rows(payload: dict[str, Any] | list[Any]) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("trades", "examples", "rows", "data"):
        rows = payload.get(key)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return [payload]


def _values(row: dict[str, Any], keys: tuple[str, ...]) -> list[str]:
    values: list[str] = []
    for key in keys:
        for value in _row_values(row, key):
            text = str(value or "").strip()
            if text and text not in values:
                values.append(text)
    return values


def _row_values(row: dict[str, Any], key: str) -> list[Any]:
    value = row.get(key)
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                return [value]
            if isinstance(parsed, list):
                return parsed
    return [value]


def _first_value(row: dict[str, Any], keys: tuple[str, ...]) -> Any:
    vals = _values(row, keys)
    return vals[0] if vals else None


def _normalize_lookup(value: Any, *, normalized: bool) -> str:
    if not normalized:
        return str(value or "").strip().lower()
    return _normalized_text(value)


def _normalized_slug(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def _normalized_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _normalize_side(value: Any) -> str:
    side = str(value or "").strip().lower()
    if side in {"yes", "y", "true"}:
        return "Yes"
    if side in {"no", "n", "false"}:
        return "No"
    return ""


def _winning_side(row: dict[str, Any]) -> str:
    for key in ("winning_side", "resolved_outcome", "winner", "winningOutcome", "winning_outcome", "outcome"):
        side = _normalize_side(row.get(key))
        if side:
            return side
    return ""


def _effective_position(trade: dict[str, Any]) -> str:
    outcome = _normalize_side(_first_value(trade, ("outcome", "outcome_side", "position")))
    side = str(trade.get("side") or "").strip().upper()
    if side == "SELL":
        if outcome == "Yes":
            return "No"
        if outcome == "No":
            return "Yes"
    return outcome


def _win_pnl(trade: dict[str, Any]) -> float:
    notional = _to_float(trade.get("notional_usd") or trade.get("notional_usdc") or trade.get("account_trade_notional_usd"))
    price = _to_float(trade.get("price") or trade.get("account_trade_price"))
    if str(trade.get("side") or "").strip().upper() == "SELL":
        return notional
    if price > 0:
        return notional / price - notional
    size = _to_float(trade.get("size") or trade.get("account_trade_size"))
    return size - notional if size else 0.0


def _loss_pnl(trade: dict[str, Any]) -> float:
    notional = _to_float(trade.get("notional_usd") or trade.get("notional_usdc") or trade.get("account_trade_notional_usd"))
    if str(trade.get("side") or "").strip().upper() == "SELL":
        size = _to_float(trade.get("size") or trade.get("account_trade_size"))
        return notional - size if size else -notional
    return -notional


def _to_float(value: Any) -> float:
    try:
        if value is None or value == "":
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _compact_resolution(row: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "market_id",
        "marketId",
        "condition_id",
        "conditionId",
        "token_id",
        "tokenId",
        "slug",
        "event_slug",
        "primary_key",
        "matched_key",
        "winning_side",
        "resolved_outcome",
        "source",
        "resolution_source",
        "status",
        "station_id",
        "station_name",
        "observation_value",
        "observed_value",
        "observation_timestamp",
        "observed_at",
        "resolution_value",
        "value",
        "resolution_timestamp",
        "resolved_at",
        "official_source_available",
    )
    return {key: row[key] for key in keys if key in row}
