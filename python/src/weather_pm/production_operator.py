from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from weather_pm.orderbook_simulator import simulate_orderbook_fill
from weather_pm.paper_ledger import paper_ledger_refresh
from weather_pm.portfolio_risk import apply_portfolio_risk_to_candidates
from weather_pm.surface_inconsistency import detect_surface_inconsistencies
from weather_pm.threshold_watcher import build_threshold_watch_report

SCHEMA_VERSION = 1
DEFAULT_JSON_NAME = "weather_production_operator_report_latest.json"
DEFAULT_MD_NAME = "weather_production_operator_report_latest.md"


def build_production_weather_report(
    surface: dict[str, Any],
    *,
    paper_ledger: dict[str, Any] | None = None,
    backtest_report: dict[str, Any] | None = None,
    consensus_report: dict[str, Any] | None = None,
    live_mode_enabled: bool = False,
    observed_value: float | None = None,
    hours_to_resolution: float | None = 2.0,
    limit: int = 10,
) -> dict[str, Any]:
    if not isinstance(surface, dict):
        raise ValueError("production weather report requires a surface object")
    paper_ledger = _ledger_with_summary(paper_ledger or {"orders": []})
    candidates = _build_candidates(surface, observed_value=observed_value, hours_to_resolution=hours_to_resolution)
    candidates = apply_portfolio_risk_to_candidates(candidates)
    candidates = sorted(candidates, key=_candidate_sort_key)[: max(int(limit), 0)]
    for candidate in candidates:
        candidate["strict_next_action"] = _candidate_next_action(candidate)
        candidate["live_order_allowed"] = False

    source_confirmed = _surface_source_confirmed(surface)
    book_fresh = any((candidate.get("execution") or {}).get("top_ask") is not None for candidate in candidates)
    risk_caps_satisfied = all((candidate.get("portfolio_risk") or {}).get("cap_status") != "blocked" for candidate in candidates)
    readiness = build_live_readiness_checks(
        source_confirmed=source_confirmed,
        book_fresh=book_fresh,
        paper_ledger=paper_ledger,
        backtest_report=backtest_report,
        risk_caps_satisfied=risk_caps_satisfied,
        explicit_live_mode_enabled=live_mode_enabled,
    )
    layers = _production_layers(surface, candidates, paper_ledger, backtest_report, consensus_report)
    blockers = _blockers(candidates, readiness)
    summary = {
        "candidate_count": len(candidates),
        "implemented_layers": sum(1 for row in layers if row["status"] == "implemented"),
        "guarded_layers": sum(1 for row in layers if row["status"] == "guarded"),
        "missing_layers": sum(1 for row in layers if row["status"] == "missing"),
        "live_ready": readiness["ready"],
        "paper_only": True,
        "blocker_count": len(blockers),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "report_type": "polymarket_weather_production_operator",
        "summary": summary,
        "production_layers": layers,
        "top_current_candidates": candidates,
        "blockers": blockers,
        "strict_next_actions": _strict_next_actions(readiness, candidates),
        "live_readiness": readiness,
        "components": {
            "surface": _surface_component(surface),
            "threshold_watcher": build_threshold_watch_report(surface, hours_to_resolution=hours_to_resolution, observed_value=observed_value, limit=limit),
            "paper_ledger": paper_ledger.get("summary", {}),
            "backtest": (backtest_report or {}).get("summary", {}) if isinstance(backtest_report, dict) else {},
            "consensus": _consensus_summary(consensus_report, surface),
        },
        "artifacts": {},
    }


def build_live_readiness_checks(
    *,
    source_confirmed: bool,
    book_fresh: bool,
    paper_ledger: dict[str, Any] | None,
    backtest_report: dict[str, Any] | None,
    risk_caps_satisfied: bool,
    explicit_live_mode_enabled: bool,
) -> dict[str, Any]:
    ledger = _ledger_with_summary(paper_ledger or {"orders": []})
    ledger_summary = ledger.get("summary", {})
    paper_healthy = bool(ledger_summary.get("orders", 0) >= 1) and not any(
        str(order.get("operator_action")) == "RED_FLAG_RECHECK_SOURCE" or str(order.get("status")) == "cancelled"
        for order in ledger.get("orders", [])
        if isinstance(order, dict)
    )
    backtest_summary = (backtest_report or {}).get("summary", {}) if isinstance(backtest_report, dict) else {}
    backtest_available = bool(backtest_summary.get("replayed_trade_count", 0) > 0 or backtest_summary.get("input_trade_count", 0) > 0)
    checks = {
        "source_confirmed": {"pass": bool(source_confirmed), "required": True, "detail": "official source/station confirmed"},
        "book_fresh": {"pass": bool(book_fresh), "required": True, "detail": "orderbook/fill simulation available"},
        "paper_ledger_healthy": {"pass": paper_healthy, "required": True, "detail": "paper ledger exists and has no red source flags"},
        "backtest_replay_available": {"pass": backtest_available, "required": True, "detail": "historical replay/backtest artifact available"},
        "risk_caps_satisfied": {"pass": bool(risk_caps_satisfied), "required": True, "detail": "portfolio caps not blocking candidates"},
        "explicit_live_mode_enabled": {"pass": bool(explicit_live_mode_enabled), "required": True, "detail": "operator explicitly enabled live mode"},
    }
    blockers = [name for name, check in checks.items() if not check["pass"]]
    return {
        "ready": not blockers,
        "status": "ready_for_guarded_live_execution" if not blockers else "refuse_live_execution",
        "checks": checks,
        "blockers": blockers,
        "live_order_allowed": not blockers,
    }


