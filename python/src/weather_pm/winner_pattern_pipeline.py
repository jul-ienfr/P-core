from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from weather_pm.account_resolution_coverage import build_resolution_coverage_report
from weather_pm.decision_dataset import build_account_decision_dataset
from weather_pm.orderbook_context import build_orderbook_context_report
from weather_pm.paper_candidate_gate import build_winner_pattern_paper_candidates
from weather_pm.weather_decision_context import enrich_decision_weather_context
from weather_pm.winner_pattern_engine import build_winner_pattern_engine
from weather_pm.winner_pattern_report import build_winner_pattern_operator_report


WATCHLIST_CAPTURE_SCOPE = [
    "current_orderbook_compact_snapshots_for_matched_surfaces",
    "full_book_only_on_account_trade_large_movement_or_candidate_trigger",
    "forecast_snapshots",
    "market_surface_snapshots",
    "observed_account_trades",
]


def build_winner_pattern_watchlist_capture_payload(
    *,
    source: str = "winner_pattern_pipeline_audit",
    captured_at: str | None = None,
    retention_policy: str = "bounded_live_observer_30_days_jsonl_optional_archive",
    compressed: bool = False,
) -> dict[str, Any]:
    """Describe the bounded live-observer watchlist mode without network I/O.

    This is a paper-only Phase 11 audit/helper payload.  It intentionally does
    not fetch markets, books, forecasts, or account trades; live collection stays
    behind the existing observer controls and storage guardrails.
    """

    return {
        "mode": "winner_pattern_watchlist",
        "capture_scope": list(WATCHLIST_CAPTURE_SCOPE),
        "trigger_policy": {
            "compact_orderbook": "matched_surfaces_only",
            "full_book": "account_trade_large_movement_or_candidate_trigger_only",
            "network_default": "disabled_in_fixture_pipeline",
        },
        "retention_policy": retention_policy,
        "compressed": bool(compressed),
        "source": source,
        "captured_at": captured_at or datetime.now(UTC).isoformat(),
        "paper_only": True,
        "live_order_allowed": False,
    }


def run_winner_pattern_pipeline(
    *,
    trades_json: str | Path,
    resolutions_json: str | Path,
    orderbook_snapshots_json: str | Path,
    market_snapshots_json: str | Path,
    forecast_snapshots_json: str | Path,
    output_dir: str | Path,
    allow_network: bool = False,
) -> dict[str, Any]:
    if allow_network:
        raise ValueError("allow-network is not yet supported for winner-pattern-pipeline")

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    trades_payload = _load_object(trades_json, "trades JSON")
    resolutions_payload = _load_object(resolutions_json, "resolutions JSON")
    orderbook_payload = _load_object(orderbook_snapshots_json, "orderbook snapshots JSON")
    markets_payload = _load_object(market_snapshots_json, "market snapshots JSON")
    forecasts_payload = _load_object(forecast_snapshots_json, "forecast snapshots JSON")

    resolution_coverage = build_resolution_coverage_report(trades_payload, resolutions_payload)
    resolution_coverage["watchlist_capture_mode"] = build_winner_pattern_watchlist_capture_payload(source="winner_pattern_pipeline")
    resolution_path = _write_json(out_dir / "resolution_coverage.json", resolution_coverage)

    orderbook_context = build_orderbook_context_report(resolution_coverage, orderbook_payload)
    orderbook_path = _write_json(out_dir / "orderbook_context.json", orderbook_context)

    decision_dataset = build_account_decision_dataset(orderbook_context, markets_payload)
    _merge_orderbook_context(decision_dataset, orderbook_context)
    _merge_resolution_matches(decision_dataset, resolution_coverage)
    historical_weather_context = enrich_decision_weather_context(decision_dataset, forecasts_payload)
    _merge_weather_context(decision_dataset, historical_weather_context)
    decision_path = _write_json(out_dir / "decision_dataset.json", decision_dataset)
    historical_weather_path = _write_json(out_dir / "historical_decision_weather_context.json", historical_weather_context)

    # Current market contexts are needed by the paper-candidate gate; enrich the
    # same fixture market snapshots with forecast-at-time evidence in addition to
    # the historical decision dataset artifact.
    weather_context = enrich_decision_weather_context({"examples": _market_rows(markets_payload)}, forecasts_payload)
    weather_path = _write_json(out_dir / "weather_context.json", weather_context)

    winner_patterns = build_winner_pattern_engine(decision_dataset, resolution_coverage, min_resolved_trades=5)
    patterns_path = _write_json(out_dir / "winner_patterns.json", winner_patterns)

    current_orderbooks = _current_orderbooks_from_snapshots(orderbook_payload)
    paper_candidates = build_winner_pattern_paper_candidates(winner_patterns, markets_payload, current_orderbooks, weather_context)
    candidates_path = _write_json(out_dir / "paper_candidates.json", paper_candidates)

    report_payload = build_winner_pattern_operator_report(
        winner_patterns,
        paper_candidates,
        resolution_coverage=resolution_coverage,
        orderbook_context=orderbook_context,
    )
    report_path = out_dir / "operator_report.md"
    report_path.write_text(report_payload["markdown"], encoding="utf-8")

    artifact_paths = {
        "resolution_coverage": str(resolution_path),
        "orderbook_context": str(orderbook_path),
        "decision_dataset": str(decision_path),
        "weather_context": str(weather_path),
        "historical_decision_weather_context": str(historical_weather_path),
        "winner_patterns": str(patterns_path),
        "paper_candidates": str(candidates_path),
        "operator_report": str(report_path),
    }
    artifact_counts = {
        "resolution_coverage": int(resolution_coverage.get("summary", {}).get("resolved", 0)),
        "orderbook_context": int(orderbook_context.get("summary", {}).get("with_orderbook_context", 0)),
        "decision_dataset": len(decision_dataset.get("examples", [])) if isinstance(decision_dataset.get("examples"), list) else 0,
        "weather_context": max(
            int(weather_context.get("summary", {}).get("with_weather_context", 0)),
            int(historical_weather_context.get("summary", {}).get("with_weather_context", 0)),
        ),
        "winner_patterns": len(winner_patterns.get("robust_patterns", [])) if isinstance(winner_patterns.get("robust_patterns"), list) else 0,
        "research_only_patterns": len(winner_patterns.get("research_only_patterns", [])) if isinstance(winner_patterns.get("research_only_patterns"), list) else 0,
        "promotion_blocked_patterns": int(winner_patterns.get("summary", {}).get("promotion_blocked_patterns", 0)) if isinstance(winner_patterns.get("summary"), dict) else 0,
        "paper_candidates": len(paper_candidates.get("paper_candidates", [])) if isinstance(paper_candidates.get("paper_candidates"), list) else 0,
    }
    return {
        "paper_only": True,
        "live_order_allowed": False,
        "allow_network": False,
        "output_dir": str(out_dir),
        "artifact_paths": artifact_paths,
        "artifact_counts": artifact_counts,
    }


