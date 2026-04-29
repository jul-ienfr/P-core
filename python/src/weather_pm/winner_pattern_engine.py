from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path
from typing import Any


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
            "paper_only": True,
            "live_order_allowed": False,
        }
        feature_counts["market_type"] += 1
        feature_counts[f"archetype:{archetype}"] += 1
        if total_pnl < 0 or (rows and bad_capturability / max(1, len(rows)) > 0.5):
            anti.append({**base, "pattern_status": "anti_pattern", "block_live_radar": True, "reason": "negative_out_of_sample_pnl" if total_pnl < 0 else "bad_capturability"})
        elif resolved_count < min_resolved_trades or top1_share > max_top1_pnl_share:
            research.append({**base, "pattern_status": "research_only", "block_live_radar": False, "reason": "concentrated_or_small_sample"})
        elif total_pnl > 0 and capturable_count >= min_resolved_trades:
            robust.append({**base, "pattern_status": "robust_candidate", "block_live_radar": False, "reason": "positive_capturable_out_of_sample"})
        else:
            research.append({**base, "pattern_status": "research_only", "block_live_radar": False, "reason": "insufficient_positive_capturable_evidence"})

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
        actions.append("Expand sample size and reduce wallet concentration before promotion.")
    if capturability_gaps:
        actions.append("Backfill historical L2/orderbook snapshots to close capturability gaps.")
    return actions


def render_winner_pattern_markdown(payload: dict[str, Any]) -> str:
    summary = payload.get("summary", {}) if isinstance(payload.get("summary"), dict) else {}
    lines = ["# Weather Winner Pattern Engine", "", "## Safety", "", "- paper_only: true", "- live_order_allowed: false", "", "## Summary", ""]
    lines.append(f"- Robust patterns: {summary.get('robust_patterns', len(payload.get('robust_patterns', [])))}")
    lines.append(f"- Anti-patterns: {summary.get('anti_patterns', len(payload.get('anti_patterns', [])))}")
    lines.append(f"- Research-only patterns: {summary.get('research_only_patterns', len(payload.get('research_only_patterns', [])))}")
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
