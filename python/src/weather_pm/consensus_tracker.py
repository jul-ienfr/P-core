from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from weather_pm.market_parser import parse_market_question

SCHEMA_VERSION = 1
DEFAULT_JSON_NAME = "weather_consensus_tracker_latest.json"
DEFAULT_CSV_NAME = "weather_consensus_tracker_latest.csv"
DEFAULT_MD_NAME = "weather_consensus_tracker_latest.md"
GENERIC_SURFACES = {"", "generic", "generic_city", "generic_city_history", "historical_city", "city_history"}


def build_weather_consensus_tracker(signals: Iterable[dict[str, Any]], *, top_handle_limit: int = 5) -> dict[str, Any]:
    grouped: dict[tuple[str, str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    malformed: list[dict[str, Any]] = []

    for index, raw_signal in enumerate(signals):
        if not isinstance(raw_signal, dict):
            malformed.append({"index": index, "reason": "signal_not_object", "title": None, "handle": None})
            continue
        normalized = _normalize_signal(raw_signal, index=index)
        if normalized.get("malformed_reason"):
            malformed.append(
                {
                    "index": index,
                    "reason": normalized["malformed_reason"],
                    "title": raw_signal.get("title") or raw_signal.get("question") or raw_signal.get("market_title"),
                    "handle": raw_signal.get("handle") or raw_signal.get("userName") or raw_signal.get("username"),
                }
            )
            continue
        grouped[_group_key(normalized)].append(normalized)

    clusters = [_build_cluster(key, rows, top_handle_limit=top_handle_limit) for key, rows in grouped.items()]
    clusters.sort(
        key=lambda cluster: (
            -float(cluster["consensus_score"]),
            str(cluster["key"]["city"]),
            str(cluster["key"]["date"]),
            str(cluster["key"]["measurement_kind"]),
            str(cluster["key"]["unit"]),
            str(cluster["key"]["surface"]),
        )
    )
    summary = {
        "cluster_count": len(clusters),
        "signal_count": sum(int(cluster["signal_count"]) for cluster in clusters),
        "unique_account_count": len({wallet for rows in grouped.values() for wallet in (row["account_id"] for row in rows)}),
        "malformed_signal_count": len(malformed),
        "true_multi_account_consensus_count": sum(1 for cluster in clusters if cluster["cluster_type"] == "true_multi_account_consensus"),
        "single_account_heavy_count": sum(1 for cluster in clusters if cluster["cluster_type"] == "single_account_heavy"),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "summary": summary,
        "clusters": clusters,
        "malformed_signals": malformed,
        "artifacts": {},
    }


def write_weather_consensus_artifacts(
    signals: Iterable[dict[str, Any]],
    *,
    output_dir: str | Path = "data/polymarket",
    top_handle_limit: int = 5,
) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    report = build_weather_consensus_tracker(signals, top_handle_limit=top_handle_limit)
    json_path = output_path / DEFAULT_JSON_NAME
    csv_path = output_path / DEFAULT_CSV_NAME
    md_path = output_path / DEFAULT_MD_NAME
    report["artifacts"] = {"json_path": str(json_path), "csv_path": str(csv_path), "md_path": str(md_path)}
    json_path.write_text(json.dumps(report, indent=2, sort_keys=False), encoding="utf-8")
    _write_clusters_csv(report["clusters"], csv_path)
    md_path.write_text(_clusters_markdown(report), encoding="utf-8")
    return {"json_path": str(json_path), "csv_path": str(csv_path), "md_path": str(md_path), "summary": report["summary"]}


def load_consensus_signals(path: str | Path) -> list[dict[str, Any]]:
    input_path = Path(path)
    if input_path.suffix.lower() == ".csv":
        with input_path.open(newline="", encoding="utf-8") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("signals", "trades", "positions", "activity"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    raise ValueError("consensus tracker input must be a JSON list/object with signals or a CSV file")


def _normalize_signal(raw: dict[str, Any], *, index: int) -> dict[str, Any]:
    title = str(raw.get("title") or raw.get("question") or raw.get("market_title") or "").strip()
    if not title:
        return {"malformed_reason": "missing_title"}
    try:
        structure = parse_market_question(title)
    except ValueError:
        return {"malformed_reason": "unsupported_title"}
    side = _normalize_side(raw.get("side") or raw.get("outcome") or raw.get("position_side"))
    handle = str(raw.get("handle") or raw.get("userName") or raw.get("username") or raw.get("account") or raw.get("wallet") or f"account_{index}")
    wallet = str(raw.get("wallet") or raw.get("proxyWallet") or raw.get("account_id") or handle)
    surface = str(raw.get("surface") or raw.get("station_code") or raw.get("source_station_code") or raw.get("source") or "generic_city_history").strip() or "generic_city_history"
    return {
        "title": title,
        "city": str(structure.city),
        "date": str(structure.date_local or raw.get("date") or "unknown"),
        "measurement_kind": str(structure.measurement_kind),
        "unit": str(structure.unit).lower(),
        "surface": surface,
        "temperature": structure.target_value if structure.target_value is not None else structure.range_low,
        "side": side,
        "handle": handle,
        "account_id": wallet,
        "active_value_usdc": _to_float(raw.get("active_value_usdc") or raw.get("active_value") or raw.get("position_value_usdc") or raw.get("notional_usdc")),
        "recent_trade_usdc": _to_float(raw.get("recent_trade_usdc") or raw.get("trade_usdc") or raw.get("recent_volume_usdc")),
        "signal_kind": str(raw.get("signal_kind") or raw.get("kind") or "").lower(),
    }


def _group_key(row: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (row["city"], row["date"], row["measurement_kind"], row["unit"], row["surface"])


def _build_cluster(key: tuple[str, str, str, str, str], rows: list[dict[str, Any]], *, top_handle_limit: int) -> dict[str, Any]:
    city, date, measurement_kind, unit, surface = key
    account_ids = {str(row["account_id"]) for row in rows}
    active_value = round(sum(float(row["active_value_usdc"]) for row in rows), 6)
    recent_trade = round(sum(float(row["recent_trade_usdc"]) for row in rows), 6)
    side_totals: Counter[str] = Counter()
    temp_counts: Counter[float] = Counter()
    handle_value: Counter[str] = Counter()
    for row in rows:
        side_totals[str(row["side"])] += float(row["active_value_usdc"]) + float(row["recent_trade_usdc"])
        if row.get("temperature") is not None:
            temp_counts[float(row["temperature"])] += 1
        handle_value[str(row["handle"])] += float(row["active_value_usdc"]) + float(row["recent_trade_usdc"])
    dominant_side = _dominant(side_totals, default="UNKNOWN")
    weights = _weight_components(rows, surface=surface)
    score = round(
        len(account_ids) * 10.0
        + len(rows) * 2.0
        + active_value * 0.01
        + recent_trade * 0.05
        + weights["recent_same_surface"]
        + weights["generic_historical_city"],
        6,
    )
    return {
        "key": {"city": city, "date": date, "measurement_kind": measurement_kind, "unit": unit, "surface": surface},
        "unique_account_count": len(account_ids),
        "signal_count": len(rows),
        "active_value_usdc": active_value,
        "recent_trade_usdc": recent_trade,
        "dominant_side": dominant_side,
        "dominant_temperatures": [temperature for temperature, _ in temp_counts.most_common(3)],
        "top_handles": [handle for handle, _ in handle_value.most_common(top_handle_limit)],
        "cluster_type": _cluster_type(len(account_ids), len(rows), active_value, handle_value),
        "consensus_score": score,
        "weight_components": weights,
    }


def _cluster_type(unique_accounts: int, signal_count: int, active_value: float, handle_value: Counter[str]) -> str:
    if unique_accounts >= 2:
        return "true_multi_account_consensus"
    if signal_count >= 2 or active_value >= 250 or (handle_value and handle_value.most_common(1)[0][1] >= 250):
        return "single_account_heavy"
    return "weak_single_account_signal"


def _weight_components(rows: list[dict[str, Any]], *, surface: str) -> dict[str, float]:
    generic = surface.strip().lower() in GENERIC_SURFACES
    recent_same_surface = 0.0
    generic_historical_city = 0.0
    for row in rows:
        recent_trade = float(row["recent_trade_usdc"])
        active_value = float(row["active_value_usdc"])
        signal_kind = str(row.get("signal_kind") or "")
        if not generic and (recent_trade > 0 or signal_kind in {"recent", "recent_trade", "position"}):
            recent_same_surface += 20.0 + recent_trade * 0.5 + active_value * 0.02
        elif generic or signal_kind in {"historical", "historical_city"}:
            generic_historical_city += 3.0 + active_value * 0.001
    return {"recent_same_surface": round(recent_same_surface, 6), "generic_historical_city": round(generic_historical_city, 6)}


def _write_clusters_csv(clusters: list[dict[str, Any]], path: Path) -> None:
    fieldnames = [
        "city",
        "date",
        "measurement_kind",
        "unit",
        "surface",
        "unique_account_count",
        "signal_count",
        "active_value_usdc",
        "recent_trade_usdc",
        "dominant_side",
        "dominant_temperatures",
        "top_handles",
        "cluster_type",
        "consensus_score",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for cluster in clusters:
            key = cluster["key"]
            writer.writerow(
                {
                    **key,
                    "unique_account_count": cluster["unique_account_count"],
                    "signal_count": cluster["signal_count"],
                    "active_value_usdc": cluster["active_value_usdc"],
                    "recent_trade_usdc": cluster["recent_trade_usdc"],
                    "dominant_side": cluster["dominant_side"],
                    "dominant_temperatures": ";".join(str(value) for value in cluster["dominant_temperatures"]),
                    "top_handles": ";".join(cluster["top_handles"]),
                    "cluster_type": cluster["cluster_type"],
                    "consensus_score": cluster["consensus_score"],
                }
            )


def _clusters_markdown(report: dict[str, Any]) -> str:
    lines = ["# Weather Consensus Tracker", "", f"Schema version: {report['schema_version']}", ""]
    summary = report["summary"]
    lines.append(
        f"Clusters: {summary['cluster_count']} | Signals: {summary['signal_count']} | Malformed: {summary['malformed_signal_count']}"
    )
    lines.extend(["", "| City | Date | Surface | Accounts | Signals | Side | Temps | Type | Score |", "| --- | --- | --- | ---: | ---: | --- | --- | --- | ---: |"])
    for cluster in report["clusters"]:
        key = cluster["key"]
        lines.append(
            "| {city} | {date} | {surface} | {accounts} | {signals} | {side} | {temps} | {ctype} | {score} |".format(
                city=key["city"],
                date=key["date"],
                surface=key["surface"],
                accounts=cluster["unique_account_count"],
                signals=cluster["signal_count"],
                side=cluster["dominant_side"],
                temps=", ".join(str(value) for value in cluster["dominant_temperatures"]),
                ctype=cluster["cluster_type"],
                score=cluster["consensus_score"],
            )
        )
    lines.append("")
    return "\n".join(lines)


def _normalize_side(value: Any) -> str:
    side = str(value or "UNKNOWN").strip().upper()
    if side in {"Y", "YES", "BUY_YES", "LONG_YES"}:
        return "YES"
    if side in {"N", "NO", "BUY_NO", "LONG_NO"}:
        return "NO"
    return side or "UNKNOWN"


def _dominant(counter: Counter[str], *, default: str) -> str:
    if not counter:
        return default
    return sorted(counter.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _to_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