def _merge_weather_context(decision_dataset: dict[str, Any], weather_context: dict[str, Any]) -> None:
    examples = decision_dataset.get("examples") if isinstance(decision_dataset.get("examples"), list) else []
    enriched = weather_context.get("examples") if isinstance(weather_context.get("examples"), list) else []
    for target, source in zip(examples, enriched, strict=False):
        if not isinstance(target, dict) or not isinstance(source, dict):
            continue
        for key in (
            "decision_context_leakage_allowed",
            "resolution_source",
            "station_id",
            "station_name",
            "forecast_timestamp",
            "forecast_value",
            "forecast_value_at_decision",
            "forecast_age_minutes",
            "forecast_source",
            "distance_to_threshold",
            "distance_to_bin_center",
            "official_source_available",
            "weather_context_available",
            "missing_reason",
            "observation_value",
            "observation_timestamp",
            "resolution_value",
        ):
            if key in source:
                target[key] = source[key]


def _merge_orderbook_context(decision_dataset: dict[str, Any], orderbook_context: dict[str, Any]) -> None:
    book_by_key: dict[str, dict[str, Any]] = {}
    for trade in orderbook_context.get("trades", []) if isinstance(orderbook_context.get("trades"), list) else []:
        if not isinstance(trade, dict):
            continue
        for key in _trade_bridge_keys(trade):
            book_by_key.setdefault(key, trade)
    for example in decision_dataset.get("examples", []) if isinstance(decision_dataset.get("examples"), list) else []:
        if not isinstance(example, dict):
            continue
        book = _lookup_bridge_row(book_by_key, example)
        if book:
            _copy_bridge_fields(
                example,
                book,
                (
                    "market_id",
                    "condition_id",
                    "token_id",
                    "orderbook_context_available",
                    "capturability",
                    "capturable_score",
                    "best_bid",
                    "best_ask",
                    "spread",
                    "depth_near_touch",
                    "snapshot_timestamp",
                    "staleness_seconds",
                ),
            )