def write_production_weather_report_artifacts(
    surface: dict[str, Any],
    *,
    output_dir: str | Path = "data/polymarket",
    paper_ledger: dict[str, Any] | None = None,
    backtest_report: dict[str, Any] | None = None,
    consensus_report: dict[str, Any] | None = None,
    live_mode_enabled: bool = False,
    observed_value: float | None = None,
    hours_to_resolution: float | None = 2.0,
    limit: int = 10,
) -> dict[str, Any]:
    report = build_production_weather_report(
        surface,
        paper_ledger=paper_ledger,
        backtest_report=backtest_report,
        consensus_report=consensus_report,
        live_mode_enabled=live_mode_enabled,
        observed_value=observed_value,
        hours_to_resolution=hours_to_resolution,
        limit=limit,
    )
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / DEFAULT_JSON_NAME
    md_path = output / DEFAULT_MD_NAME
    report["artifacts"] = {"json_path": str(json_path), "md_path": str(md_path), "generated_at": _utc_now()}
    json_path.write_text(json.dumps(report, indent=2, sort_keys=False), encoding="utf-8")
    md_path.write_text(render_production_weather_report_markdown(report), encoding="utf-8")
    return {"json_path": str(json_path), "md_path": str(md_path), "summary": report["summary"]}


def render_production_weather_report_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        "# Polymarket Weather Production Operator Report",
        "",
        f"Paper only: {summary.get('paper_only', True)} | Live ready: {summary.get('live_ready', False)} | Candidates: {summary.get('candidate_count', 0)}",
        "",
        "## Implemented vs Missing Production Layers",
        "",
        "| Layer | Status | Detail |",
        "|---|---|---|",
    ]
    for layer in report.get("production_layers", []):
        lines.append(f"| {_cell(layer.get('layer'))} | {_cell(layer.get('status'))} | {_cell(layer.get('detail'))} |")
    lines.extend(["", "## Top Current Candidates", "", "| Market | Side | Action | Source | Limit | Top Ask | Risk |", "|---|---|---|---|---:|---:|---|"])
    for row in report.get("top_current_candidates", []):
        execution = row.get("execution") if isinstance(row.get("execution"), dict) else {}
        risk = row.get("portfolio_risk") if isinstance(row.get("portfolio_risk"), dict) else {}
        lines.append(
            f"| {_cell(row.get('market_id'))} | {_cell(row.get('candidate_side'))} | {_cell(row.get('strict_next_action'))} | {_cell(row.get('source_status'))} | {_fmt(row.get('strict_limit'))} | {_fmt(execution.get('top_ask'))} | {_cell(risk.get('recommendation'))} |"
        )
    lines.extend(["", "## Blockers", ""])
    for blocker in report.get("blockers", []):
        lines.append(f"- {blocker}")
    lines.extend(["", "## Strict Next Actions", ""])
    for action in report.get("strict_next_actions", []):
        lines.append(f"- {action}")
    readiness = report.get("live_readiness", {})
    lines.extend(["", "## Guarded Live Readiness", "", f"Status: {readiness.get('status')}", ""])
    for name, check in (readiness.get("checks") or {}).items():
        mark = "PASS" if check.get("pass") else "FAIL"
        lines.append(f"- {name}: {mark} — {check.get('detail')}")
    lines.append("")
    return "\n".join(lines)


def load_optional_json(path: str | Path | None) -> dict[str, Any] | None:
    if not path:
        return None
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object at {path}")
    return payload


