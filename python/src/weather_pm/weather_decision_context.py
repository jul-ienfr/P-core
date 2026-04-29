from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from weather_pm.market_parser import parse_market_question


def enrich_decision_weather_context(
    decision_dataset_payload: dict[str, Any],
    forecast_snapshots_payload: dict[str, Any],
    resolution_sources_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    examples = _rows_from_payload(decision_dataset_payload, "examples")
    forecasts = _forecast_rows_from_payload(forecast_snapshots_payload)
    resolutions = _rows_from_payload(resolution_sources_payload or {}, "resolutions")
    enriched = [_enrich_row(row, forecasts, resolutions) for row in examples]
    with_context = sum(1 for row in enriched if row.get("weather_context_available") is True)
    summary = {
        "paper_only": True,
        "live_order_allowed": False,
        "examples": len(enriched),
        "with_weather_context": with_context,
        "missing_weather_context": len(enriched) - with_context,
        "decision_context_leakage_allowed": False,
    }
    return {"paper_only": True, "live_order_allowed": False, "summary": summary, "examples": enriched}


def write_decision_weather_context(
    decision_dataset_json: str | Path,
    forecast_snapshots_json: str | Path,
    output_json: str | Path,
    *,
    resolution_sources_json: str | Path | None = None,
) -> dict[str, Any]:
    decisions = _load_object(decision_dataset_json, "decision dataset JSON")
    forecasts = _load_object(forecast_snapshots_json, "forecast snapshots JSON")
    resolutions = _load_object(resolution_sources_json, "resolution sources JSON") if resolution_sources_json else None
    artifact = enrich_decision_weather_context(decisions, forecasts, resolutions)
    output_path = Path(output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")
    return dict(artifact["summary"])


def _enrich_row(row: dict[str, Any], forecasts: list[dict[str, Any]], resolutions: list[dict[str, Any]]) -> dict[str, Any]:
    row = _with_question_surface(row)
    decision_ts = _parse_timestamp(row.get("timestamp") or row.get("timestamp_bucket") or row.get("active_timestamp"))
    forecast = _select_forecast(row, forecasts, decision_ts)
    resolution = _select_resolution(row, resolutions)
    base = dict(row)
    if forecast is None:
        return {
            **base,
            **_empty_context("no_forecast_at_or_before_decision"),
            **_resolution_fields(resolution, decision_ts),
        }
    forecast_ts = _parse_timestamp(_forecast_timestamp(forecast))
    forecast_value = _forecast_value(forecast)
    forecast_age = _forecast_age_minutes(forecast, decision_ts, forecast_ts)
    threshold = _to_float(row.get("threshold") if row.get("threshold") is not None else forecast.get("threshold"))
    bin_center = _to_float(row.get("bin_center") if row.get("bin_center") is not None else forecast.get("bin_center"))
    official_available = bool(forecast.get("official_source_available") or (resolution or {}).get("official_source_available"))
    derived_fields = _derived_market_fields(row, threshold, bin_center)
    threshold = _to_float(derived_fields.get("threshold"))
    bin_center = _to_float(derived_fields.get("bin_center"))
    return {
        **base,
        **derived_fields,
        "decision_context_leakage_allowed": False,
        "resolution_source": (resolution or {}).get("resolution_source") or forecast.get("resolution_source"),
        "station_id": (resolution or {}).get("station_id") or forecast.get("station_id") or forecast.get("station_code"),
        "station_name": (resolution or {}).get("station_name") or forecast.get("station_name"),
        "forecast_timestamp": _decision_forecast_timestamp(forecast, decision_ts, forecast_ts, forecast_age),
        "forecast_value": forecast_value,
        "forecast_value_at_decision": forecast_value,
        "forecast_age_minutes": forecast_age,
        "forecast_source": forecast.get("source") or forecast.get("forecast_source"),
        "distance_to_threshold": _rounded_delta(forecast_value, threshold),
        "distance_to_bin_center": _rounded_delta(forecast_value, bin_center),
        "official_source_available": official_available,
        "weather_context_available": True,
        "missing_reason": None,
        "paper_only": True,
        "live_order_allowed": False,
        **_resolution_fields(resolution, decision_ts),
    }


def _empty_context(reason: str) -> dict[str, Any]:
    return {
        "decision_context_leakage_allowed": False,
        "resolution_source": None,
        "station_id": None,
        "station_name": None,
        "forecast_timestamp": None,
        "forecast_value": None,
        "forecast_value_at_decision": None,
        "forecast_age_minutes": None,
        "distance_to_threshold": None,
        "distance_to_bin_center": None,
        "official_source_available": False,
        "weather_context_available": False,
        "missing_reason": reason,
        "paper_only": True,
        "live_order_allowed": False,
    }


def _resolution_fields(resolution: dict[str, Any] | None, decision_ts: datetime | None = None) -> dict[str, Any]:
    resolution = resolution or {}
    resolution_timestamp = _resolution_timestamp(resolution)
    resolution_ts = _parse_timestamp(resolution_timestamp)
    return {
        "observation_value": _to_float(resolution.get("observation_value") if resolution.get("observation_value") is not None else resolution.get("observed_value")),
        "observation_timestamp": resolution.get("observation_timestamp") or resolution.get("observed_at") or resolution.get("timestamp"),
        "resolution_value": _to_float(resolution.get("resolution_value") if resolution.get("resolution_value") is not None else resolution.get("value")),
        "resolution_timestamp": _format_timestamp(resolution_ts) or resolution_timestamp,
        "time_to_resolution_minutes": _minutes_between(decision_ts, resolution_ts),
    }


def _resolution_timestamp(resolution: dict[str, Any]) -> Any:
    for key in ("resolution_timestamp", "resolved_at", "resolvedAt", "updated_at", "updatedAt", "closed_at", "closedAt", "closed_time", "endDate", "end_date"):
        if resolution.get(key):
            return resolution.get(key)
    return None


def _select_forecast(row: dict[str, Any], forecasts: list[dict[str, Any]], decision_ts: datetime | None) -> dict[str, Any] | None:
    candidates: list[tuple[datetime, int, dict[str, Any]]] = []
    for index, forecast in enumerate(forecasts):
        if not _matches_surface(row, forecast):
            continue
        forecast_ts = _parse_timestamp(_forecast_timestamp(forecast))
        if forecast_ts is not None and decision_ts is not None and forecast_ts > decision_ts:
            continue
        candidates.append((forecast_ts or datetime.min.replace(tzinfo=timezone.utc), index, forecast))
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item[0], item[1]))[2]