def _merge_resolution_matches(decision_dataset: dict[str, Any], resolution_coverage: dict[str, Any]) -> None:
    resolved_by_key: dict[str, list[dict[str, Any]]] = {}
    for trade in resolution_coverage.get("trades", []) if isinstance(resolution_coverage.get("trades"), list) else []:
        if not isinstance(trade, dict):
            continue
        match = trade.get("resolution_match") if isinstance(trade.get("resolution_match"), dict) else {}
        if match.get("resolved") is True:
            bridge_row = {"trade": trade, "match": match}
            for key in _trade_bridge_keys(trade):
                resolved_by_key.setdefault(key, []).append(bridge_row)
    for example in decision_dataset.get("examples", []) if isinstance(decision_dataset.get("examples"), list) else []:
        if not isinstance(example, dict):
            continue
        bridge_row = _lookup_resolution_bridge_row(resolved_by_key, example)
        match = bridge_row.get("match") if bridge_row else None
        if match:
            resolution = match.get("resolution") if isinstance(match.get("resolution"), dict) else {}
            for field in ("primary_key", "matched_key"):
                if resolution.get(field) and not example.get("market_id"):
                    example["market_id"] = resolution.get(field)
                    break
            operator_pnl = _operator_pnl(bridge_row.get("trade", {}) if bridge_row else {})
            example["pnl"] = operator_pnl if operator_pnl is not None else match.get("pnl")
            example["out_of_sample_pnl"] = example["pnl"]
            example["outcome"] = match.get("outcome")
            example["winning_side"] = match.get("winning_side")
            if resolution.get("source"):
                example["resolution_source"] = resolution.get("source")
            if match.get("resolved") is True:
                example["resolution_verified"] = True


def _lookup_bridge_row(rows_by_key: dict[str, dict[str, Any]], example: dict[str, Any]) -> dict[str, Any] | None:
    for key in _trade_bridge_keys(example):
        if key in rows_by_key:
            return rows_by_key[key]
    return None


def _lookup_resolution_bridge_row(rows_by_key: dict[str, list[dict[str, Any]]], example: dict[str, Any]) -> dict[str, Any] | None:
    matches: list[dict[str, Any]] = []
    seen: set[int] = set()
    for key in _trade_bridge_keys(example):
        for row in rows_by_key.get(key, []):
            row_id = id(row)
            if row_id not in seen:
                seen.add(row_id)
                matches.append(row)
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]
    scored = sorted((( _resolution_bridge_score(row.get("trade", {}), example), idx, row) for idx, row in enumerate(matches)), key=lambda item: (item[0], -item[1]), reverse=True)
    return scored[0][2] if scored and scored[0][0] > 0 else matches[0]


def _resolution_bridge_score(trade: dict[str, Any], example: dict[str, Any]) -> int:
    score = 0
    comparable = (
        ("wallet", "wallet"),
        ("account", "account"),
        ("handle", "account"),
        ("timestamp", "timestamp"),
        ("created_at", "timestamp"),
        ("createdAt", "timestamp"),
        ("trade_id", "trade_id"),
        ("slug", "slug"),
        ("outcome", "side"),
        ("side", "side"),
    )
    for left, right in comparable:
        if _norm_bridge_value(trade.get(left)) and _norm_bridge_value(trade.get(left)) == _norm_bridge_value(example.get(right)):
            score += 1
    return score


def _norm_bridge_value(value: Any) -> str:
    return str(value or "").strip().lower()


def _operator_pnl(trade: dict[str, Any]) -> float | None:
    for key in ("estimated_pnl_usdc", "estimated_pnl_usd", "realized_pnl", "realized_pnl_usdc", "pnl", "out_of_sample_pnl"):
        if key not in trade or trade.get(key) in (None, ""):
            continue
        try:
            return float(trade.get(key))
        except (TypeError, ValueError):
            continue
    return None


def _trade_bridge_keys(row: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    for key in ("market_id", "marketId", "id", "condition_id", "conditionId", "token_id", "tokenId", "slug", "title", "question"):
        _append_key(keys, row.get(key))
    match = row.get("resolution_match") if isinstance(row.get("resolution_match"), dict) else {}
    resolution = match.get("resolution") if isinstance(match.get("resolution"), dict) else row.get("resolution") if isinstance(row.get("resolution"), dict) else {}
    if isinstance(resolution, dict):
        for key in ("primary_key", "matched_key", "question", "slug"):
            _append_key(keys, resolution.get(key))
    return keys


def _append_key(keys: list[str], value: Any) -> None:
    text = str(value or "").strip()
    if text and text not in keys:
        keys.append(text)


def _copy_bridge_fields(target: dict[str, Any], source: dict[str, Any], fields: tuple[str, ...]) -> None:
    for key in fields:
        if key in source and (target.get(key) is None or target.get(key) == ""):
            target[key] = source[key]


def _current_orderbooks_from_snapshots(payload: dict[str, Any]) -> dict[str, Any]:
    rows = payload.get("snapshots") or payload.get("orderbook_snapshots") or payload.get("orderbooks") or []
    out: list[dict[str, Any]] = []
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            if row.get("best_bid") is not None or row.get("best_ask") is not None or row.get("spread") is not None:
                out.append(dict(row))
    return {"paper_only": True, "live_order_allowed": False, "orderbooks": out}


def _market_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("markets") or payload.get("current_markets") or payload.get("rows") or payload.get("data") or []
    if isinstance(rows, list):
        return [dict(row) for row in rows if isinstance(row, dict)]
    return []


def _load_object(path: str | Path, label: str) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