def _build_candidates(surface: dict[str, Any], *, observed_value: float | None, hours_to_resolution: float | None) -> list[dict[str, Any]]:
    markets = [market for market in surface.get("markets", []) if isinstance(market, dict)]
    inconsistencies = _inconsistencies(surface, markets)
    inconsistency_by_market = {str(row.get("market_id")): row for row in inconsistencies if row.get("market_id")}
    threshold_report = build_threshold_watch_report(surface, hours_to_resolution=hours_to_resolution, observed_value=observed_value, limit=max(len(markets), 1))
    threshold_by_market = {str(row.get("market_id")): row for row in threshold_report.get("threshold_watch", []) if isinstance(row, dict)}
    source = surface.get("source", {}) if isinstance(surface.get("source"), dict) else {}
    identity = surface.get("surface_identity", {}) if isinstance(surface.get("surface_identity"), dict) else {}
    candidates = []
    for market in markets:
        market_id = str(market.get("market_id") or market.get("id") or "")
        threshold_watch = threshold_by_market.get(market_id, {})
        inconsistency = inconsistency_by_market.get(market_id, {})
        side = str(threshold_watch.get("candidate_side") or inconsistency.get("candidate_side") or (market.get("account_consensus_hint") or {}).get("dominant_side") or "YES").upper()
        top_ask = _float((market.get("orderbook") or {}).get("best_ask"))
        strict_limit = round(min((top_ask if top_ask is not None else 0.99) + 0.02, 0.99), 4)
        orderbook = _simulation_orderbook(market.get("orderbook"), side=side)
        edge = 0.14 if threshold_watch else max(_float(inconsistency.get("severity")) or 0.05, 0.05)
        execution = simulate_orderbook_fill(orderbook, side=side, spend_usd=5.0, probability_edge=edge, strict_limit=strict_limit)
        candidate = {
            "market_id": market_id,
            "question": market.get("question"),
            "city": identity.get("city"),
            "date": identity.get("date"),
            "measurement_kind": identity.get("measurement_kind"),
            "unit": identity.get("unit"),
            "source_provider": source.get("provider"),
            "source_station_code": source.get("station_code"),
            "source_status": source.get("status"),
            "source_url": market.get("source_url") or source.get("source_url"),
            "source_direct": _surface_source_confirmed(surface),
            "candidate_side": side,
            "side": side,
            "strict_limit": strict_limit,
            "probability_edge": edge,
            "threshold": threshold_watch.get("threshold"),
            "forecast_value": observed_value if observed_value is not None else threshold_watch.get("source_value"),
            "sigma": 1.0,
            "error_width": 1.0,
            "primary_archetype": "threshold_harvester" if threshold_watch else "event_surface_grid_specialist",
            "correlated_surface_id": "|".join(str(identity.get(key) or "") for key in ("city", "date", "measurement_kind", "unit")),
            "execution": execution,
            "execution_blocker": execution.get("execution_blocker"),
            "threshold_watch": threshold_watch,
            "inconsistency_flags": [inconsistency] if inconsistency else [],
            "account_consensus": market.get("account_consensus_hint") or surface.get("account_consensus") or {},
        }
        candidates.append(candidate)
    return candidates


