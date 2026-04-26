from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def build_winning_patterns_operator_report(
    *,
    classified_summary: dict[str, Any],
    continued_summary: dict[str, Any],
    strategy_patterns: dict[str, Any],
    strategy_report: dict[str, Any],
    future_consensus: dict[str, Any],
    orderbook_bridge: dict[str, Any],
    limit: int = 10,
) -> dict[str, Any]:
    strategy_summary = strategy_report.get("summary", {}) if isinstance(strategy_report.get("summary"), dict) else {}
    summary = {
        "positive_weather_accounts": int(continued_summary.get("total_profitable_weather_pnl_accounts") or 0),
        "weather_heavy_or_mixed_accounts": int(
            classified_summary.get("weather_heavy_or_specialist_count")
            or classified_summary.get("weather_heavy_count")
            or 0
        ),
        "classified_counts": _dict_ints(classified_summary.get("classification_counts")),
        "top80_accounts_analyzed": int(strategy_summary.get("account_count") or 0),
    }
    report = {
        "summary": summary,
        "archetype_counts": _dict_ints(strategy_summary.get("archetype_counts")),
        "weather_title_kind_counts": _dict_ints(strategy_patterns.get("kind_counts")),
        "top_cities": _top_cities(strategy_patterns.get("top_cities"), limit=limit),
        "rules": _rules(),
        "consensus_surfaces": _consensus_surfaces(future_consensus.get("rows"), limit=limit),
        "orderbook_candidates": _orderbook_candidates(future_consensus.get("rows"), orderbook_bridge.get("rows"), limit=limit),
        "implementation_priorities": [str(item) for item in strategy_summary.get("implementation_priorities") or []],
    }
    report["discord_brief"] = _discord_brief(report)
    return report


