from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path
from typing import Any

PROMOTION_GATE_VERSION = "weather_winner_pattern_v2_2026_04"


def _rows(payload: dict[str, Any], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [dict(row) for row in value if isinstance(row, dict)]
    return []


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _ratio(numerator: int | float, denominator: int | float) -> float:
    return round((float(numerator) / float(denominator)), 6) if denominator else 0.0


def _pct(numerator: int | float, denominator: int | float) -> float:
    return round(_ratio(numerator, denominator) * 100.0, 6)


def _percentile(values: list[float], pct: float) -> float | None:
    cleaned = sorted(values)
    if not cleaned:
        return None
    if len(cleaned) == 1:
        return round(cleaned[0], 6)
    pos = (len(cleaned) - 1) * pct
    low = int(pos)
    high = min(low + 1, len(cleaned) - 1)
    weight = pos - low
    return round(cleaned[low] * (1.0 - weight) + cleaned[high] * weight, 6)


def classify_archetype(example: dict[str, Any]) -> str:
    label = str(example.get("label") or "").lower()
    market_type = str(example.get("market_type") or example.get("surface") or "").lower()
    if label == "no_trade":
        return "abstention_filter"
    if "exact" in market_type or example.get("bin_center") is not None and "bin" in market_type:
        return "exact_bin_anomaly_hunter"
    if _num(example.get("surface_count"), 0) >= 3 or _num(example.get("markets_in_surface"), 0) >= 3:
        return "surface_grid_trader"
    if example.get("forecast_age_minutes") is not None and _num(example.get("forecast_age_minutes"), 9999) <= 15 and _num(example.get("price"), 0) >= 0.75:
        return "late_certainty_compounder"
    if example.get("distance_to_threshold") is not None and abs(_num(example.get("distance_to_threshold"))) <= 1.0:
        return "threshold_harvester"
    return "unclear"


def _key(example: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(example.get("market_type") or "unknown"),
        str(example.get("city") or "any"),
        str(example.get("side") or "any").upper(),
        classify_archetype(example),
    )


def _pattern_id(key: tuple[str, str, str, str]) -> str:
    return "|".join(part.lower().replace(" ", "_") for part in key)


def _is_out_of_sample(row: dict[str, Any], index: int, total: int) -> bool:
    split = str(row.get("sample_split") or row.get("split") or "").lower()
    if split in {"out_of_sample", "oos", "validation", "test"}:
        return True
    if split in {"train", "training", "discovery"}:
        return False
    return index >= max(0, int(total * 0.6))


def _has_v2_promotion_context(rows: list[dict[str, Any]]) -> bool:
    v2_keys = {
        "sample_split",
        "forecast_value_at_decision",
        "threshold",
        "bin_center",
        "resolution_verified",
        "resolution_source",
        "time_to_resolution_minutes",
        "spread",
        "depth_near_touch",
        "estimated_slippage_bps",
        "staleness_seconds",
    }
    return any(any(key in row for key in v2_keys) for row in rows)


def _promotion_metrics_and_blockers(rows: list[dict[str, Any]], *, min_resolved_v2: int = 20) -> tuple[dict[str, Any], list[str]]:
    resolved = [row for row in rows if row.get("pnl") is not None or row.get("out_of_sample_pnl") is not None]
    resolved_count = len(resolved)
    denominator = max(1, resolved_count)
    pnls = [_num(row.get("out_of_sample_pnl", row.get("pnl")), 0.0) for row in resolved]
    total_pnl = sum(pnls)

    capturable = [row for row in resolved if str(row.get("capturability") or "").lower() == "capturable"]
    bad_capturability = [
        row
        for row in resolved
        if str(row.get("capturability") or "").lower() in {"not_capturable", "unknown"} or row.get("orderbook_context_available") is False
    ]
    orderbook_available = [row for row in resolved if row.get("orderbook_context_available") is True]

    wallet_counts: Counter[str] = Counter()
    wallet_pnl: dict[str, float] = defaultdict(float)
    for row, pnl in zip(resolved, pnls):
        wallet = str(row.get("wallet") or row.get("account") or "unknown")
        wallet_counts[wallet] += 1
        wallet_pnl[wallet] += pnl
    positive_wallet_pnls = sorted((pnl for pnl in wallet_pnl.values() if pnl > 0), reverse=True)
    positive_wallet_total = sum(positive_wallet_pnls)
    top_wallet = max(wallet_pnl, key=lambda wallet: wallet_pnl[wallet], default="")

    positive_trade_pnls = sorted((pnl for pnl in pnls if pnl > 0), reverse=True)
    positive_trade_total = sum(positive_trade_pnls)

    oos_rows = [row for idx, row in enumerate(resolved) if _is_out_of_sample(row, idx, resolved_count)]
    oos_pnls = [_num(row.get("out_of_sample_pnl", row.get("pnl")), 0.0) for row in oos_rows]
    oos_pnl = sum(oos_pnls)
    oos_notional = sum(_num(row.get("notional") or row.get("stake") or row.get("amount"), 0.0) for row in oos_rows)
    oos_roi = (oos_pnl / oos_notional) if oos_notional else None
    oos_gains = sum(pnl for pnl in oos_pnls if pnl > 0)
    oos_losses = abs(sum(pnl for pnl in oos_pnls if pnl < 0))
    oos_profit_factor = (oos_gains / oos_losses) if oos_losses else (999.0 if oos_gains > 0 else 0.0)
    oos_win_rate = _ratio(sum(1 for pnl in oos_pnls if pnl > 0), len(oos_pnls))
    oos_capturable = sum(1 for row in oos_rows if str(row.get("capturability") or "").lower() == "capturable")

    spreads = [_num(row.get("spread"), 0.0) for row in resolved if row.get("spread") is not None]
    depths = [_num(row.get("depth_near_touch"), 0.0) for row in resolved if row.get("depth_near_touch") is not None]
    slippages = [_num(row.get("estimated_slippage_bps"), 0.0) for row in resolved if row.get("estimated_slippage_bps") is not None]
    stale_contexts = sum(1 for row in resolved if row.get("staleness_seconds") is not None and _num(row.get("staleness_seconds"), 0.0) > 3600)

    forecast_complete = [
        row
        for row in resolved
        if row.get("weather_context_available") is True
        and row.get("forecast_value_at_decision") is not None
        and (row.get("threshold") is not None or row.get("bin_center") is not None)
    ]
    fresh_forecasts = [row for row in forecast_complete if 0 <= _num(row.get("forecast_age_minutes"), 999999) <= 120]
    verified_resolutions = [
        row
        for row in resolved
        if row.get("resolution_verified") is True
        or (row.get("resolution_verified") is not False and str(row.get("resolution_source") or "").startswith("official"))
    ]
    distances = [abs(_num(row.get("distance_to_threshold"), 0.0)) for row in resolved if row.get("distance_to_threshold") is not None]
    near_threshold = [distance for distance in distances if distance < 0.5]
    time_to_resolution = [_num(row.get("time_to_resolution_minutes"), 0.0) for row in resolved if row.get("time_to_resolution_minutes") is not None]

    metrics = {
        "resolved_trades": resolved_count,
        "capturable_resolved_trades": len(capturable),
        "capturable_ratio": _ratio(len(capturable), denominator),
        "bad_capturability_ratio": _ratio(len(bad_capturability), denominator),
        "unique_wallets": len(wallet_counts),
        "positive_wallets": sum(1 for pnl in wallet_pnl.values() if pnl > 0),
        "max_wallet_trade_share": round(max(wallet_counts.values(), default=0) / denominator, 6),
        "max_wallet_positive_pnl_share": round((positive_wallet_pnls[0] / positive_wallet_total) if positive_wallet_total else 0.0, 6),
        "top3_wallet_positive_pnl_share": round((sum(positive_wallet_pnls[:3]) / positive_wallet_total) if positive_wallet_total else 0.0, 6),
        "pnl_without_top_wallet": round(total_pnl - wallet_pnl.get(top_wallet, 0.0), 6),
        "max_trade_positive_pnl_share": round((positive_trade_pnls[0] / positive_trade_total) if positive_trade_total else 0.0, 6),
        "top3_trade_positive_pnl_share": round((sum(positive_trade_pnls[:3]) / positive_trade_total) if positive_trade_total else 0.0, 6),
        "pnl_without_top_trade": round(total_pnl - (positive_trade_pnls[0] if positive_trade_pnls else 0.0), 6),
        "oos_resolved_trades": len(oos_rows),
        "oos_capturable_trades": oos_capturable,
        "oos_pnl": round(oos_pnl, 6),
        "oos_roi": round(oos_roi, 6) if oos_roi is not None else None,
        "oos_win_rate": round(oos_win_rate, 6),
        "oos_profit_factor": round(oos_profit_factor, 6),
        "historical_orderbook_coverage_ratio": _ratio(len(orderbook_available), denominator),
        "historical_capturable_ratio": _ratio(len(capturable), denominator),
        "stale_context_ratio": _ratio(stale_contexts, denominator),
        "median_spread": _percentile(spreads, 0.5),
        "p90_spread": _percentile(spreads, 0.9),
        "median_depth_near_touch": _percentile(depths, 0.5),
        "p90_estimated_slippage_bps": _percentile(slippages, 0.9),
        "weather_context_coverage_pct": _pct(sum(1 for row in resolved if row.get("weather_context_available") is True), denominator),
        "forecast_complete_pct": _pct(len(forecast_complete), denominator),
        "forecast_fresh_pct": _pct(len(fresh_forecasts), denominator),
        "resolution_verified_pct": _pct(len(verified_resolutions), denominator),
        "median_abs_distance_to_threshold": _percentile(distances, 0.5),
        "near_threshold_share_pct": _pct(len(near_threshold), len(distances) or denominator),
        "median_time_to_resolution_minutes": _percentile(time_to_resolution, 0.5),
        "p95_time_to_resolution_minutes": _percentile(time_to_resolution, 0.95),
    }

    blockers: list[str] = []

    def block(condition: bool, reason: str) -> None:
        if condition and reason not in blockers:
            blockers.append(reason)

    block(resolved_count < min_resolved_v2, "insufficient_resolved_sample")
    block(len(capturable) < 16 or metrics["capturable_ratio"] < 0.8, "insufficient_capturable_resolved_sample")
    block(len(wallet_counts) < 4, "insufficient_independent_wallets")
    block(metrics["positive_wallets"] < 3, "insufficient_positive_wallets")
    block(metrics["max_wallet_trade_share"] > 0.50 or metrics["max_wallet_positive_pnl_share"] > 0.45, "wallet_concentrated_pnl")
    block(metrics["pnl_without_top_wallet"] <= 0, "top_wallet_dependent_pnl")
    block(metrics["pnl_without_top_trade"] <= 0 or metrics["max_trade_positive_pnl_share"] > 0.35, "trade_concentrated_pnl")
    block(len(oos_rows) < 8, "insufficient_out_of_sample_sample")
    block(oos_capturable < 6, "insufficient_oos_capturable_sample")
    block(oos_pnl <= 0 or (oos_roi is not None and oos_roi < 0.03) or oos_win_rate < 0.52 or oos_profit_factor < 1.20, "weak_out_of_sample_pnl")
    block(metrics["historical_orderbook_coverage_ratio"] < 0.80, "insufficient_historical_orderbook_coverage")
    block(metrics["historical_capturable_ratio"] < 0.70, "insufficient_historical_capturable_ratio")
    block(metrics["bad_capturability_ratio"] > 0.20, "bad_capturability_ratio")
    block(metrics["stale_context_ratio"] > 0.10, "historical_snapshots_stale")
    block((metrics["median_spread"] is not None and metrics["median_spread"] > 0.06) or (metrics["p90_spread"] is not None and metrics["p90_spread"] > 0.10), "historical_spread_too_wide")
    block(metrics["median_depth_near_touch"] is not None and metrics["median_depth_near_touch"] < 25, "historical_depth_too_thin")
    block(metrics["p90_estimated_slippage_bps"] is not None and metrics["p90_estimated_slippage_bps"] > 250, "historical_slippage_too_high")
    block(metrics["weather_context_coverage_pct"] < 100.0, "missing_weather_context")
    block(metrics["forecast_complete_pct"] < 95.0, "incomplete_forecast_context")
    block(metrics["forecast_fresh_pct"] < 90.0, "stale_forecast")
    block(metrics["resolution_verified_pct"] < 95.0, "unverified_resolution")
    block((metrics["median_abs_distance_to_threshold"] is not None and metrics["median_abs_distance_to_threshold"] < 1.0) or metrics["near_threshold_share_pct"] > 35.0, "near_threshold_share_too_high")
    block(metrics["median_time_to_resolution_minutes"] is None or metrics["median_time_to_resolution_minutes"] > 360 or (metrics["p95_time_to_resolution_minutes"] is not None and metrics["p95_time_to_resolution_minutes"] > 1440), "slow_resolution_feedback_loop")

    return metrics, blockers


def build_winner_pattern_engine(
    decision_context: dict[str, Any],
    resolved_trades: dict[str, Any] | None = None,
    *,
    min_resolved_trades: int = 5,
    max_top1_pnl_share: float = 0.8,
) -> dict[str, Any]:
    examples = _rows(decision_context, ("examples", "decisions", "rows"))
    resolved_rows = _rows(resolved_trades or {}, ("trades", "resolved_trades", "examples"))
    if resolved_rows:
        by_market = {str(row.get("market_id") or row.get("id") or ""): row for row in resolved_rows}
        for ex in examples:
            rid = str(ex.get("market_id") or "")
            if rid in by_market:
                for k in ("pnl", "out_of_sample_pnl", "capturability", "orderbook_context_available", "wallet", "account"):
                    if k not in ex and k in by_market[rid]:
                        ex[k] = by_market[rid][k]

    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for ex in examples:
        if str(ex.get("label", "trade")).lower() in {"trade", "no_trade"}:
            grouped[_key(ex)].append(ex)

    robust: list[dict[str, Any]] = []
    anti: list[dict[str, Any]] = []
    research: list[dict[str, Any]] = []
    account_pnl: dict[str, float] = defaultdict(float)
    account_counts: Counter[str] = Counter()
    feature_counts: Counter[str] = Counter()
    capturability_gaps = 0

    for key, rows in grouped.items():
        market_type, city, side, archetype = key
        resolved_count = sum(1 for row in rows if row.get("pnl") is not None or row.get("out_of_sample_pnl") is not None)
        total_pnl = sum(_num(row.get("out_of_sample_pnl", row.get("pnl")), 0.0) for row in rows)
        capturable_count = sum(1 for row in rows if str(row.get("capturability") or "").lower() == "capturable" or row.get("orderbook_context_available") is True)
        bad_capturability = sum(1 for row in rows if str(row.get("capturability") or "").lower() in {"not_capturable", "unknown"} or row.get("orderbook_context_available") is False)
        capturability_gaps += bad_capturability
        pnl_by_account: dict[str, float] = defaultdict(float)
        for row in rows:
            acct = str(row.get("wallet") or row.get("account") or "unknown")
            pnl = _num(row.get("out_of_sample_pnl", row.get("pnl")), 0.0)
            pnl_by_account[acct] += pnl
            account_pnl[acct] += pnl
            account_counts[acct] += 1
        positive_total = sum(v for v in pnl_by_account.values() if v > 0)
        top1_share = (max((v for v in pnl_by_account.values() if v > 0), default=0.0) / positive_total) if positive_total > 0 else 0.0
        use_v2_gate = _has_v2_promotion_context(rows)
        promotion_metrics, promotion_blockers = _promotion_metrics_and_blockers(rows) if use_v2_gate else ({}, [])
        base = {
            "pattern_id": _pattern_id(key),
            "market_type": market_type,
            "city": city,
            "side": side,
            "archetype": archetype,
            "resolved_trades": resolved_count,
            "examples": len(rows),
            "out_of_sample_pnl": round(total_pnl, 6),
            "capturable_contexts": capturable_count,
            "top1_pnl_share": round(top1_share, 6),
            "promotion_gate_version": PROMOTION_GATE_VERSION,
            "promotion_eligible": not promotion_blockers,
            "promotion_blockers": promotion_blockers,
            "promotion_metrics": promotion_metrics,
            "paper_only": True,
            "live_order_allowed": False,
        }
        feature_counts["market_type"] += 1
        feature_counts[f"archetype:{archetype}"] += 1
        if total_pnl < 0:
            anti.append({**base, "promotion_eligible": False, "pattern_status": "anti_pattern", "block_live_radar": True, "reason": "negative_out_of_sample_pnl"})
        elif use_v2_gate and promotion_blockers:
            research.append({**base, "promotion_eligible": False, "pattern_status": "research_only", "block_live_radar": False, "reason": promotion_blockers[0]})
        elif resolved_count < min_resolved_trades or top1_share > max_top1_pnl_share:
            research.append({**base, "promotion_eligible": False, "pattern_status": "research_only", "block_live_radar": False, "reason": "concentrated_or_small_sample"})
        elif total_pnl > 0 and capturable_count >= min_resolved_trades:
            reason = "passed_weather_winner_pattern_v2_promotion_gate" if use_v2_gate else "positive_capturable_out_of_sample"
            robust.append({**base, "promotion_eligible": not promotion_blockers, "pattern_status": "robust_candidate", "block_live_radar": False, "reason": reason})
        else:
            research.append({**base, "promotion_eligible": False, "pattern_status": "research_only", "block_live_radar": False, "reason": "insufficient_positive_capturable_evidence"})

    robust.sort(key=lambda r: (_num(r.get("out_of_sample_pnl")), _num(r.get("resolved_trades"))), reverse=True)
    anti.sort(key=lambda r: _num(r.get("out_of_sample_pnl")))
    account_summaries = [
        {"account": acct, "trades": account_counts[acct], "pnl": round(pnl, 6), "paper_only": True, "live_order_allowed": False}
        for acct, pnl in sorted(account_pnl.items(), key=lambda item: item[1], reverse=True)
    ]
    return {
        "paper_only": True,
        "live_order_allowed": False,
        "summary": {
            "examples": len(examples),
            "robust_patterns": len(robust),
            "anti_patterns": len(anti),
            "research_only_patterns": len(research),
            "capturability_gaps": capturability_gaps,
            "promotion_gate_version": PROMOTION_GATE_VERSION,
            "promotion_eligible_patterns": sum(1 for row in robust if row.get("promotion_eligible") is True),
            "promotion_blocked_patterns": sum(1 for row in research if row.get("promotion_eligible") is False),
        },
        "robust_patterns": robust,
        "anti_patterns": anti,
        "research_only_patterns": research,
        "account_summaries": account_summaries,
        "feature_importance_counters": dict(feature_counts),
        "operator_next_actions": _next_actions(robust, anti, research, capturability_gaps),
    }


def _next_actions(robust: list[dict[str, Any]], anti: list[dict[str, Any]], research: list[dict[str, Any]], capturability_gaps: int) -> list[str]:
    actions = ["Keep all outputs paper-only; live_order_allowed remains false."]
    if robust:
        actions.append("Send robust candidates through paper candidate gate with current orderbook and weather checks.")
    if anti:
        actions.append("Block anti-pattern conflicts from live radar and paper probes.")
    if research:
        actions.append("Review promotion_blockers and expand sample/capturability/weather evidence before promotion.")
    if capturability_gaps:
        actions.append("Backfill historical L2/orderbook snapshots to close capturability gaps.")
    return actions


def render_winner_pattern_markdown(payload: dict[str, Any]) -> str:
    summary = payload.get("summary", {}) if isinstance(payload.get("summary"), dict) else {}
    lines = ["# Weather Winner Pattern Engine", "", "## Safety", "", "- paper_only: true", "- live_order_allowed: false", "", "## Summary", ""]
    lines.append(f"- Robust patterns: {summary.get('robust_patterns', len(payload.get('robust_patterns', [])))}")
    lines.append(f"- Anti-patterns: {summary.get('anti_patterns', len(payload.get('anti_patterns', [])))}")
    lines.append(f"- Research-only patterns: {summary.get('research_only_patterns', len(payload.get('research_only_patterns', [])))}")
    lines.append(f"- Promotion gate: {summary.get('promotion_gate_version', PROMOTION_GATE_VERSION)}")
    lines.append(f"- Promotion eligible patterns: {summary.get('promotion_eligible_patterns', 0)}")
    lines.append(f"- Promotion blocked patterns: {summary.get('promotion_blocked_patterns', 0)}")
    lines.extend(["", "## Operator next actions", ""])
    for action in payload.get("operator_next_actions", []):
        lines.append(f"- {action}")
    return "\n".join(lines) + "\n"


def write_winner_pattern_engine(
    decision_context_json: str | Path,
    resolved_trades_json: str | Path,
    output_json: str | Path,
    *,
    output_md: str | Path | None = None,
    min_resolved_trades: int = 5,
    max_top1_pnl_share: float = 0.8,
) -> dict[str, Any]:
    decision_context = json.loads(Path(decision_context_json).read_text(encoding="utf-8"))
    resolved_trades = json.loads(Path(resolved_trades_json).read_text(encoding="utf-8"))
    payload = build_winner_pattern_engine(decision_context, resolved_trades, min_resolved_trades=min_resolved_trades, max_top1_pnl_share=max_top1_pnl_share)
    out = Path(output_json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    if output_md:
        md = Path(output_md)
        md.parent.mkdir(parents=True, exist_ok=True)
        md.write_text(render_winner_pattern_markdown(payload), encoding="utf-8")
    return {
        "paper_only": True,
        "live_order_allowed": False,
        "robust_patterns": len(payload["robust_patterns"]),
        "anti_patterns": len(payload["anti_patterns"]),
        "research_only_patterns": len(payload["research_only_patterns"]),
        "output_json": str(out),
        "output_md": str(output_md) if output_md else None,
    }
