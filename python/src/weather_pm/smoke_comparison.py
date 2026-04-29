from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def build_smoke_comparison(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    before_summary = _summary(before)
    after_summary = _summary(after)
    robust_before = _as_int(before_summary.get("robust_patterns"))
    robust_after = _as_int(after_summary.get("robust_patterns"))
    research_before = _as_int(before_summary.get("research_only_patterns"))
    research_after = _as_int(after_summary.get("research_only_patterns"))
    patterns = _pattern_deltas(before, after)
    context_deltas = _context_deltas(before, after)
    summary = {
        "robust_patterns_delta": robust_after - robust_before,
        "research_only_patterns_delta": research_after - research_before,
    }
    payload = {
        "paper_only": True,
        "live_order_allowed": False,
        "summary": summary,
        "before": {"robust_patterns": robust_before, "research_only_patterns": research_before},
        "after": {"robust_patterns": robust_after, "research_only_patterns": research_after},
        "context_deltas": context_deltas,
        "patterns": patterns,
    }
    payload["markdown"] = _markdown(payload)
    return payload


def write_smoke_comparison(before_json: str | Path, after_json: str | Path, output_json: str | Path, output_md: str | Path | None = None) -> dict[str, int]:
    payload = build_smoke_comparison(_load_object(before_json), _load_object(after_json))
    out = Path(output_json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    if output_md:
        md = Path(output_md)
        md.parent.mkdir(parents=True, exist_ok=True)
        md.write_text(payload["markdown"], encoding="utf-8")
    return dict(payload["summary"])


def _summary(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("summary")
    return value if isinstance(value, dict) else {}


def _pattern_deltas(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    before_patterns = _patterns_by_id(before)
    after_patterns = _patterns_by_id(after)
    rows: list[dict[str, Any]] = []
    for pattern_id in sorted(set(before_patterns) | set(after_patterns)):
        before_blockers = set(_blockers(before_patterns.get(pattern_id, {})))
        after_blockers = set(_blockers(after_patterns.get(pattern_id, {})))
        rows.append(
            {
                "pattern_id": pattern_id,
                "before_state": before_patterns.get(pattern_id, {}).get("state", "absent"),
                "after_state": after_patterns.get(pattern_id, {}).get("state", "absent"),
                "added_blockers": sorted(after_blockers - before_blockers),
                "removed_blockers": sorted(before_blockers - after_blockers),
                "paper_only": True,
                "live_order_allowed": False,
            }
        )
    return rows


def _patterns_by_id(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for state, key in (("robust", "robust_patterns"), ("research_only", "research_only_patterns"), ("anti", "anti_patterns")):
        rows = payload.get(key)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if isinstance(row, dict) and row.get("pattern_id"):
                enriched = dict(row)
                enriched["state"] = state
                out[str(row["pattern_id"])] = enriched
    return out


def _blockers(row: dict[str, Any]) -> list[str]:
    value = row.get("promotion_blockers")
    return [str(x) for x in value] if isinstance(value, list) else []


def _context_deltas(before: dict[str, Any], after: dict[str, Any]) -> dict[str, dict[str, float | int | None]]:
    before_context = _combined_context(before)
    after_context = _combined_context(after)
    out: dict[str, dict[str, float | int | None]] = {}
    for key in sorted(set(before_context) | set(after_context)):
        b = _as_number(before_context.get(key))
        a = _as_number(after_context.get(key))
        if b is None and a is None:
            continue
        out[key] = {"before": b, "after": a, "delta": None if b is None or a is None else a - b}
    return out


def _combined_context(payload: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in ("resolution_coverage_summary", "orderbook_context_summary", "weather_context_summary", "summary"):
        value = payload.get(key)
        if isinstance(value, dict):
            out.update(value)
    return out


def _markdown(payload: dict[str, Any]) -> str:
    before = payload["before"]
    after = payload["after"]
    lines = [
        "# Weather PM smoke comparison",
        "",
        f"- paper_only: {str(payload['paper_only']).lower()}",
        f"- live_order_allowed: {str(payload['live_order_allowed']).lower()}",
        f"- robust_patterns: {before['robust_patterns']} -> {after['robust_patterns']} ({_signed(payload['summary']['robust_patterns_delta'])})",
        f"- research_only_patterns: {before['research_only_patterns']} -> {after['research_only_patterns']} ({_signed(payload['summary']['research_only_patterns_delta'])})",
        "",
        "## Context deltas",
    ]
    for key, row in payload["context_deltas"].items():
        lines.append(f"- {key}: {row['before']} -> {row['after']} ({_signed(row['delta']) if row['delta'] is not None else 'n/a'})")
    lines.extend(["", "## Pattern blocker deltas"])
    for row in payload["patterns"]:
        removed = ", ".join(row["removed_blockers"]) or "none"
        added = ", ".join(row["added_blockers"]) or "none"
        lines.append(f"- {row['pattern_id']}: {row['before_state']} -> {row['after_state']}; removed blockers: {removed}; added blockers: {added}")
    return "\n".join(lines) + "\n"


def _load_object(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("smoke comparison input must be a JSON object")
    return payload


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _as_number(value: Any) -> float | int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _signed(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return f"+{value}" if value >= 0 else str(value)
