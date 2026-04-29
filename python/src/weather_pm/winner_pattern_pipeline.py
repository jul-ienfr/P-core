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
    decision_path = _write_json(out_dir / "decision_dataset.json", decision_dataset)

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
        "winner_patterns": str(patterns_path),
        "paper_candidates": str(candidates_path),
        "operator_report": str(report_path),
    }
    artifact_counts = {
        "resolution_coverage": int(resolution_coverage.get("summary", {}).get("resolved", 0)),
        "orderbook_context": int(orderbook_context.get("summary", {}).get("with_orderbook_context", 0)),
        "decision_dataset": len(decision_dataset.get("examples", [])) if isinstance(decision_dataset.get("examples"), list) else 0,
        "weather_context": int(weather_context.get("summary", {}).get("with_weather_context", 0)),
        "winner_patterns": len(winner_patterns.get("robust_patterns", [])) if isinstance(winner_patterns.get("robust_patterns"), list) else 0,
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


def _merge_orderbook_context(decision_dataset: dict[str, Any], orderbook_context: dict[str, Any]) -> None:
    book_by_market: dict[str, dict[str, Any]] = {}
    for trade in orderbook_context.get("trades", []) if isinstance(orderbook_context.get("trades"), list) else []:
        if isinstance(trade, dict):
            market_id = str(trade.get("market_id") or trade.get("id") or "")
            if market_id:
                book_by_market[market_id] = trade
    for example in decision_dataset.get("examples", []) if isinstance(decision_dataset.get("examples"), list) else []:
        if not isinstance(example, dict):
            continue
        book = book_by_market.get(str(example.get("market_id") or ""))
        if book:
            for key in ("orderbook_context_available", "capturability", "capturable_score", "best_bid", "best_ask", "spread"):
                if key in book:
                    example[key] = book[key]


def _merge_resolution_matches(decision_dataset: dict[str, Any], resolution_coverage: dict[str, Any]) -> None:
    resolved_by_market: dict[str, dict[str, Any]] = {}
    for trade in resolution_coverage.get("trades", []) if isinstance(resolution_coverage.get("trades"), list) else []:
        if not isinstance(trade, dict):
            continue
        market_id = str(trade.get("market_id") or trade.get("id") or "")
        match = trade.get("resolution_match") if isinstance(trade.get("resolution_match"), dict) else {}
        if market_id and match.get("resolved") is True:
            resolved_by_market[market_id] = match
    for example in decision_dataset.get("examples", []) if isinstance(decision_dataset.get("examples"), list) else []:
        if not isinstance(example, dict):
            continue
        match = resolved_by_market.get(str(example.get("market_id") or ""))
        if match:
            example["pnl"] = match.get("pnl")
            example["outcome"] = match.get("outcome")
            example["winning_side"] = match.get("winning_side")


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
