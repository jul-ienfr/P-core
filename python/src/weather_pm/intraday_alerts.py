from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Mapping, Sequence


def _number(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


def _observation_value(row: Mapping[str, Any]) -> float | None:
    for key in ("value", "temperature", "temp", "observed_value", "current_value"):
        value = _number(row.get(key))
        if value is not None:
            return value
    return None


def _observed_at(row: Mapping[str, Any]) -> datetime | None:
    for key in ("observed_at", "timestamp", "time", "valid_time", "created_at"):
        parsed = _parse_time(row.get(key))
        if parsed is not None:
            return parsed
    return None


def _source_confirmed(row: Mapping[str, Any]) -> bool:
    if row.get("source_confirmed") is not None:
        return bool(row.get("source_confirmed"))
    source = str(row.get("source") or row.get("provider") or row.get("station") or "").strip().lower()
    if not source:
        return False
    return not any(marker in source for marker in ("forecast", "synthetic", "model", "market"))


def _normalise_observations(observations: Sequence[Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in observations or []:
        if not isinstance(raw, Mapping):
            continue
        observed_at = _observed_at(raw)
        value = _observation_value(raw)
        if value is None:
            continue
        rows.append({"observed_at": observed_at, "value": value, "raw": raw})
    rows.sort(key=lambda row: row["observed_at"] or datetime.min.replace(tzinfo=UTC))
    return rows


def build_intraday_alert_summary(
    observations: Sequence[Mapping[str, Any]] | None,
    *,
    threshold: float | None = None,
    direction: str = "above",
    now: datetime | str | None = None,
    stale_after_minutes: int = 90,
    momentum_spike_delta: float = 3.0,
    peak_passed_drop: float = 2.0,
) -> dict[str, Any]:
    """Extract pure intraday weather alert features from recent observation rows.

    The helper is deliberately side-effect free and returns diagnostics only. It is
    intended for paper/runtime operator payloads, not live order enablement.
    """

    rows = _normalise_observations(observations)
    if not rows:
        return {"has_observations": False, "status": "no_data", "alerts": []}

    latest = rows[-1]
    latest_value = float(latest["value"])
    latest_time = latest["observed_at"]
    now_dt = _parse_time(now) if now is not None else None
    age_minutes: int | None = None
    stale = False
    if latest_time is not None and now_dt is not None:
        age_minutes = max(0, int((now_dt - latest_time).total_seconds() // 60))
        stale = age_minutes > stale_after_minutes

    previous_value = float(rows[-2]["value"]) if len(rows) >= 2 else None
    momentum_delta = round(latest_value - previous_value, 4) if previous_value is not None else None
    momentum_spike = momentum_delta is not None and momentum_delta >= momentum_spike_delta

    peak_row = max(rows, key=lambda row: float(row["value"]))
    peak_value = float(peak_row["value"])
    latest_below_peak = round(max(0.0, peak_value - latest_value), 4)
    peak_passed = latest_below_peak >= peak_passed_drop and peak_row is not latest

    threshold_margin = None
    source_confirmed_threshold_margin = False
    threshold_value = _number(threshold)
    source_confirmed = _source_confirmed(latest["raw"])
    if threshold_value is not None:
        if str(direction).lower() in {"below", "under", "lower", "no"}:
            threshold_margin = round(threshold_value - latest_value, 4)
        else:
            threshold_margin = round(latest_value - threshold_value, 4)
        source_confirmed_threshold_margin = source_confirmed and threshold_margin > 0

    alerts: list[str] = []
    if momentum_spike:
        alerts.append("momentum_spike")
    if peak_passed:
        alerts.append("peak_passed_guard")
    if stale:
        alerts.append("stale_observation")
    if source_confirmed_threshold_margin:
        alerts.append("source_confirmed_threshold_margin")

    return {
        "has_observations": True,
        "status": "stale" if stale else "active",
        "alerts": alerts,
        "latest_value": latest_value,
        "latest_observed_at": latest_time.isoformat().replace("+00:00", "Z") if latest_time is not None else None,
        "latest_age_minutes": age_minutes,
        "previous_value": previous_value,
        "momentum_delta": momentum_delta,
        "momentum_spike": momentum_spike,
        "peak_value": peak_value,
        "latest_below_peak": latest_below_peak,
        "peak_passed": peak_passed,
        "stale_observation": stale,
        "source_confirmed": source_confirmed,
        "threshold": threshold_value,
        "direction": direction,
        "threshold_margin": threshold_margin,
        "source_confirmed_threshold_margin": source_confirmed_threshold_margin,
    }


__all__ = ["build_intraday_alert_summary"]