def write_winning_patterns_operator_report(
    *,
    classified_summary_json: str | Path,
    continued_summary_json: str | Path,
    strategy_patterns_json: str | Path,
    strategy_report_json: str | Path,
    future_consensus_json: str | Path,
    orderbook_bridge_json: str | Path,
    output_json: str | Path | None = None,
    output_md: str | Path | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    report = build_winning_patterns_operator_report(
        classified_summary=_load_json_object(classified_summary_json),
        continued_summary=_load_json_object(continued_summary_json),
        strategy_patterns=_load_json_object(strategy_patterns_json),
        strategy_report=_load_json_object(strategy_report_json),
        future_consensus=_load_json_object(future_consensus_json),
        orderbook_bridge=_load_json_object(orderbook_bridge_json),
        limit=limit,
    )
    artifacts = {
        "classified_summary_json": str(classified_summary_json),
        "continued_summary_json": str(continued_summary_json),
        "strategy_patterns_json": str(strategy_patterns_json),
        "strategy_report_json": str(strategy_report_json),
        "future_consensus_json": str(future_consensus_json),
        "orderbook_bridge_json": str(orderbook_bridge_json),
    }
    if output_json:
        output_path = Path(output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        artifacts["output_json"] = str(output_path)
        report["artifacts"] = artifacts
        output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if output_md:
        output_path = Path(output_md)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        artifacts["output_md"] = str(output_path)
        report["artifacts"] = artifacts
        output_path.write_text(markdown_winning_patterns_operator_report(report), encoding="utf-8")
        if output_json:
            Path(output_json).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    report["artifacts"] = artifacts
    return report


def compact_winning_patterns_operator_report(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "summary": report.get("summary", {}),
        "top_archetype": _top_count_key(report.get("archetype_counts")),
        "consensus_surfaces": list(report.get("consensus_surfaces") or [])[:5],
        "orderbook_candidates": list(report.get("orderbook_candidates") or [])[:5],
        "discord_brief": report.get("discord_brief"),
        "artifacts": report.get("artifacts", {}),
    }


def markdown_winning_patterns_operator_report(report: dict[str, Any]) -> str:
    lines = ["# Polymarket météo — patterns gagnants", ""]
    summary = report.get("summary", {})
    lines.append("## Synthèse")
    lines.append(f"- Comptes météo positifs: {summary.get('positive_weather_accounts', 0):,}")
    lines.append(f"- Weather-heavy/mixed: {summary.get('weather_heavy_or_mixed_accounts', 0):,}")
    lines.append(f"- Top80 analysés: {summary.get('top80_accounts_analyzed', 0):,}")
    lines.append("")
    lines.append("## Règles opérateur")
    for rule in report.get("rules") or []:
        lines.append(f"- **{rule.get('id')} {rule.get('name')}** — {rule.get('operator_rule')}")
    lines.append("")
    lines.append("## Surfaces consensus prioritaires")
    lines.append("| surface | side | comptes | signaux | statut |")
    lines.append("|---|---:|---:|---:|---|")
    for row in report.get("consensus_surfaces") or []:
        lines.append(
            f"| {row.get('city')} {row.get('date')} {row.get('top_temp')} | {row.get('side')} | {row.get('accounts')} | {row.get('signals')} | {row.get('operator_status')} |"
        )
    lines.append("")
    lines.append("## Candidats orderbook")
    lines.append("| surface | label | side | ask | source | tradability |")
    lines.append("|---|---:|---:|---:|---|---|")
    for row in report.get("orderbook_candidates") or []:
        lines.append(
            f"| {row.get('city')} {row.get('date')} | {row.get('label')} | {row.get('side')} | {row.get('target_ask')} | {row.get('source_status')} | {row.get('tradability')} |"
        )
    lines.append("")
    lines.append("## Brief")
    lines.append(str(report.get("discord_brief") or ""))
    return "\n".join(lines) + "\n"


def _rules() -> list[dict[str, str]]:
    return [
        {"id": "R1", "name": "surface complète", "operator_rule": "Group all markets by city/date/unit before scoring isolated bins."},
        {"id": "R2", "name": "side par source", "operator_rule": "Choose YES/NO from the official settlement source, not from trader consensus alone."},
        {"id": "R3", "name": "incohérences voisines", "operator_rule": "Prioritize thresholds/bins whose prices contradict neighboring bins or the implied temperature distribution."},
        {"id": "R4", "name": "consensus = carte", "operator_rule": "Use profitable-account activity to select surfaces to inspect; require source and book validation before paper/live."},
        {"id": "R5", "name": "strict limit", "operator_rule": "Enter only at strict limit when spread/slippage keep positive net edge."},
        {"id": "R6", "name": "caps portefeuille", "operator_rule": "Prefer many tiny independent edges over one large conviction; cap by city/date/surface."},
        {"id": "R7", "name": "proxy séparé", "operator_rule": "Treat forecast proxies as filters only; official source pending means watch/paper-only at most."},
    ]


def _consensus_surfaces(rows: Any, *, limit: int) -> list[dict[str, Any]]:
    clean = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        clean.append(
            {
                "city": row.get("city"),
                "date": row.get("date"),
                "side": row.get("side"),
                "top_temp": row.get("top_temp"),
                "accounts": _int_or_none(row.get("accounts")),
                "signals": _int_or_none(row.get("signals")),
                "side_share": _float_or_none(row.get("side_share")),
                "forecast_max_c": _float_or_none(row.get("forecast_max_c") if row.get("forecast_max_c") is not None else row.get("forecast_max_proxy")),
                "source_verdict": row.get("source_verdict_future") or row.get("source_verdict"),
                "action_score": _float_or_none(row.get("action_score") or row.get("confidence_score")),
                "operator_status": _surface_status(row),
            }
        )
    return sorted(clean, key=lambda item: item.get("action_score") or 0.0, reverse=True)[: max(int(limit), 0)]


def _orderbook_candidates(future_rows: Any, bridge_rows: Any, *, limit: int) -> list[dict[str, Any]]:
    future_by_surface: dict[tuple[Any, Any], dict[str, Any]] = {}
    for row in future_rows or []:
        if isinstance(row, dict):
            key = (row.get("city"), row.get("date"))
            current = future_by_surface.get(key)
            if current is None or (_float_or_none(row.get("action_score")) or 0.0) > (_float_or_none(current.get("action_score")) or 0.0):
                future_by_surface[key] = row
    candidates = []
    for row in bridge_rows or []:
        if not isinstance(row, dict):
            continue
        future = future_by_surface.get((row.get("city"), row.get("date")))
        if future is None:
            continue
        side = str(future.get("side") or "")
        target_market = row.get("target_market") if isinstance(row.get("target_market"), dict) else {}
        target_ask = _float_or_none(row.get("no_best_ask") if side == "NO" else row.get("yes_best_ask"))
        if target_ask is None:
            target_ask = _float_or_none(target_market.get("side_best_ask_est") or target_market.get("side_price"))
        avg20 = _float_or_none(row.get("no_20_avg") if side == "NO" else row.get("yes_20_avg"))
        volume = _float_or_none(row.get("volume") or target_market.get("volume") or row.get("event_volume"))
        consensus = _float_or_none(row.get("consensus_score") or row.get("confidence_score")) or 0.0
        combined = consensus + (_float_or_none(future.get("action_score")) or 0.0) + ((volume or 0.0) / 1000.0)
        source_status = row.get("source_status") or ("proxy_aligned" if row.get("source_verdict_future") or row.get("source_verdict") else "source_missing")
        tradability = row.get("tradability") or ("ok" if target_ask is not None and target_ask < 0.995 else "extreme_or_missing")
        candidates.append(
            {
                "city": row.get("city"),
                "date": row.get("date"),
                "label": row.get("label") or row.get("top_temp"),
                "market_id": target_market.get("id"),
                "side": side,
                "target_ask": target_ask,
                "target_avg20": avg20,
                "source_status": source_status,
                "tradability": tradability,
                "accounts": _int_or_none(row.get("unique_accounts") or row.get("accounts")),
                "signals": _int_or_none(row.get("signal_count") or row.get("signals")),
                "volume": volume,
                "combined_score": round(combined, 3),
                "operator_note": row.get("operator_note"),
            }
        )
    return sorted(candidates, key=lambda item: item.get("combined_score") or 0.0, reverse=True)[: max(int(limit), 0)]


def _surface_status(row: dict[str, Any]) -> str:
    if row.get("source_verdict_future") or row.get("source_verdict"):
        return "source_proxy_aligned_needs_official_check"
    return "watch_source_missing"


def _discord_brief(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    surfaces = report.get("consensus_surfaces") or []
    top = surfaces[0] if surfaces else {}
    return (
        "Météo patterns gagnants: "
        f"{summary.get('weather_heavy_or_mixed_accounts', 0)} comptes weather-heavy/mixed sur "
        f"{summary.get('positive_weather_accounts', 0)} positifs. "
        "Pattern dominant: surface ville/date complète + source officielle + strict-limit. "
        f"Top surface: {top.get('city', 'n/a')} {top.get('date', '')} {top.get('side', '')} {top.get('top_temp', '')}."
    )


def _top_cities(value: Any, *, limit: int) -> list[dict[str, Any]]:
    result = []
    for item in value or []:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            result.append({"city": item[0], "count": _int_or_none(item[1])})
        elif isinstance(item, dict):
            result.append({"city": item.get("city"), "count": _int_or_none(item.get("count"))})
    return result[: max(int(limit), 0)]


def _load_json_object(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _dict_ints(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {str(k): int(v or 0) for k, v in value.items()}


def _top_count_key(value: Any) -> str | None:
    counts = _dict_ints(value)
    return max(counts, key=counts.get) if counts else None


def _int_or_none(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return round(float(value), 6)
    except (TypeError, ValueError):
        return None