def _select_resolution(row: dict[str, Any], resolutions: list[dict[str, Any]]) -> dict[str, Any] | None:
    for resolution in resolutions:
        if _matches_surface(row, resolution):
            return resolution
    return None


def _matches_surface(row: dict[str, Any], other: dict[str, Any]) -> bool:
    row_keys = _surface_keys(row)
    other_keys = _surface_keys(other)
    if row_keys and other_keys and row_keys.intersection(other_keys):
        return True
    row_city = _norm(row.get("city"))
    other_city = _norm(other.get("city"))
    if row_city and row_city == other_city and other.get("date") is None and other.get("resolution_date") is None:
        return True
    if row_city and row_city == other_city and _is_broad_city_forecast(other):
        return True
    return (
        row_city == other_city
        and str(row.get("date") or "") == str(other.get("date") or other.get("resolution_date") or "")
        and _norm(row.get("market_type")) == _norm(other.get("market_type") or other.get("weather_market_type") or other.get("type"))
    )


def _is_broad_city_forecast(row: dict[str, Any]) -> bool:
    return bool(row.get("sparse_key") and row.get("city") and not str(row.get("sparse_key")).strip().isdigit())


def _surface_keys(row: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for key in ("primary_key", "matched_key", "market_id", "marketId", "id", "condition_id", "conditionId", "slug", "sparse_key"):
        value = row.get(key)
        if value is not None and str(value).strip():
            keys.add(str(value).strip().lower())
    return keys


def _forecast_timestamp(row: dict[str, Any]) -> Any:
    for key in ("forecast_timestamp", "timestamp", "snapshot_timestamp", "created_at", "createdAt"):
        if row.get(key):
            return row.get(key)
    return None


def _with_question_surface(row: dict[str, Any]) -> dict[str, Any]:
    question = str(row.get("question") or row.get("title") or "")
    if not question:
        return dict(row)
    out = dict(row)
    parsed = _parse_market_structure(question)
    if not out.get("city"):
        city = getattr(parsed, "city", None) or _city_from_question(question)
        if city:
            out["city"] = city
    if not out.get("date"):
        date = getattr(parsed, "date_local", None) or _date_from_question(question)
        if date:
            out["date"] = date
    return out


def _derived_market_fields(row: dict[str, Any], threshold: float | None, bin_center: float | None) -> dict[str, Any]:
    derived: dict[str, Any] = {}
    if threshold is not None:
        derived["threshold"] = threshold
    if bin_center is not None:
        derived["bin_center"] = bin_center
    question = str(row.get("question") or row.get("title") or "")
    parsed = _parse_market_structure(question) if question else None
    if parsed is None:
        return derived
    if "threshold" not in derived and getattr(parsed, "target_value", None) is not None:
        derived["threshold"] = float(parsed.target_value)
    if "bin_center" not in derived:
        range_low = getattr(parsed, "range_low", None)
        range_high = getattr(parsed, "range_high", None)
        if range_low is not None and range_high is not None:
            derived["bin_center"] = round((float(range_low) + float(range_high)) / 2, 4)
        elif getattr(parsed, "target_value", None) is not None and not getattr(parsed, "is_threshold", False):
            derived["bin_center"] = float(parsed.target_value)
    return derived


def _parse_market_structure(question: str) -> Any | None:
    try:
        return parse_market_question(question)
    except ValueError:
        return None


def _city_from_question(question: str) -> str | None:
    marker = " in "
    lower = question.lower()
    start = lower.find(marker)
    if start < 0:
        return None
    after = question[start + len(marker) :]
    end_positions = [pos for token in (" be ", " on ", "?") if (pos := after.lower().find(token)) >= 0]
    city = after[: min(end_positions) if end_positions else len(after)].strip(" ?.,")
    return city or None


def _date_from_question(question: str) -> str | None:
    lower = question.lower()
    marker = " on "
    start = lower.rfind(marker)
    if start < 0:
        return None
    date = question[start + len(marker) :].strip(" ?.,")
    return date or None


def _parse_timestamp(raw: Any) -> datetime | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    if text.isdigit():
        try:
            return datetime.fromtimestamp(int(text), tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat().replace("+00:00", "Z")


def _minutes_between(start: datetime | None, end: datetime | None) -> int | None:
    if start is None or end is None:
        return None
    return int((end - start).total_seconds() // 60)


def _rows_from_payload(payload: dict[str, Any], preferred_key: str) -> list[dict[str, Any]]:
    rows = payload.get(preferred_key) or payload.get("data")
    if preferred_key == "forecasts" and rows is None:
        rows = payload.get("forecast_snapshots") or payload.get("snapshots")
    if isinstance(rows, list):
        return [dict(row) for row in rows if isinstance(row, dict)]
    return []


def _forecast_rows_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = _rows_from_payload(payload, "forecasts")
    if rows:
        return rows
    sparse: list[dict[str, Any]] = []
    for key, value in payload.items():
        if not isinstance(value, dict):
            continue
        row = dict(value)
        text_key = str(key).strip()
        if text_key:
            row.setdefault("sparse_key", text_key)
            if text_key.isdigit():
                row.setdefault("primary_key", text_key)
                row.setdefault("id", text_key)
            else:
                row.setdefault("market_id", text_key)
                row.setdefault("city", text_key)
        sparse.append(row)
    return sparse


def _load_object(path: str | Path, label: str) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be an object")
    return payload


def _rounded_delta(value: float | None, anchor: float | None) -> float | None:
    if value is None or anchor is None:
        return None
    return round(value - anchor, 4)


def _forecast_value(row: dict[str, Any]) -> float | None:
    for key in ("forecast_value", "value", "forecast_high_c", "forecast_max_proxy", "forecast_round_temp"):
        value = _to_float(row.get(key))
        if value is not None:
            return value
    return None


def _decision_forecast_timestamp(
    forecast: dict[str, Any],
    decision_ts: datetime | None,
    forecast_ts: datetime | None,
    forecast_age_minutes: int | None,
) -> str | None:
    formatted = _format_timestamp(forecast_ts)
    if formatted is not None:
        return formatted
    raw_timestamp = _forecast_timestamp(forecast)
    if raw_timestamp is not None:
        return raw_timestamp
    if decision_ts is not None and forecast_age_minutes is not None:
        return _format_timestamp(datetime.fromtimestamp(decision_ts.timestamp() - (forecast_age_minutes * 60), tz=timezone.utc))
    return None


def _forecast_age_minutes(forecast: dict[str, Any], decision_ts: datetime | None, forecast_ts: datetime | None) -> int | None:
    if decision_ts is not None and forecast_ts is not None:
        return int((decision_ts - forecast_ts).total_seconds() // 60)
    freshness = _to_float(forecast.get("freshness_minutes"))
    return None if freshness is None else int(freshness)


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()