def _inconsistencies(surface: dict[str, Any], markets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from weather_pm.market_parser import parse_market_question

    exact_bins = []
    thresholds = []
    for market in markets:
        try:
            structure = parse_market_question(str(market.get("question") or ""))
        except ValueError:
            continue
        row = {
            "id": market.get("market_id"),
            "structure": structure,
            "yes_price": _float((market.get("orderbook") or {}).get("best_ask")) or 0.0,
        }
        if market.get("contract_kind") == "exact_bin" or structure.is_exact_bin:
            exact_bins.append(row)
        else:
            thresholds.append(row)
    return detect_surface_inconsistencies(exact_bins=exact_bins, thresholds=thresholds)


def _production_layers(surface: dict[str, Any], candidates: list[dict[str, Any]], paper_ledger: dict[str, Any], backtest_report: dict[str, Any] | None, consensus_report: dict[str, Any] | None) -> list[dict[str, str]]:
    return [
        {"layer": "source_first_event_surface", "status": "implemented", "detail": "surface source status: " + str((surface.get("source") or {}).get("status"))},
        {"layer": "cross_market_inconsistency_engine", "status": "implemented", "detail": "candidate inconsistency flags included"},
        {"layer": "orderbook_strict_limit_simulation", "status": "implemented", "detail": "strict-limit fill metrics included"},
        {"layer": "near_resolution_threshold_watcher", "status": "implemented", "detail": "threshold recommendations included"},
        {"layer": "continuous_consensus_tracker", "status": "implemented" if consensus_report or surface.get("account_consensus") else "missing", "detail": "account consensus summary available"},
        {"layer": "historical_replay_backtest", "status": "implemented" if backtest_report else "missing", "detail": "backtest/replay readiness gate"},
        {"layer": "strict_limit_paper_execution_ledger", "status": "implemented" if (paper_ledger.get("summary") or {}).get("orders", 0) >= 1 else "missing", "detail": "paper ledger health gate"},
        {"layer": "portfolio_sizing_risk_caps", "status": "implemented", "detail": "portfolio caps applied to candidates"},
        {"layer": "guarded_live_execution", "status": "guarded", "detail": "live execution refused unless all readiness checks pass"},
        {"layer": "real_money_live_execution", "status": "missing", "detail": "intentionally disabled until explicit operator approval"},
    ]


def _blockers(candidates: list[dict[str, Any]], readiness: dict[str, Any]) -> list[str]:
    blockers = [f"live_readiness:{name}" for name in readiness.get("blockers", [])]
    blockers.extend(f"candidate:{row.get('market_id')}:{row.get('execution_blocker')}" for row in candidates if row.get("execution_blocker"))
    return list(dict.fromkeys(blockers))


def _strict_next_actions(readiness: dict[str, Any], candidates: list[dict[str, Any]]) -> list[str]:
    actions = [
        "refresh profitable weather accounts and consensus signals",
        "confirm official source/station before any paper add",
        "simulate strict-limit fills from a fresh orderbook before placement",
        "place paper limits only within portfolio caps",
        "monitor paper ledger and postmortem every filled/settled order",
    ]
    if "explicit_live_mode_enabled" in readiness.get("blockers", []):
        actions.append("enable live mode only after explicit operator approval")
    if any(row.get("execution_blocker") for row in candidates):
        actions.append("do not chase moved prices; leave blocked rows watch-only")
    return actions


def _candidate_next_action(candidate: dict[str, Any]) -> str:
    if candidate.get("execution_blocker"):
        return "watch_only_until_fresh_book_or_lower_limit"
    risk = candidate.get("portfolio_risk") if isinstance(candidate.get("portfolio_risk"), dict) else {}
    if risk.get("approved_size_usdc", 0) > 0:
        return "paper_limit_only_after_source_recheck"
    return "avoid_or_wait_for_cap_capacity"


def _ledger_with_summary(ledger: dict[str, Any]) -> dict[str, Any]:
    try:
        return paper_ledger_refresh(ledger, refreshes={}, settlements={})
    except Exception:
        orders = [order for order in ledger.get("orders", []) if isinstance(order, dict)] if isinstance(ledger, dict) else []
        ledger = {"orders": orders}
        ledger["summary"] = {"orders": len(orders), "status_counts": dict(Counter(str(o.get("status")) for o in orders)), "paper_only": True, "live_order_allowed": False}
        return ledger


def _surface_source_confirmed(surface: dict[str, Any]) -> bool:
    status = str(((surface.get("source") or {}) if isinstance(surface.get("source"), dict) else {}).get("status") or "")
    return status in {"source_confirmed", "source_confirmed_fixture"}


def _surface_component(surface: dict[str, Any]) -> dict[str, Any]:
    return {
        "identity": surface.get("surface_identity", {}),
        "source": surface.get("source", {}),
        "market_count": len(surface.get("markets", [])) if isinstance(surface.get("markets"), list) else 0,
    }


def _consensus_summary(consensus_report: dict[str, Any] | None, surface: dict[str, Any]) -> dict[str, Any]:
    if isinstance(consensus_report, dict):
        return consensus_report.get("summary", consensus_report)
    return surface.get("account_consensus", {}) if isinstance(surface.get("account_consensus"), dict) else {}


def _simulation_orderbook(orderbook: Any, *, side: str) -> dict[str, Any]:
    if not isinstance(orderbook, dict):
        return {}
    ask = _float(orderbook.get("best_ask"))
    if ask is None:
        return orderbook
    return {side.upper(): {"asks": [{"price": ask, "size": 100.0}]}}


def _candidate_sort_key(candidate: dict[str, Any]) -> tuple[float, float]:
    risk = candidate.get("portfolio_risk") if isinstance(candidate.get("portfolio_risk"), dict) else {}
    return (-(float(risk.get("approved_size_usdc") or 0.0)), -(float(candidate.get("probability_edge") or 0.0)))


def _float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _cell(value: Any) -> str:
    return "" if value is None else str(value).replace("|", "\\|")


def _fmt(value: Any) -> str:
    parsed = _float(value)
    return "" if parsed is None else f"{parsed:.4f}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
