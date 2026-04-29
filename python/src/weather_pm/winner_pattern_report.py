from __future__ import annotations

import json
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
            "resolved_pct": coverage_summary.get("resolved_pct") if isinstance(coverage_summary, dict) else None,
            "capturability_gaps": missing_books,
        },
        "markdown": md,
        "inputs_present": {"resolution_coverage": resolution_coverage is not None, "orderbook_context": orderbook_context is not None},
    }


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
