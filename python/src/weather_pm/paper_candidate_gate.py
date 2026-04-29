from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _list(payload: dict[str, Any], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [dict(row) for row in value if isinstance(row, dict)]
    return []


def _market_id(row: dict[str, Any]) -> str:
    return str(row.get("market_id") or row.get("id") or row.get("condition_id") or "")


def _matches(pattern: dict[str, Any], market: dict[str, Any]) -> bool:
    for key in ("market_type", "city", "side"):
        pv = pattern.get(key)
        mv = market.get(key)
        if pv not in (None, "", "any", "unknown") and mv not in (None, "") and str(pv).lower() != str(mv).lower():
            return False
    return True


def _by_market(payload: dict[str, Any], keys: tuple[str, ...]) -> dict[str, dict[str, Any]]:
    return {_market_id(row): row for row in _list(payload, keys) if _market_id(row)}


def _book_capturable(book: dict[str, Any] | None) -> bool:
    if not book:
        return False
    if book.get("orderbook_context_available") is False:
        return False
    spread = book.get("spread")
    if spread is None and book.get("best_bid") is not None and book.get("best_ask") is not None:
        spread = float(book["best_ask"]) - float(book["best_bid"])
    try:
        return spread is not None and float(spread) <= 0.08
    except (TypeError, ValueError):
        return False


def _weather_available(ctx: dict[str, Any] | None) -> bool:
    if not ctx:
        return False
    return ctx.get("weather_context_available") is True or ctx.get("available") is True


def build_winner_pattern_paper_candidates(
    winner_patterns: dict[str, Any],
    current_markets: dict[str, Any],
    current_orderbooks: dict[str, Any],
    current_weather_context: dict[str, Any],
) -> dict[str, Any]:
    robust = _list(winner_patterns, ("robust_patterns",))
    anti = _list(winner_patterns, ("anti_patterns",))
    research = _list(winner_patterns, ("research_only_patterns",))
    markets = _list(current_markets, ("markets", "current_markets", "rows"))
    books = _by_market(current_orderbooks, ("orderbooks", "books", "markets", "snapshots"))
    weather = _by_market(current_weather_context, ("contexts", "examples", "markets", "weather_context"))
    considered: list[dict[str, Any]] = []
    paper_candidates: list[dict[str, Any]] = []
    watch_only: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    research_only_matches = 0

    for market in markets:
        mid = _market_id(market)
        anti_match = next((p for p in anti if p.get("block_live_radar") is True and _matches(p, market)), None)
        robust_match = next((p for p in robust if _matches(p, market)), None)
        research_match = next((p for p in research if _matches(p, market)), None)
        matched_pattern = robust_match or research_match
        book = books.get(mid)
        ctx = weather.get(mid)
        base = {
            "market_id": mid,
            "question": market.get("question") or market.get("title"),
            "matched_pattern_id": matched_pattern.get("pattern_id") if matched_pattern else None,
            "matched_pattern_status": matched_pattern.get("pattern_status") if matched_pattern else None,
            "paper_only": True,
            "live_order_allowed": False,
        }
        if anti_match is not None:
            row = {**base, "decision": "blocked", "reason": "anti_pattern_conflict", "conflicting_pattern_id": anti_match.get("pattern_id"), "paper_probe_authorized": False}
            blocked.append(row)
        elif robust_match is None:
            if research_match is not None:
                research_only_matches += 1
                row = {**base, "decision": "watch_only", "reason": "research_only_pattern_match", "paper_probe_authorized": False}
            else:
                row = {**base, "decision": "watch_only", "reason": "no_robust_pattern_match", "paper_probe_authorized": False}
            watch_only.append(row)
        elif not book:
            row = {**base, "decision": "watch_only", "reason": "missing_current_orderbook", "paper_probe_authorized": False}
            watch_only.append(row)
        elif not _book_capturable(book):
            row = {**base, "decision": "watch_only", "reason": "current_orderbook_not_capturable", "paper_probe_authorized": False}
            watch_only.append(row)
        elif not _weather_available(ctx):
            row = {**base, "decision": "watch_only", "reason": "missing_current_weather_context", "paper_probe_authorized": False}
            watch_only.append(row)
        else:
            row = {**base, "decision": "paper_candidate", "reason": "robust_pattern_orderbook_weather_aligned", "paper_probe_authorized": True, "paper_notional_cap_usdc": 5.0}
            paper_candidates.append(row)
        considered.append(row)

    return {
        "paper_only": True,
        "live_order_allowed": False,
        "summary": {
            "considered_markets": len(considered),
            "paper_candidates": len(paper_candidates),
            "watch_only": len(watch_only),
            "blocked": len(blocked),
            "research_only_matches": research_only_matches,
        },
        "paper_candidates": paper_candidates,
        "watch_only": watch_only,
        "blocked": blocked,
        "considered_markets": considered,
    }


def render_paper_candidates_markdown(payload: dict[str, Any]) -> str:
    lines = ["# Winner Pattern Paper Candidates", "", "## Safety", "", "- paper_only: true", "- live_order_allowed: false", "", "## Considered markets", ""]
    for row in payload.get("considered_markets", []):
        if isinstance(row, dict):
            lines.append(f"- {row.get('market_id')}: {row.get('decision')} ({row.get('reason')})")
    return "\n".join(lines) + "\n"


def write_winner_pattern_paper_candidates(
    winner_patterns_json: str | Path,
    current_markets_json: str | Path,
    current_orderbooks_json: str | Path,
    current_weather_context_json: str | Path,
    output_json: str | Path,
    *,
    output_md: str | Path | None = None,
) -> dict[str, Any]:
    payload = build_winner_pattern_paper_candidates(
        json.loads(Path(winner_patterns_json).read_text(encoding="utf-8")),
        json.loads(Path(current_markets_json).read_text(encoding="utf-8")),
        json.loads(Path(current_orderbooks_json).read_text(encoding="utf-8")),
        json.loads(Path(current_weather_context_json).read_text(encoding="utf-8")),
    )
    out = Path(output_json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    if output_md:
        md = Path(output_md)
        md.parent.mkdir(parents=True, exist_ok=True)
        md.write_text(render_paper_candidates_markdown(payload), encoding="utf-8")
    return {
        "paper_only": True,
        "live_order_allowed": False,
        "considered_markets": len(payload["considered_markets"]),
        "paper_candidates": len(payload["paper_candidates"]),
        "watch_only": len(payload["watch_only"]),
        "blocked": len(payload["blocked"]),
        "output_json": str(out),
        "output_md": str(output_md) if output_md else None,
    }
