from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from typing import Any


def _count(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    return len(value) if isinstance(value, list) else 0


def build_winner_pattern_operator_report(
    winner_patterns: dict[str, Any],
    paper_candidates: dict[str, Any],
    *,
    resolution_coverage: dict[str, Any] | None = None,
    orderbook_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    robust = _count(winner_patterns, "robust_patterns")
    anti = _count(winner_patterns, "anti_patterns")
    research = _count(winner_patterns, "research_only_patterns")
    candidates = _count(paper_candidates, "paper_candidates")
    watch = _count(paper_candidates, "watch_only")
    blocked = _count(paper_candidates, "blocked")
    all_patterns = [
        row
        for key in ("robust_patterns", "research_only_patterns", "anti_patterns")
        for row in (winner_patterns.get(key, []) if isinstance(winner_patterns.get(key), list) else [])
        if isinstance(row, dict)
    ]
    promotion_eligible = sum(1 for row in all_patterns if row.get("promotion_eligible") is True)
    promotion_blocked = sum(1 for row in all_patterns if row.get("promotion_eligible") is False and row.get("promotion_blockers"))
    candidate_summary = paper_candidates.get("summary", {}) if isinstance(paper_candidates.get("summary"), dict) else {}
    research_only_matches = int(candidate_summary.get("research_only_matches", 0)) if isinstance(candidate_summary, dict) else 0
    top_blockers = _top_promotion_blockers(all_patterns)
    blocker_gaps = _promotion_blocker_gaps(all_patterns)
    closest_research = _closest_research_only_patterns(
        winner_patterns.get("research_only_patterns", []) if isinstance(winner_patterns.get("research_only_patterns"), list) else []
    )
    coverage_summary = resolution_coverage.get("summary", resolution_coverage) if isinstance(resolution_coverage, dict) else {}
    orderbook_summary = orderbook_context.get("summary", orderbook_context) if isinstance(orderbook_context, dict) else {}
    missing_books = orderbook_summary.get("missing_orderbook_context", orderbook_summary.get("missing_current_orderbook")) if isinstance(orderbook_summary, dict) else None
    md = _markdown(winner_patterns, paper_candidates, coverage_summary if isinstance(coverage_summary, dict) else {}, orderbook_summary if isinstance(orderbook_summary, dict) else {})
    return {
        "paper_only": True,
        "live_order_allowed": False,
        "summary": {
            "robust_patterns": robust,
            "anti_patterns": anti,
            "research_only_patterns": research,
            "paper_candidates": candidates,
            "watch_only": watch,
            "blocked": blocked,
            "research_only_matches": research_only_matches,
            "promotion_eligible_patterns": promotion_eligible,
            "promotion_blocked_patterns": promotion_blocked,
            "promotion_gate_version": (winner_patterns.get("summary", {}) if isinstance(winner_patterns.get("summary"), dict) else {}).get("promotion_gate_version"),
            "top_promotion_blockers": top_blockers,
            "promotion_blocker_gaps": blocker_gaps,
            "closest_research_only_patterns": closest_research,
            "resolved_pct": coverage_summary.get("resolved_pct") if isinstance(coverage_summary, dict) else None,
            "capturability_gaps": missing_books,
        },
        "markdown": md,
        "inputs_present": {"resolution_coverage": resolution_coverage is not None, "orderbook_context": orderbook_context is not None},
    }


def _top_promotion_blockers(patterns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    for row in patterns:
        blockers = row.get("promotion_blockers") if isinstance(row.get("promotion_blockers"), list) else []
        counts.update(str(blocker) for blocker in blockers)
    return [
        {"blocker": blocker, "patterns": count}
        for blocker, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:10]
    ]


def _as_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    number = _as_float(value)
    return int(number) if number is not None else None


def _count_gap(pattern_id: Any, blocker: str, current: int | None, required: int) -> dict[str, Any] | None:
    if current is None:
        return None
    return {
        "pattern_id": pattern_id,
        "blocker": blocker,
        "current": current,
        "required": required,
        "missing": max(0, required - current),
    }


def _pct_gap(pattern_id: Any, blocker: str, pct_value: Any, denominator: int | None, required_pct: float) -> dict[str, Any] | None:
    pct = _as_float(pct_value)
    if pct is None or denominator is None or denominator <= 0:
        return None
    current = min(denominator, max(0, int(math.floor((pct / 100.0) * denominator + 1e-9))))
    required = min(denominator, int(math.ceil((required_pct / 100.0) * denominator)))
    return {
        "pattern_id": pattern_id,
        "blocker": blocker,
        "current": f"{current}/{denominator}",
        "required": f"{required}/{denominator}",
        "missing": max(0, required - current),
    }


def _ratio_gap(pattern_id: Any, blocker: str, ratio_value: Any, denominator: int | None, required_ratio: float) -> dict[str, Any] | None:
    ratio = _as_float(ratio_value)
    if ratio is None or denominator is None or denominator <= 0:
        return None
    current = min(denominator, max(0, int(math.floor(ratio * denominator + 1e-9))))
    required = min(denominator, int(math.ceil(required_ratio * denominator)))
    return {
        "pattern_id": pattern_id,
        "blocker": blocker,
        "current": f"{current}/{denominator}",
        "required": f"{required}/{denominator}",
        "missing": max(0, required - current),
    }


def _promotion_blocker_gap(pattern: dict[str, Any], blocker: str) -> dict[str, Any] | None:
    metrics = pattern.get("promotion_metrics") if isinstance(pattern.get("promotion_metrics"), dict) else {}
    pattern_id = pattern.get("pattern_id")
    resolved = _as_int(metrics.get("resolved_trades", pattern.get("resolved_trades")))
    if blocker == "insufficient_resolved_sample":
        return _count_gap(pattern_id, blocker, resolved, 20)
    if blocker == "insufficient_capturable_resolved_sample":
        current = _as_int(metrics.get("capturable_resolved_trades"))
        return _count_gap(pattern_id, blocker, current, 16) or _ratio_gap(pattern_id, blocker, metrics.get("capturable_ratio"), resolved, 0.80)
    if blocker == "insufficient_independent_wallets":
        return _count_gap(pattern_id, blocker, _as_int(metrics.get("unique_wallets")), 4)
    if blocker == "insufficient_positive_wallets":
        return _count_gap(pattern_id, blocker, _as_int(metrics.get("positive_wallets")), 3)
    if blocker == "insufficient_out_of_sample_sample":
        return _count_gap(pattern_id, blocker, _as_int(metrics.get("oos_resolved_trades")), 8)
    if blocker == "insufficient_oos_capturable_sample":
        return _count_gap(pattern_id, blocker, _as_int(metrics.get("oos_capturable_trades")), 6)
    if blocker == "insufficient_historical_orderbook_coverage":
        return _ratio_gap(pattern_id, blocker, metrics.get("historical_orderbook_coverage_ratio"), resolved, 0.80)
    if blocker == "insufficient_historical_capturable_ratio":
        return _ratio_gap(pattern_id, blocker, metrics.get("historical_capturable_ratio"), resolved, 0.70)
    if blocker == "missing_weather_context":
        return _pct_gap(pattern_id, blocker, metrics.get("weather_context_coverage_pct"), resolved, 100.0)
    if blocker == "incomplete_forecast_context":
        return _pct_gap(pattern_id, blocker, metrics.get("forecast_complete_pct"), resolved, 95.0)
    if blocker == "stale_forecast":
        return _pct_gap(pattern_id, blocker, metrics.get("forecast_fresh_pct"), resolved, 90.0)
    if blocker == "unverified_resolution":
        return _pct_gap(pattern_id, blocker, metrics.get("resolution_verified_pct"), resolved, 95.0)
    return None


def _promotion_blocker_gaps(patterns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    for pattern in patterns:
        blockers = pattern.get("promotion_blockers") if isinstance(pattern.get("promotion_blockers"), list) else []
        for blocker in blockers:
            gap = _promotion_blocker_gap(pattern, str(blocker))
            if gap is not None:
                gaps.append(gap)
    return gaps[:25]


def _format_blocker_gap(gap: dict[str, Any]) -> str:
    return f"{gap['pattern_id']} / {gap['blocker']}: {gap['current']}, need {gap['required']} (+{gap['missing']})"


def _readiness_score(pattern: dict[str, Any]) -> float:
    metrics = pattern.get("promotion_metrics") if isinstance(pattern.get("promotion_metrics"), dict) else {}
    resolved = min(float(metrics.get("resolved_trades") or pattern.get("resolved_trades") or 0) / 20.0, 1.0)
    capturable = min(float(metrics.get("historical_capturable_ratio") or 0.0), 1.0)
    fresh = min(float(metrics.get("forecast_fresh_pct") or 0.0) / 100.0, 1.0)
    oos_positive = 1.0 if float(metrics.get("oos_pnl") or pattern.get("out_of_sample_pnl") or 0.0) > 0 else 0.0
    blocker_penalty = max(0.0, 1.0 - 0.08 * len(pattern.get("promotion_blockers") if isinstance(pattern.get("promotion_blockers"), list) else []))
    return round(((resolved * 0.35) + (capturable * 0.25) + (fresh * 0.20) + (oos_positive * 0.20)) * blocker_penalty, 3)


def _closest_research_only_patterns(research: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in research:
        if not isinstance(row, dict):
            continue
        metrics = row.get("promotion_metrics") if isinstance(row.get("promotion_metrics"), dict) else {}
        rows.append(
            {
                "pattern_id": row.get("pattern_id"),
                "reason": row.get("reason"),
                "readiness_score": _readiness_score(row),
                "resolved_trades": metrics.get("resolved_trades", row.get("resolved_trades")),
                "out_of_sample_pnl": metrics.get("oos_pnl", row.get("out_of_sample_pnl")),
                "promotion_blockers": list(row.get("promotion_blockers") or []) if isinstance(row.get("promotion_blockers"), list) else [],
                "paper_only": True,
                "live_order_allowed": False,
            }
        )
    rows.sort(key=lambda row: (float(row.get("readiness_score") or 0.0), float(row.get("out_of_sample_pnl") or 0.0), int(row.get("resolved_trades") or 0)), reverse=True)
    return rows[:10]


def _markdown(winner_patterns: dict[str, Any], paper_candidates: dict[str, Any], coverage: dict[str, Any], orderbook: dict[str, Any]) -> str:
    robust = winner_patterns.get("robust_patterns", []) if isinstance(winner_patterns.get("robust_patterns"), list) else []
    anti = winner_patterns.get("anti_patterns", []) if isinstance(winner_patterns.get("anti_patterns"), list) else []
    research = winner_patterns.get("research_only_patterns", []) if isinstance(winner_patterns.get("research_only_patterns"), list) else []
    watch = paper_candidates.get("watch_only", []) if isinstance(paper_candidates.get("watch_only"), list) else []
    candidates = paper_candidates.get("paper_candidates", []) if isinstance(paper_candidates.get("paper_candidates"), list) else []
    candidate_summary = paper_candidates.get("summary", {}) if isinstance(paper_candidates.get("summary"), dict) else {}
    lines = [
        "# Weather Winner Pattern Engine",
        "",
        "## Safety",
        "",
        "- paper_only: true",
        "- live_order_allowed: false",
        "- Paper probes only; no signing, placement, or cancellation authority.",
        "",
        "## Coverage",
        "",
        f"- Resolution coverage: {coverage.get('resolved_pct', 'unknown')}",
        f"- Missing orderbook context: {orderbook.get('missing_orderbook_context', 'unknown')}",
        "",
        "## Robust patterns",
        "",
    ]
    lines.extend([f"- {row.get('pattern_id', 'pattern')} ({row.get('archetype', 'unclear')})" for row in robust[:10] if isinstance(row, dict)] or ["- none"])
    lines.extend(["", "## Research-only patterns", ""])
    lines.extend([f"- {row.get('pattern_id', 'pattern')}: {row.get('reason', 'research_only')} ({row.get('examples', 0)} examples)" for row in research[:10] if isinstance(row, dict)] or ["- none"])
    lines.extend(["", "## Anti-patterns", ""])
    lines.extend([f"- {row.get('pattern_id', 'pattern')}: {row.get('reason', 'blocked')}" for row in anti[:10] if isinstance(row, dict)] or ["- none"])
    summary = winner_patterns.get("summary", {}) if isinstance(winner_patterns.get("summary"), dict) else {}
    eligible = sum(1 for row in robust if isinstance(row, dict) and row.get("promotion_eligible") is True)
    blocked_patterns = [
        row
        for row in [*robust, *research, *anti]
        if isinstance(row, dict) and row.get("promotion_eligible") is False and row.get("promotion_blockers")
    ]
    top_blockers = _top_promotion_blockers(blocked_patterns)
    blocker_gaps = _promotion_blocker_gaps(blocked_patterns)
    closest_research = _closest_research_only_patterns(research)
    lines.extend(["", "## Capturability gaps", ""])
    lines.append(f"- Historical/current orderbook gaps: {orderbook.get('missing_orderbook_context', orderbook.get('missing_current_orderbook', 'unknown'))}")
    lines.extend(["", "## Promotion readiness", ""])
    lines.append(f"- Promotion gate: {summary.get('promotion_gate_version', 'unknown')}")
    lines.append(f"- Eligible robust patterns: {eligible}")
    lines.append(f"- Blocked patterns with explicit blockers: {len(blocked_patterns)}")
    lines.extend(["", "## Promotion blockers", ""])
    for row in blocked_patterns[:10]:
        blockers = row.get("promotion_blockers") if isinstance(row.get("promotion_blockers"), list) else []
        lines.append(f"- {row.get('pattern_id', 'pattern')}: {', '.join(str(blocker) for blocker in blockers) or row.get('reason', 'blocked')}")
    if not blocked_patterns:
        lines.append("- none")
    lines.extend(["", "### Top promotion blockers", ""])
    lines.extend([f"- {row['blocker']}: {row['patterns']}" for row in top_blockers] or ["- none"])
    lines.extend(["", "### Promotion blocker gaps", ""])
    lines.extend([f"- {_format_blocker_gap(row)}" for row in blocker_gaps] or ["- none"])
    lines.extend(["", "### Closest research-only patterns", ""])
    for row in closest_research[:10]:
        blockers = row.get("promotion_blockers") if isinstance(row.get("promotion_blockers"), list) else []
        lines.append(
            f"- {row.get('pattern_id')}: readiness={row.get('readiness_score')} "
            f"resolved={row.get('resolved_trades')} pnl={row.get('out_of_sample_pnl')} "
            f"blockers={', '.join(str(blocker) for blocker in blockers) or 'none'}"
        )
    if not closest_research:
        lines.append("- none")
    lines.extend(["", "## Paper candidates / watch-only", ""])
    lines.append(f"- Paper candidates: {len(candidates)}")
    lines.append(f"- Watch-only: {len(watch)}")
    lines.append(f"- Research-only matches: {candidate_summary.get('research_only_matches', 0)}")
    for row in watch[:10]:
        if isinstance(row, dict):
            suffix = f" -> {row.get('matched_pattern_id')}" if row.get("matched_pattern_id") else ""
            lines.append(f"  - {row.get('market_id')}: {row.get('reason')}{suffix}")
    lines.extend(["", "## Next data gaps", ""])
    for action in winner_patterns.get("operator_next_actions", []) if isinstance(winner_patterns.get("operator_next_actions"), list) else []:
        lines.append(f"- {action}")
    if len(lines) > 0 and lines[-1] == "## Next data gaps":
        lines.append("- Expand resolution, orderbook, and forecast-at-decision coverage.")
    return "\n".join(lines) + "\n"


def write_winner_pattern_operator_report(
    winner_patterns_json: str | Path,
    paper_candidates_json: str | Path,
    output_json: str | Path,
    output_md: str | Path,
    *,
    resolution_coverage_json: str | Path | None = None,
    orderbook_context_json: str | Path | None = None,
) -> dict[str, Any]:
    coverage = json.loads(Path(resolution_coverage_json).read_text(encoding="utf-8")) if resolution_coverage_json else None
    orderbook = json.loads(Path(orderbook_context_json).read_text(encoding="utf-8")) if orderbook_context_json else None
    payload = build_winner_pattern_operator_report(
        json.loads(Path(winner_patterns_json).read_text(encoding="utf-8")),
        json.loads(Path(paper_candidates_json).read_text(encoding="utf-8")),
        resolution_coverage=coverage,
        orderbook_context=orderbook,
    )
    out = Path(output_json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    md = Path(output_md)
    md.parent.mkdir(parents=True, exist_ok=True)
    md.write_text(payload["markdown"], encoding="utf-8")
    summary = payload["summary"]
    return {
        "paper_only": True,
        "live_order_allowed": False,
        "robust_patterns": summary["robust_patterns"],
        "paper_candidates": summary["paper_candidates"],
        "watch_only": summary["watch_only"],
        "output_md": str(md),
    }
