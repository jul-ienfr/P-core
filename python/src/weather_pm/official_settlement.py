from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Protocol

from weather_pm.models import MarketStructure, StationHistoryBundle, StationHistoryPoint


@dataclass(slots=True)
class OfficialWeatherObservation:
    provider: str
    station_code: str | None
    observed_date: str | None
    measurement_kind: str
    value: float
    unit: str
    source: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class OfficialSettlementResult:
    provider: str
    resolved: bool
    outcome_yes: bool | None
    outcome_label: str | None
    observed_value: float | None
    observed_unit: str
    observation: OfficialWeatherObservation | None
    reason: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["observation"] = self.observation.to_dict() if self.observation else None
        return payload


class OfficialPayloadClient(Protocol):
    def fetch_official_payload(
        self,
        *,
        provider: str,
        structure: MarketStructure,
        target_date: str,
        station_code: str | None,
    ) -> Any: ...


def settlement_validation_status(
    *,
    official_result: Any = None,
    polymarket_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    official_label = _official_outcome_label(official_result)
    polymarket_label = _polymarket_winning_label(polymarket_result)
    official_observation_found = getattr(official_result, "observation", None) is not None
    outcome_classified = official_label is not None
    polymarket_resolved = polymarket_label is not None
    manual_review_required = bool(outcome_classified and polymarket_resolved and official_label != polymarket_label)
    if manual_review_required:
        status = "settlement_mismatch"
    elif outcome_classified and polymarket_resolved:
        status = "settlement_matches"
    elif polymarket_resolved:
        status = "polymarket_resolved"
    elif outcome_classified:
        status = "outcome_classified"
    elif official_observation_found:
        status = "official_observation_found"
    else:
        status = "unresolved"
    return {
        "settlement_validation_status": status,
        "official_outcome": official_label,
        "polymarket_outcome": polymarket_label,
        "manual_review_required": manual_review_required,
    }


def resolve_official_weather_settlement(
    *,
    provider: str,
    structure: MarketStructure,
    payload: Any = None,
    history_bundle: StationHistoryBundle | None = None,
    target_date: str | None = None,
    station_code: str | None = None,
    client: OfficialPayloadClient | None = None,
) -> OfficialSettlementResult:
    """Resolve a weather market from already-fetched official payloads.

    No live network work is performed unless the caller supplies a client and omits both
    payload and history_bundle. Tests exercise the pure payload path.
    """
    if target_date is None:
        target_date = _target_date_from_structure(structure)
    if target_date is None:
        return _unresolved(provider, structure, "missing target_date")

    try:
        if history_bundle is not None:
            observation = parse_station_history_bundle(history_bundle, structure, target_date=target_date)
        else:
            if payload is None and client is not None:
                payload = client.fetch_official_payload(
                    provider=provider,
                    structure=structure,
                    target_date=target_date,
                    station_code=station_code,
                )
            if payload is None:
                return _unresolved(provider, structure, "missing official payload")
            observation = _parse_provider_payload(provider, payload, structure, target_date=target_date, station_code=station_code)
    except ValueError as exc:
        return _unresolved(provider, structure, str(exc))

    return classify_official_outcome(observation, structure)


def parse_noaa_daily_summary(
    payload: Any,
    structure: MarketStructure,
    *,
    target_date: str,
    station_code: str | None = None,
    payload_unit: str = "f",
) -> OfficialWeatherObservation:
    rows = _rows_from_payload(payload)
    field = "TMAX" if structure.measurement_kind == "high" else "TMIN" if structure.measurement_kind == "low" else "TEMP"
    for row in rows:
        if not isinstance(row, dict):
            continue
        if not _row_matches_date(row, target_date):
            continue
        if station_code and not _row_matches_station(row, station_code):
            continue
        raw_value = _get_case_insensitive(row, field)
        if raw_value in (None, "", "-") or isinstance(raw_value, dict):
            continue
        value = _convert_temperature(float(raw_value), from_unit=payload_unit, to_unit=structure.unit)
        return OfficialWeatherObservation(
            provider="noaa",
            station_code=station_code or _station_from_row(row),
            observed_date=target_date,
            measurement_kind=structure.measurement_kind,
            value=round(value, 2),
            unit=structure.unit.lower(),
            source="noaa_daily_summary",
        )
    raise ValueError("missing official observation in NOAA daily summary payload")


def parse_wunderground_observations(
    payload: Any,
    structure: MarketStructure,
    *,
    target_date: str,
    station_code: str | None = None,
) -> OfficialWeatherObservation:
    observations = payload.get("observations") if isinstance(payload, dict) else payload
    if not isinstance(observations, list):
        raise ValueError("missing official observation in Wunderground payload")
    points: list[StationHistoryPoint] = []
    for observation in observations:
        if not isinstance(observation, dict):
            continue
        if station_code and not _row_matches_station(observation, station_code):
            continue
        timestamp = str(observation.get("obsTimeLocal") or observation.get("obsTimeUtc") or observation.get("time") or "")
        if _normalize_date(timestamp) != target_date:
            continue
        extracted = _extract_observation_temperature(observation, default_unit=structure.unit)
        if extracted is None:
            continue
        value, from_unit = extracted
        converted = _convert_temperature(value, from_unit=from_unit, to_unit=structure.unit)
        points.append(StationHistoryPoint(timestamp=timestamp, value=round(converted, 2), unit=structure.unit.lower()))
    return _observation_from_points(
        provider="wunderground",
        source="wunderground_observations",
        station_code=station_code,
        target_date=target_date,
        structure=structure,
        points=points,
    )


def parse_hko_monthly_extract(
    payload: Any,
    structure: MarketStructure,
    *,
    target_date: str,
    station_code: str | None = "HKO",
) -> OfficialWeatherObservation:
    rows = _rows_from_payload(payload)
    target = _parse_iso_date(target_date)
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_date = _parse_hko_row_date(
            _get_first(row, "date", "Date", "recordDate", "day", "Day"),
            year=target.year,
            month=target.month,
        )
        if row_date != target_date:
            continue
        raw_value = _extract_high_low_row_value(row, structure)
        if raw_value is None:
            continue
        raw_unit = str(_get_first(row, "unit", "Unit") or "c")
        value = _convert_temperature(float(raw_value), from_unit=raw_unit, to_unit=structure.unit)
        return OfficialWeatherObservation(
            provider="hong_kong_observatory",
            station_code=station_code,
            observed_date=target_date,
            measurement_kind=structure.measurement_kind,
            value=round(value, 2),
            unit=structure.unit.lower(),
            source="hko_monthly_extract",
        )
    raise ValueError("missing official observation in HKO monthly extract payload")


def parse_station_history_bundle(
    bundle: StationHistoryBundle,
    structure: MarketStructure,
    *,
    target_date: str | None = None,
) -> OfficialWeatherObservation:
    points = []
    for point in bundle.points:
        if target_date is not None and _normalize_date(point.timestamp) != target_date:
            continue
        converted = _convert_temperature(point.value, from_unit=point.unit, to_unit=structure.unit)
        points.append(StationHistoryPoint(timestamp=point.timestamp, value=round(converted, 2), unit=structure.unit.lower()))
    return _observation_from_points(
        provider=bundle.source_provider,
        source="station_history_bundle",
        station_code=bundle.station_code,
        target_date=target_date,
        structure=structure,
        points=points,
    )


def classify_official_outcome(
    observation: OfficialWeatherObservation,
    structure: MarketStructure,
) -> OfficialSettlementResult:
    outcome_yes: bool | None
    if structure.is_threshold:
        if structure.target_value is None:
            return _unresolved(observation.provider, structure, "missing threshold target", observation=observation)
        direction = (structure.threshold_direction or "higher").lower()
        if direction == "higher":
            outcome_yes = observation.value >= structure.target_value
        elif direction == "below":
            outcome_yes = observation.value <= structure.target_value
        else:
            return _unresolved(observation.provider, structure, f"unsupported threshold direction: {direction}", observation=observation)
    elif structure.is_exact_bin:
        if structure.range_low is None or structure.range_high is None:
            return _unresolved(observation.provider, structure, "missing exact-bin range", observation=observation)
        if structure.range_low == structure.range_high:
            outcome_yes = round(observation.value) == round(structure.range_low)
        else:
            outcome_yes = structure.range_low <= observation.value <= structure.range_high
    else:
        return _unresolved(observation.provider, structure, "unsupported market structure", observation=observation)

    return OfficialSettlementResult(
        provider=observation.provider,
        resolved=True,
        outcome_yes=outcome_yes,
        outcome_label="YES" if outcome_yes else "NO",
        observed_value=observation.value,
        observed_unit=observation.unit,
        observation=observation,
        reason="official_observation_classified",
    )


def _official_outcome_label(official_result: Any) -> str | None:
    if official_result is None:
        return None
    outcome_yes = getattr(official_result, "outcome_yes", None)
    if not bool(getattr(official_result, "resolved", False)) or outcome_yes is None:
        return None
    return "Yes" if bool(outcome_yes) else "No"


def _polymarket_winning_label(polymarket_result: dict[str, Any] | None) -> str | None:
    if not polymarket_result:
        return None
    if polymarket_result.get("settlement_status") not in {"SETTLED_WON", "SETTLED_LOST"}:
        return None
    winning = polymarket_result.get("winning_outcome")
    return str(winning) if winning not in (None, "") else None


def _parse_provider_payload(
    provider: str,
    payload: Any,
    structure: MarketStructure,
    *,
    target_date: str,
    station_code: str | None,
) -> OfficialWeatherObservation:
    if provider == "noaa":
        return parse_noaa_daily_summary(payload, structure, target_date=target_date, station_code=station_code)
    if provider == "wunderground":
        return parse_wunderground_observations(payload, structure, target_date=target_date, station_code=station_code)
    if provider == "hong_kong_observatory":
        return parse_hko_monthly_extract(payload, structure, target_date=target_date, station_code=station_code or "HKO")
    raise ValueError(f"unsupported provider: {provider}")


def _observation_from_points(
    *,
    provider: str,
    source: str,
    station_code: str | None,
    target_date: str | None,
    structure: MarketStructure,
    points: list[StationHistoryPoint],
) -> OfficialWeatherObservation:
    if not points:
        raise ValueError(f"missing official observation in {source}")
    if structure.measurement_kind == "low":
        selected = min(points, key=lambda point: point.value)
    else:
        selected = max(points, key=lambda point: point.value)
    return OfficialWeatherObservation(
        provider=provider,
        station_code=station_code,
        observed_date=target_date or _normalize_date(selected.timestamp),
        measurement_kind=structure.measurement_kind,
        value=round(selected.value, 2),
        unit=structure.unit.lower(),
        source=source,
    )


def _unresolved(
    provider: str,
    structure: MarketStructure,
    reason: str,
    *,
    observation: OfficialWeatherObservation | None = None,
) -> OfficialSettlementResult:
    return OfficialSettlementResult(
        provider=provider,
        resolved=False,
        outcome_yes=None,
        outcome_label=None,
        observed_value=observation.value if observation else None,
        observed_unit=(observation.unit if observation else structure.unit.lower()),
        observation=observation,
        reason=reason,
    )


def _rows_from_payload(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("data", "records", "observations", "results", "rows"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return rows
    raise ValueError("missing official observation rows")


def _get_case_insensitive(row: dict[str, Any], key: str) -> Any:
    lowered = key.lower()
    for candidate, value in row.items():
        if str(candidate).lower() == lowered:
            return value
    return None


def _get_first(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = _get_case_insensitive(row, key)
        if value is not None:
            return value
    return None


def _row_matches_date(row: dict[str, Any], target_date: str) -> bool:
    raw = _get_first(row, "DATE", "date", "time", "timestamp", "obsTimeLocal", "obsTimeUtc")
    return _normalize_date(str(raw or "")) == target_date


def _row_matches_station(row: dict[str, Any], station_code: str) -> bool:
    lowered = station_code.strip().lower()
    for key in ("STATION", "station", "stationID", "stationId", "station_code", "stationCode", "icao", "id"):
        raw = _get_case_insensitive(row, key)
        if raw is not None and str(raw).strip().lower() == lowered:
            return True
    # Some official fixture rows omit the station when the request URL already scopes it.
    return not any(_get_case_insensitive(row, key) is not None for key in ("STATION", "station", "stationID", "stationId", "station_code", "stationCode", "icao", "id"))


def _station_from_row(row: dict[str, Any]) -> str | None:
    raw = _get_first(row, "STATION", "station", "stationID", "stationId", "station_code", "stationCode", "icao", "id")
    return str(raw) if raw is not None else None


def _extract_observation_temperature(row: dict[str, Any], *, default_unit: str) -> tuple[float, str] | None:
    imperial = row.get("imperial")
    if isinstance(imperial, dict) and imperial.get("temp") not in (None, "", "-"):
        return float(imperial["temp"]), "f"
    metric = row.get("metric")
    if isinstance(metric, dict) and metric.get("temp") not in (None, "", "-"):
        return float(metric["temp"]), "c"
    for key in ("temp", "temperature", "value"):
        raw = _get_case_insensitive(row, key)
        if isinstance(raw, dict) and raw.get("value") not in (None, "", "-"):
            return float(raw["value"]), str(raw.get("unit") or raw.get("unitCode") or default_unit)
        if raw not in (None, "", "-") and not isinstance(raw, dict):
            return float(raw), str(_get_first(row, "unit", "Unit", "tempUnit", "tempUnits") or default_unit)
    return None


def _extract_high_low_row_value(row: dict[str, Any], structure: MarketStructure) -> Any:
    keys = (
        ("max", "maximum", "maxt", "tempmax", "tmax", "value")
        if structure.measurement_kind == "high"
        else ("min", "minimum", "mint", "tempmin", "tmin", "value")
    )
    for key in keys:
        value = _get_case_insensitive(row, key)
        if value not in (None, "", "-") and not isinstance(value, dict):
            return value
    return None


def _convert_temperature(value: float, *, from_unit: str, to_unit: str) -> float:
    source = _normalize_unit(from_unit)
    target = _normalize_unit(to_unit)
    if source == target:
        return value
    if source == "c" and target == "f":
        return value * 9.0 / 5.0 + 32.0
    if source == "f" and target == "c":
        return (value - 32.0) * 5.0 / 9.0
    return value


def _normalize_unit(unit: str) -> str:
    text = str(unit).strip().lower()
    if text in {"degc", "celsius", "degree c", "degrees c", "°c"} or text.endswith(":degc"):
        return "c"
    if text in {"degf", "fahrenheit", "degree f", "degrees f", "°f"} or text.endswith(":degf"):
        return "f"
    return text[:1] if text else ""


def _normalize_date(raw_value: str) -> str | None:
    text = str(raw_value).strip()
    if not text:
        return None
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    for fmt in ("%Y%m%d", "%d/%m/%Y", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text[:19], fmt).date().isoformat()
        except ValueError:
            pass
    return None


def _parse_iso_date(raw_value: str) -> datetime:
    try:
        return datetime.strptime(raw_value, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"date must be YYYY-MM-DD: {raw_value}") from exc


def _parse_hko_row_date(raw_value: Any, *, year: int, month: int) -> str | None:
    if raw_value is None:
        return None
    text = str(raw_value).strip()
    normalized = _normalize_date(text)
    if normalized is not None:
        return normalized
    if text.isdigit():
        try:
            return datetime(year, month, int(text)).date().isoformat()
        except ValueError:
            return None
    return None


def _target_date_from_structure(structure: MarketStructure) -> str | None:
    raw = structure.date_local
    if not raw:
        return None
    normalized = _normalize_date(raw)
    return normalized
