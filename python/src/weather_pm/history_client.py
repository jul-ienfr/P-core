from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import quote, urlencode
from urllib.request import urlopen

from weather_pm.forecast_client import _convert_temperature
from weather_pm.models import MarketStructure, ResolutionMetadata, StationHistoryBundle, StationHistoryPoint


def build_station_history_bundle(
    structure: MarketStructure,
    resolution: ResolutionMetadata,
    *,
    start_date: str,
    end_date: str,
    client: StationHistoryClient | None = None,
) -> StationHistoryBundle:
    history_client = client or StationHistoryClient()
    try:
        return history_client.fetch_history_bundle(structure, resolution, start_date=start_date, end_date=end_date)
    except Exception:
        return StationHistoryBundle(
            source_provider=resolution.provider,
            station_code=resolution.station_code,
            source_url=resolution.source_url,
            latency_tier="unsupported",
            points=[],
            summary={},
        )


class StationHistoryClient:
    def __init__(self, *, timeout: float = 10.0, now_utc: datetime | None = None) -> None:
        self.timeout = timeout
        self._now_utc = now_utc

    def fetch_latest_bundle(self, structure: MarketStructure, resolution: ResolutionMetadata) -> StationHistoryBundle:
        if resolution.provider == "noaa" and resolution.station_code:
            url = f"https://api.weather.gov/stations/{quote(resolution.station_code)}/observations/latest"
            payload = self._fetch_json(url)
            points = self._parse_noaa_latest_point(structure, payload)
            return self._bundle(resolution, url=url, points=points, latency_tier="direct_latest")

        if resolution.provider == "wunderground" and resolution.source_url and resolution.station_code:
            payload = self._fetch_json(resolution.source_url)
            points = self._parse_wunderground_points(structure, payload)
            if points:
                points = [points[-1]]
            return self._bundle(resolution, url=resolution.source_url, points=points, latency_tier="direct_latest")

        if resolution.provider == "accuweather" and resolution.source_url:
            payload = self._fetch_json(resolution.source_url)
            points = self._parse_accuweather_current_points(structure, payload)
            return self._bundle(resolution, url=resolution.source_url, points=points, latency_tier="direct_latest")

        if resolution.provider == "aviation_weather" and resolution.station_code:
            url = self._build_aviation_weather_url(resolution.station_code)
            payload = self._fetch_json(url)
            points = self._parse_aviation_weather_points(structure, payload)
            if points:
                points = [points[-1]]
            return self._bundle(resolution, url=url, points=points, latency_tier="direct_latest")

        if resolution.provider == "hong_kong_observatory":
            url = "https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=rhrread&lang=en"
            payload = self._fetch_json(url)
            points = self._parse_hko_latest_points(structure, payload)
            hko_resolution = ResolutionMetadata(
                provider=resolution.provider,
                source_url=resolution.source_url,
                station_code=resolution.station_code or "HKO",
                station_name=resolution.station_name,
                station_type=resolution.station_type,
                wording_clear=resolution.wording_clear,
                rules_clear=resolution.rules_clear,
                manual_review_needed=resolution.manual_review_needed,
                revision_risk=resolution.revision_risk,
            )
            return self._bundle(hko_resolution, url=url, points=points, latency_tier="direct_latest")

        if resolution.provider in _DIRECT_API_PROVIDERS and resolution.source_url:
            payload = self._fetch_json(resolution.source_url)
            points = self._parse_generic_weather_points(structure, resolution, payload, latest=True)
            latency_tier = "direct_latest" if resolution.provider == "meteo_france" else "direct_api"
            return self._bundle(resolution, url=resolution.source_url, points=points[-1:] if points else [], latency_tier=latency_tier)

        if resolution.provider in _DIRECT_SOURCE_PROVIDERS and resolution.source_url:
            payload = self._fetch_json(resolution.source_url)
            points = self._parse_generic_weather_points(structure, resolution, payload, latest=True)
            latency_tier = "direct_latest" if resolution.provider in {"environment_canada", "pagasa"} else _latency_tier_for_provider(resolution.provider)
            return self._bundle(resolution, url=resolution.source_url, points=points[-1:] if points else [], latency_tier=latency_tier)

        raise ValueError(f"no direct latest route for provider={resolution.provider!r}")

    def fetch_history_bundle(
        self,
        structure: MarketStructure,
        resolution: ResolutionMetadata,
        *,
        start_date: str,
        end_date: str,
    ) -> StationHistoryBundle:
        if resolution.provider == "noaa" and resolution.station_code:
            daily_summary = _uses_noaa_daily_summary(structure, start_date=start_date, end_date=end_date)
            url = self._build_noaa_history_url(structure, resolution.station_code, start_date=start_date, end_date=end_date)
            payload = self._fetch_json(url)
            points = (
                self._parse_noaa_daily_summary_points(structure, payload)
                if daily_summary
                else self._parse_noaa_points(structure, payload)
            )
            return self._bundle(resolution, url=url, points=points, latency_tier="direct_history" if daily_summary else "direct")

        if resolution.provider == "wunderground" and resolution.source_url and resolution.station_code:
            url = self._build_wunderground_history_url(resolution.source_url, start_date=start_date, end_date=end_date)
            payload = self._fetch_json(url)
            points = self._parse_wunderground_points(structure, payload)
            return self._bundle(resolution, url=url, points=points)

        if resolution.provider == "accuweather" and resolution.source_url:
            url = self._build_accuweather_history_url(resolution.source_url, start_date=start_date, end_date=end_date)
            payload = self._fetch_json(url)
            points = self._parse_accuweather_daily_points(structure, payload, start_date=start_date, end_date=end_date)
            return self._bundle(resolution, url=url, points=points, latency_tier="direct_history")

        if resolution.provider == "aviation_weather" and resolution.station_code:
            url = self._build_aviation_weather_url(resolution.station_code, start_date=start_date, end_date=end_date)
            payload = self._fetch_json(url)
            points = self._parse_aviation_weather_points(structure, payload)
            return self._bundle(resolution, url=url, points=points, latency_tier="direct_history")

        if resolution.provider == "hong_kong_observatory":
            url = self._build_hko_daily_extract_url(structure, start_date=start_date, end_date=end_date)
            payload = self._fetch_json(url)
            points = self._parse_hko_daily_extract_points(structure, payload, start_date=start_date, end_date=end_date)
            hko_resolution = ResolutionMetadata(
                provider=resolution.provider,
                source_url=resolution.source_url,
                station_code=resolution.station_code or "HKO",
                station_name=resolution.station_name,
                station_type=resolution.station_type,
                wording_clear=resolution.wording_clear,
                rules_clear=resolution.rules_clear,
                manual_review_needed=resolution.manual_review_needed,
                revision_risk=resolution.revision_risk,
            )
            return self._bundle(hko_resolution, url=url, points=points, latency_tier="direct_history")

        if resolution.provider == "meteostat" and (resolution.station_code or structure.city):
            url = self._build_meteostat_history_url(structure, resolution, start_date=start_date, end_date=end_date)
            payload = self._fetch_json(url)
            points = self._parse_meteostat_daily_points(structure, payload, start_date=start_date, end_date=end_date)
            bundle = self._bundle(resolution, url=url, points=points, latency_tier="fallback_history")
            if resolution.station_code is None:
                bundle.polling_focus = "meteostat_city_daily_history"
            return bundle

        if resolution.provider == "ecmwf_copernicus":
            url = self._build_ecmwf_copernicus_history_url(structure, start_date=start_date, end_date=end_date)
            payload = self._fetch_json(url)
            points = self._parse_generic_weather_points(structure, resolution, payload, start_date=start_date, end_date=end_date)
            return self._bundle(resolution, url=url, points=points, latency_tier="fallback_reanalysis")

        if resolution.provider == "environment_canada" and resolution.source_url:
            url = self._build_environment_canada_history_url(resolution.source_url, start_date=start_date, end_date=end_date)
            payload = self._fetch_json(url)
            points = self._parse_generic_weather_points(structure, resolution, payload, start_date=start_date, end_date=end_date)
            return self._bundle(resolution, url=url, points=points, latency_tier="direct_history")

        if resolution.provider in (_DIRECT_API_PROVIDERS | _DIRECT_SOURCE_PROVIDERS) and resolution.source_url:
            payload = self._fetch_json(resolution.source_url)
            points = self._parse_generic_weather_points(structure, resolution, payload, start_date=start_date, end_date=end_date)
            if resolution.provider in {"web_scrape", "local_official_weather_source"} and not points:
                raise ValueError(f"{resolution.provider} payload had no parseable temperature rows")
            latency_tier = "direct_history" if resolution.provider == "meteo_france" else _latency_tier_for_provider(resolution.provider)
            return self._bundle(resolution, url=resolution.source_url, points=points, latency_tier=latency_tier)

        raise ValueError(f"no direct history route for provider={resolution.provider!r}")

    def _build_noaa_history_url(self, structure: MarketStructure, station_code: str, *, start_date: str, end_date: str) -> str:
        if _uses_noaa_daily_summary(structure, start_date=start_date, end_date=end_date):
            query = urlencode(
                {
                    "dataset": "daily-summaries",
                    "stations": station_code,
                    "startDate": start_date,
                    "endDate": end_date,
                    "format": "json",
                    "units": "standard",
                    "includeAttributes": "false",
                }
            )
            return f"https://www.ncei.noaa.gov/access/services/data/v1?{query}"
        query = urlencode({"start": f"{start_date}T00:00:00Z", "end": f"{end_date}T23:59:59Z"})
        return f"https://api.weather.gov/stations/{quote(station_code)}/observations?{query}"

    def _build_wunderground_history_url(self, source_url: str, *, start_date: str, end_date: str) -> str:
        if start_date != end_date:
            raise ValueError("Wunderground direct history currently supports a single day per request")
        return f"{source_url.rstrip('/')}/date/{start_date}"

    def _build_accuweather_history_url(self, source_url: str, *, start_date: str, end_date: str) -> str:
        if start_date != end_date:
            raise ValueError("AccuWeather direct history currently supports a single day per request")
        separator = "&" if "?" in source_url else "?"
        return f"{source_url}{separator}details=true"

    def _build_aviation_weather_url(self, station_code: str, *, start_date: str | None = None, end_date: str | None = None) -> str:
        query = {"ids": station_code, "format": "json", "taf": "false"}
        if start_date and end_date:
            query.update({"start": f"{start_date}T00:00:00Z", "end": f"{end_date}T23:59:59Z"})
        return f"https://aviationweather.gov/api/data/metar?{urlencode(query)}"

    def _build_hko_daily_extract_url(self, structure: MarketStructure, *, start_date: str, end_date: str) -> str:
        if start_date != end_date:
            raise ValueError("HKO direct daily extract currently supports a single day per request")
        parsed_date = _parse_iso_date(start_date)
        data_type = "CLMMINT" if structure.measurement_kind == "low" else "CLMMAXT"
        query = urlencode(
            {
                "dataType": data_type,
                "rformat": "json",
                "station": "HKO",
                "year": parsed_date.year,
                "month": parsed_date.month,
            }
        )
        return f"https://data.weather.gov.hk/weatherAPI/opendata/opendata.php?{query}"

    def _build_meteostat_history_url(self, structure: MarketStructure, resolution: ResolutionMetadata, *, start_date: str, end_date: str) -> str:
        location_key = "station" if resolution.station_code else "city"
        location_value = resolution.station_code or structure.city
        query = urlencode({location_key: location_value, "start": start_date, "end": end_date})
        return f"meteostat://daily?{query}"

    def _build_ecmwf_copernicus_history_url(self, structure: MarketStructure, *, start_date: str, end_date: str) -> str:
        query = urlencode({"city": structure.city, "start": start_date, "end": end_date})
        return f"ecmwf_copernicus://reanalysis?{query}"

    def _build_environment_canada_history_url(self, source_url: str, *, start_date: str, end_date: str) -> str:
        parsed = _parse_iso_date(start_date)
        separator = "&" if "?" in source_url else "?"
        query = urlencode({"timeframe": "2", "StartYear": "1840", "EndYear": parsed.year, "Year": parsed.year, "Month": parsed.month, "Day": parsed.day})
        return f"{source_url}{separator}{query}"

    def _parse_noaa_latest_point(self, structure: MarketStructure, payload: dict[str, Any]) -> list[StationHistoryPoint]:
        properties = payload.get("properties")
        if not isinstance(properties, dict):
            raise ValueError("NOAA latest payload missing properties")
        point = self._parse_noaa_properties_point(structure, properties)
        return [point] if point else []

    def _parse_noaa_points(self, structure: MarketStructure, payload: dict[str, Any]) -> list[StationHistoryPoint]:
        features = payload.get("features")
        if not isinstance(features, list):
            raise ValueError("NOAA history payload missing features")
        points: list[StationHistoryPoint] = []
        for feature in features:
            if not isinstance(feature, dict):
                continue
            properties = feature.get("properties")
            if not isinstance(properties, dict):
                continue
            point = self._parse_noaa_properties_point(structure, properties)
            if point:
                points.append(point)
        return points

    def _parse_noaa_properties_point(self, structure: MarketStructure, properties: dict[str, Any]) -> StationHistoryPoint | None:
        temperature = properties.get("temperature")
        if not isinstance(temperature, dict) or temperature.get("value") is None:
            return None
        timestamp = str(properties.get("timestamp") or "")
        value = _convert_temperature(float(temperature["value"]), from_unit="c", to_unit=structure.unit)
        return StationHistoryPoint(timestamp=timestamp, value=round(value, 2), unit=structure.unit)

    def _parse_noaa_daily_summary_points(self, structure: MarketStructure, payload: Any) -> list[StationHistoryPoint]:
        if not isinstance(payload, list):
            raise ValueError("NOAA daily summary payload missing data rows")
        field = "TMAX" if structure.measurement_kind == "high" else "TMIN"
        points: list[StationHistoryPoint] = []
        for row in payload:
            if not isinstance(row, dict):
                continue
            value = row.get(field)
            if value is None or value == "" or value == "-" or isinstance(value, dict):
                continue
            points.append(StationHistoryPoint(timestamp=str(row.get("DATE") or ""), value=round(float(value), 2), unit=structure.unit))
        return points

    def _parse_wunderground_points(self, structure: MarketStructure, payload: dict[str, Any]) -> list[StationHistoryPoint]:
        observations = payload.get("observations")
        if not isinstance(observations, list):
            raise ValueError("Wunderground history payload missing observations")
        points: list[StationHistoryPoint] = []
        for observation in observations:
            if not isinstance(observation, dict):
                continue
            timestamp = str(observation.get("obsTimeLocal") or observation.get("obsTimeUtc") or "")
            metric = observation.get("metric")
            imperial = observation.get("imperial")
            if isinstance(imperial, dict) and imperial.get("temp") is not None:
                value = _convert_temperature(float(imperial["temp"]), from_unit="f", to_unit=structure.unit)
            elif isinstance(metric, dict) and metric.get("temp") is not None:
                value = _convert_temperature(float(metric["temp"]), from_unit="c", to_unit=structure.unit)
            else:
                continue
            points.append(StationHistoryPoint(timestamp=timestamp, value=round(value, 2), unit=structure.unit))
        return points

    def _parse_accuweather_current_points(self, structure: MarketStructure, payload: dict[str, Any]) -> list[StationHistoryPoint]:
        observation = payload[0] if isinstance(payload, list) and payload else payload
        if not isinstance(observation, dict):
            raise ValueError("AccuWeather current payload missing observation")
        timestamp = str(observation.get("LocalObservationDateTime") or observation.get("EpochTime") or "")
        value_and_unit = _extract_accuweather_temperature(observation.get("Temperature"), structure)
        if value_and_unit is None:
            raise ValueError("AccuWeather current payload missing temperature")
        value, from_unit = value_and_unit
        converted = _convert_temperature(value, from_unit=from_unit, to_unit=structure.unit)
        return [StationHistoryPoint(timestamp=timestamp, value=round(converted, 2), unit=structure.unit)]

    def _parse_accuweather_daily_points(
        self,
        structure: MarketStructure,
        payload: dict[str, Any],
        *,
        start_date: str,
        end_date: str,
    ) -> list[StationHistoryPoint]:
        if start_date != end_date:
            raise ValueError("AccuWeather direct history currently supports a single day per request")
        rows = payload.get("DailyForecasts") or payload.get("dailyForecasts") or payload.get("forecasts")
        if not isinstance(rows, list):
            raise ValueError("AccuWeather daily payload missing forecasts")
        points: list[StationHistoryPoint] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            row_date = _parse_accuweather_date(row.get("Date") or row.get("date") or row.get("LocalDate"))
            if row_date != start_date:
                continue
            temperature = row.get("Temperature") or row.get("temperature")
            value_and_unit = _extract_accuweather_daily_temperature(temperature, structure)
            if value_and_unit is None:
                continue
            value, from_unit = value_and_unit
            converted = _convert_temperature(value, from_unit=from_unit, to_unit=structure.unit)
            points.append(StationHistoryPoint(timestamp=row_date, value=round(converted, 2), unit=structure.unit))
        return points

    def _parse_aviation_weather_points(self, structure: MarketStructure, payload: Any) -> list[StationHistoryPoint]:
        observations = payload.get("data") or payload.get("observations") if isinstance(payload, dict) else payload
        if not isinstance(observations, list):
            raise ValueError("AviationWeather payload missing observations")
        points: list[StationHistoryPoint] = []
        for observation in observations:
            if not isinstance(observation, dict):
                continue
            parsed = _extract_aviation_weather_temperature(observation)
            if parsed is None:
                continue
            value, from_unit = parsed
            timestamp = str(observation.get("obsTime") or observation.get("reportTime") or observation.get("receiptTime") or observation.get("time") or "")
            converted = _convert_temperature(value, from_unit=from_unit, to_unit=structure.unit)
            points.append(StationHistoryPoint(timestamp=timestamp, value=round(converted, 2), unit=structure.unit))
        return points

    def _parse_hko_latest_points(self, structure: MarketStructure, payload: dict[str, Any]) -> list[StationHistoryPoint]:
        temperature = payload.get("temperature")
        rows = temperature.get("data") if isinstance(temperature, dict) else None
        if not isinstance(rows, list):
            raise ValueError("HKO latest payload missing temperature data rows")
        timestamp = str(payload.get("updateTime") or payload.get("UpdateTime") or "")
        points: list[StationHistoryPoint] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            place = str(row.get("place") or row.get("Place") or "").strip().lower()
            if place not in {"hong kong observatory", "hko"}:
                continue
            value = row.get("value") or row.get("Value")
            if value is None or value == "" or value == "-" or isinstance(value, dict):
                continue
            converted = _convert_temperature(float(value), from_unit=str(row.get("unit") or row.get("Unit") or "C").lower(), to_unit=structure.unit)
            points.append(StationHistoryPoint(timestamp=timestamp, value=round(converted, 2), unit=structure.unit))
        return points

    def _parse_hko_daily_extract_points(
        self,
        structure: MarketStructure,
        payload: dict[str, Any],
        *,
        start_date: str,
        end_date: str,
    ) -> list[StationHistoryPoint]:
        if start_date != end_date:
            raise ValueError("HKO direct daily extract currently supports a single day per request")
        target = _parse_iso_date(start_date)
        raw_rows = payload.get("data") or payload.get("records") or payload.get("observations")
        if not isinstance(raw_rows, list):
            raise ValueError("HKO daily extract payload missing data rows")
        points: list[StationHistoryPoint] = []
        for row in raw_rows:
            if not isinstance(row, dict):
                continue
            row_date = _parse_hko_row_date(row.get("date") or row.get("Date") or row.get("recordDate") or row.get("day"), year=target.year, month=target.month)
            if row_date != target.date().isoformat():
                continue
            value = _extract_hko_row_value(row, structure)
            if value is None:
                continue
            converted = _convert_temperature(value, from_unit=str(row.get("unit") or row.get("Unit") or "C").lower(), to_unit=structure.unit)
            points.append(StationHistoryPoint(timestamp=row_date, value=round(converted, 2), unit=structure.unit))
        return points

    def _parse_meteostat_daily_points(
        self,
        structure: MarketStructure,
        payload: dict[str, Any],
        *,
        start_date: str,
        end_date: str,
    ) -> list[StationHistoryPoint]:
        start = _parse_iso_date(start_date).date().isoformat()
        end = _parse_iso_date(end_date).date().isoformat()
        raw_rows = payload.get("data") or payload.get("rows") or payload.get("observations")
        if not isinstance(raw_rows, list):
            raise ValueError("Meteostat daily payload missing data rows")
        points: list[StationHistoryPoint] = []
        for row in raw_rows:
            if not isinstance(row, dict):
                continue
            row_date = _parse_meteostat_row_date(row.get("date") or row.get("time") or row.get("datetime"))
            if row_date is None or row_date < start or row_date > end:
                continue
            value = _extract_meteostat_row_value(row, structure)
            if value is None:
                continue
            converted = _convert_temperature(value, from_unit=str(row.get("unit") or row.get("Unit") or "C").lower(), to_unit=structure.unit)
            points.append(StationHistoryPoint(timestamp=row_date, value=round(converted, 2), unit=structure.unit))
        return points

    def _parse_generic_weather_points(
        self,
        structure: MarketStructure,
        resolution: ResolutionMetadata,
        payload: Any,
        *,
        latest: bool = False,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[StationHistoryPoint]:
        rows = _extract_rows(payload)
        if not rows:
            raise ValueError(f"{resolution.provider} payload missing table-like rows")
        start = _parse_iso_date(start_date).date().isoformat() if start_date else None
        end = _parse_iso_date(end_date).date().isoformat() if end_date else None
        points: list[StationHistoryPoint] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            if resolution.station_code and not _row_matches_station(row, resolution.station_code):
                continue
            timestamp = _extract_row_timestamp(row)
            row_date = _normalize_date(timestamp)
            if start and end:
                if row_date and (row_date < start or row_date > end):
                    continue
                if not row_date and latest is False and _row_has_explicit_timestamp(row):
                    continue
            extracted = _extract_generic_temperature(row, structure)
            if extracted is None:
                continue
            value, from_unit = extracted
            converted = _convert_temperature(value, from_unit=from_unit, to_unit=structure.unit)
            points.append(StationHistoryPoint(timestamp=row_date if not latest and row_date else timestamp, value=round(converted, 2), unit=structure.unit))
        if resolution.provider == "uk_met_office" and points and structure.measurement_kind in {"high", "low"}:
            selected = max(points, key=lambda point: point.value) if structure.measurement_kind == "high" else min(points, key=lambda point: point.value)
            return [StationHistoryPoint(timestamp=selected.timestamp, value=selected.value, unit=selected.unit)]
        return points

    def _bundle(
        self,
        resolution: ResolutionMetadata,
        *,
        url: str,
        points: list[StationHistoryPoint],
        latency_tier: str = "direct",
    ) -> StationHistoryBundle:
        polling_focus, expected_lag_seconds = _latency_operational_fields(resolution.provider, latency_tier)
        return StationHistoryBundle(
            source_provider=resolution.provider,
            station_code=resolution.station_code,
            source_url=url,
            latency_tier=latency_tier,
            points=points,
            summary=_summarize(points),
            polling_focus=polling_focus,
            expected_lag_seconds=expected_lag_seconds,
            source_lag_seconds=self._source_lag_seconds(points) if latency_tier == "direct_latest" else None,
        )

    def _source_lag_seconds(self, points: list[StationHistoryPoint]) -> int | None:
        if not points:
            return None
        observed_at = _parse_observation_timestamp(points[-1].timestamp)
        if observed_at is None:
            return None
        now = self._now_utc or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        return max(0, int((now.astimezone(timezone.utc) - observed_at).total_seconds()))

    def _fetch_json(self, url: str) -> dict[str, Any]:
        with urlopen(url, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))


def _uses_noaa_daily_summary(structure: MarketStructure, *, start_date: str, end_date: str) -> bool:
    return start_date == end_date and structure.measurement_kind in {"high", "low"}



def _parse_observation_timestamp(raw_timestamp: str) -> datetime | None:
    text = str(raw_timestamp).strip()
    if not text:
        return None
    candidates = [text]
    if text.endswith("Z"):
        candidates.append(f"{text[:-1]}+00:00")
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        candidates.append(f"{text}T00:00:00+00:00")
    for candidate in candidates:
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)



def _latency_operational_fields(provider: str, latency_tier: str) -> tuple[str | None, int | None]:
    focus_by_provider = {
        "weatherapi": "weatherapi_injected_payload",
        "visual_crossing": "visual_crossing_injected_payload",
        "weatherbit": "weatherbit_injected_payload",
        "tomorrow_io": "tomorrow_io_injected_payload",
        "meteoblue": "meteoblue_injected_payload",
        "open_meteo": "open_meteo_injected_payload",
        "openweather": "openweather_injected_payload",
        "yr_no": "yr_no_injected_payload",
        "world_weather_online": "world_weather_online_injected_payload",
        "meteomatics": "meteomatics_injected_payload",
        "weatherlink": "weatherlink_injected_payload",
        "ambient_weather": "ambient_weather_injected_payload",
        "netatmo": "netatmo_injected_payload",
        "windy": "windy_injected_payload",
        "aerisweather": "aerisweather_injected_payload",
        "meteo_france": "meteo_france_daily_payload",
        "uk_met_office": "uk_met_office_daily_payload" if latency_tier != "direct_latest" else "uk_met_office_injected_payload_or_explicit_endpoint",
        "dwd": "dwd_open_data_daily_observations",
        "bom": "bom_official_observations_or_injected_payload",
        "jma": "jma_official_amedas_or_injected_payload",
        "pagasa": "pagasa_official_observations_or_injected_payload",
        "imd": "imd_official_observations_or_injected_payload",
        "meteoswiss": "meteoswiss_official_observations",
        "smhi": "smhi_official_observations",
        "knmi": "knmi_official_observations",
        "aemet": "aemet_official_observations",
        "met_eireann": "met_eireann_official_observations",
        "dmi": "dmi_official_observations",
        "meteochile": "meteochile_official_observations",
        "inmet": "inmet_official_observations",
        "senamhi_peru": "senamhi_peru_official_observations",
        "ideam_colombia": "ideam_colombia_official_observations",
        "smn_argentina": "smn_argentina_official_observations",
        "smn_mexico": "smn_mexico_official_observations",
        "environment_canada": "environment_canada_official_observation" if latency_tier == "direct_latest" else "environment_canada_official_history",
        "ecmwf_copernicus": "ecmwf_copernicus_reanalysis_daily",
        "web_scrape": "manual_html_extraction",
        "local_official_weather_source": "local_official_source_review",
    }
    if provider in focus_by_provider:
        lag = 86400 if latency_tier in {"direct_history", "fallback_reanalysis"} else None
        return focus_by_provider[provider], lag
    if provider == "accuweather" and latency_tier == "direct_latest":
        return "accuweather_current_payload", None
    if provider == "accuweather" and latency_tier == "direct_history":
        return "accuweather_daily_payload", 86400
    if provider == "aviation_weather":
        return "aviation_weather_metar_observations", None
    if provider == "hong_kong_observatory" and latency_tier == "direct_latest":
        return "hko_current_weather_api", None
    if provider == "hong_kong_observatory" and latency_tier == "direct_history":
        return "hko_official_daily_extract", 86400
    if provider == "noaa" and latency_tier == "direct_latest":
        return "station_observations_latest", None
    if provider == "noaa" and latency_tier == "direct_history":
        return "noaa_official_daily_summary", 86400
    if provider == "noaa":
        return "station_observations_history", None
    if provider == "wunderground":
        return "station_history_page", None
    if provider == "meteostat":
        return "meteostat_daily_history", 86400
    return None, None


def _summarize(points: list[StationHistoryPoint]) -> dict[str, float]:
    if not points:
        return {}
    values = [point.value for point in points]
    return {
        "min": round(min(values), 2),
        "max": round(max(values), 2),
        "mean": round(sum(values) / len(values), 2),
        "latest": round(points[-1].value, 2),
        "point_count": float(len(points)),
    }


def _parse_iso_date(raw_value: str) -> datetime:
    try:
        return datetime.strptime(raw_value, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"date must be YYYY-MM-DD: {raw_value}") from exc


def _extract_aviation_weather_temperature(observation: dict[str, Any]) -> tuple[float, str] | None:
    if observation.get("temp_c") is not None:
        return float(observation["temp_c"]), "c"
    if observation.get("temp_f") is not None:
        return float(observation["temp_f"]), "f"
    if observation.get("temp") is not None:
        return float(observation["temp"]), str(observation.get("tempUnits") or observation.get("tempUnit") or "C").lower()
    temperature = observation.get("temperature")
    if isinstance(temperature, dict) and temperature.get("value") is not None:
        return float(temperature["value"]), str(temperature.get("unit") or temperature.get("unitCode") or "C").lower()
    return None


def _parse_accuweather_date(raw_value: Any) -> str | None:
    if raw_value is None:
        return None
    text = str(raw_value).strip()
    if not text:
        return None
    return text[:10]


def _extract_accuweather_daily_temperature(raw_value: Any, structure: MarketStructure) -> tuple[float, str] | None:
    if not isinstance(raw_value, dict):
        return None
    preferred_key = "Maximum" if structure.measurement_kind == "high" else "Minimum"
    value = raw_value.get(preferred_key) or raw_value.get(preferred_key.lower())
    return _extract_accuweather_temperature(value, structure)


def _extract_accuweather_temperature(raw_value: Any, structure: MarketStructure) -> tuple[float, str] | None:
    if not isinstance(raw_value, dict):
        return None
    preferred_key = "Imperial" if structure.unit.lower() == "f" else "Metric"
    preferred = raw_value.get(preferred_key) or raw_value.get(preferred_key.lower())
    if isinstance(preferred, dict) and preferred.get("Value") is not None:
        return float(preferred["Value"]), str(preferred.get("Unit") or structure.unit).lower()
    if raw_value.get("Value") is not None:
        return float(raw_value["Value"]), str(raw_value.get("Unit") or structure.unit).lower()
    for candidate in raw_value.values():
        if isinstance(candidate, dict) and candidate.get("Value") is not None:
            return float(candidate["Value"]), str(candidate.get("Unit") or structure.unit).lower()
    return None


def _parse_hko_row_date(raw_value: Any, *, year: int, month: int) -> str | None:
    if raw_value is None:
        return None
    text = str(raw_value).strip()
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    if text.isdigit():
        try:
            return datetime(year, month, int(text)).date().isoformat()
        except ValueError:
            return None
    return None


def _extract_hko_row_value(row: dict[str, Any], structure: MarketStructure) -> float | None:
    preferred_keys = (
        ("max", "maximum", "maxt", "tempmax", "value")
        if structure.measurement_kind == "high"
        else ("min", "minimum", "mint", "tempmin", "value")
    )
    lowered = {str(key).lower(): value for key, value in row.items()}
    for key in preferred_keys:
        if key in lowered and lowered[key] not in {None, "", "-"}:
            return float(lowered[key])
    return None


def _parse_meteostat_row_date(raw_value: Any) -> str | None:
    if raw_value is None:
        return None
    text = str(raw_value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text[:10], fmt).date().isoformat()
        except ValueError:
            pass
    return None


def _extract_meteostat_row_value(row: dict[str, Any], structure: MarketStructure) -> float | None:
    preferred_keys = ("tmax", "max", "tempmax") if structure.measurement_kind == "high" else ("tmin", "min", "tempmin")
    lowered = {str(key).lower(): value for key, value in row.items()}
    for key in preferred_keys:
        if key in lowered and lowered[key] not in {None, "", "-"}:
            return float(lowered[key])
    return None


_DIRECT_API_PROVIDERS = {
    "weatherapi",
    "visual_crossing",
    "weatherbit",
    "tomorrow_io",
    "meteoblue",
    "open_meteo",
    "openweather",
    "yr_no",
    "world_weather_online",
    "meteomatics",
    "weatherlink",
    "ambient_weather",
    "netatmo",
    "windy",
    "aerisweather",
    "meteo_france",
}
_DIRECT_SOURCE_PROVIDERS = {
    "uk_met_office",
    "dwd",
    "bom",
    "jma",
    "pagasa",
    "imd",
    "meteoswiss",
    "smhi",
    "knmi",
    "aemet",
    "met_eireann",
    "dmi",
    "meteochile",
    "inmet",
    "senamhi_peru",
    "ideam_colombia",
    "smn_argentina",
    "smn_mexico",
    "environment_canada",
    "web_scrape",
    "local_official_weather_source",
}


def _latency_tier_for_provider(provider: str) -> str:
    if provider == "ecmwf_copernicus":
        return "fallback_reanalysis"
    if provider in {"web_scrape", "local_official_weather_source"}:
        return "scrape_target"
    if provider in _DIRECT_API_PROVIDERS:
        return "direct_api"
    return "direct_history"


def _extract_rows(payload: Any) -> list[Any]:
    if isinstance(payload, str):
        return list(csv.DictReader(payload.splitlines()))
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    if set(payload.keys()).issubset({"content", "text", "html", "body"}):
        body = payload.get("body")
        return body if isinstance(body, list) else []

    if isinstance(payload.get("features"), list):
        rows: list[Any] = []
        for feature in payload["features"]:
            if isinstance(feature, dict) and isinstance(feature.get("properties"), dict):
                rows.append(feature["properties"])
        if rows:
            return rows

    siterep = payload.get("SiteRep")
    if isinstance(siterep, dict):
        period = (((siterep.get("DV") or {}).get("Location") or {}).get("Period"))
        rows: list[dict[str, Any]] = []
        if isinstance(period, list):
            for item in period:
                if not isinstance(item, dict):
                    continue
                date = str(item.get("value") or "").replace("Z", "")
                reps = item.get("Rep")
                if isinstance(reps, list):
                    for rep in reps:
                        if isinstance(rep, dict):
                            rows.append({**rep, "date": date, "unit": "C"})
        return rows

    daily = payload.get("daily")
    if isinstance(daily, dict):
        rows = _rows_from_columnar_daily(daily)
        if rows:
            return rows
    current_weather = payload.get("current_weather")
    if isinstance(current_weather, dict):
        return [current_weather]
    properties = payload.get("properties")
    if isinstance(properties, dict) and isinstance(properties.get("timeseries"), list):
        return properties["timeseries"]
    for key in ("observations", "data", "daily", "history", "records", "rows", "climateData", "list", "value", "datos"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    forecast = payload.get("forecast")
    if isinstance(forecast, dict) and isinstance(forecast.get("forecastday"), list):
        return forecast["forecastday"]
    if isinstance(payload.get("forecastday"), list):
        return payload["forecastday"]
    if isinstance(payload.get("DailyForecasts"), list):
        return payload["DailyForecasts"]
    if isinstance(payload.get("days"), list):
        return payload["days"]
    timelines = payload.get("data", {}).get("timelines") if isinstance(payload.get("data"), dict) else None
    if isinstance(timelines, list):
        rows: list[Any] = []
        for timeline in timelines:
            if isinstance(timeline, dict) and isinstance(timeline.get("intervals"), list):
                rows.extend(timeline["intervals"])
        return rows
    current = payload.get("current") or payload.get("currentConditions") or payload.get("main")
    if isinstance(current, dict):
        row = dict(current)
        for key in ("dt", "dt_txt", "time", "timestamp"):
            if key in payload and key not in row:
                row[key] = payload[key]
        return [row]
    return [payload]




def _row_matches_station(row: dict[str, Any], station_code: str) -> bool:
    keys = ("station", "station_id", "stationID", "STATION", "id")
    present = [str(row.get(key)) for key in keys if row.get(key) is not None]
    return not present or station_code in present


def _extract_row_timestamp(row: dict[str, Any]) -> str:
    for key in ("timestamp", "time", "datetime", "date", "Date", "fecha", "Fecha", "DT_MEDICAO", "startTime", "LocalObservationDateTime", "obsTime", "obsTimeUtc", "obsTimeLocal", "MESS_DATUM", "reference_ts", "fint", "observed"):
        value = row.get(key)
        if value not in {None, ""}:
            text = str(value)
            if key == "MESS_DATUM" and text.isdigit() and len(text) == 8:
                return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
            return text[:10] if key in {"Date"} else text
    for key in ("ts", "dateutc", "epoch", "dt"):
        value = row.get(key)
        if value not in {None, ""}:
            return str(value)
    return ""


def _row_has_explicit_timestamp(row: dict[str, Any]) -> bool:
    timestamp_keys = (
        "timestamp",
        "time",
        "datetime",
        "date",
        "Date",
        "fecha",
        "Fecha",
        "DT_MEDICAO",
        "startTime",
        "LocalObservationDateTime",
        "obsTime",
        "obsTimeUtc",
        "obsTimeLocal",
        "MESS_DATUM",
        "reference_ts",
        "fint",
        "observed",
        "ts",
        "dateutc",
        "epoch",
        "dt",
    )
    return any(row.get(key) not in {None, ""} for key in timestamp_keys)


def _normalize_date(timestamp: str) -> str | None:
    text = str(timestamp).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text[:10] if fmt == "%Y-%m-%d" else text[:8], fmt).date().isoformat()
        except ValueError:
            pass
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    return None


def _extract_generic_temperature(row: dict[str, Any], structure: MarketStructure) -> tuple[float, str] | None:
    day = row.get("day") if isinstance(row.get("day"), dict) else None
    values = row.get("values") if isinstance(row.get("values"), dict) else None
    data = row.get("data") if isinstance(row.get("data"), dict) else None
    instant_details = (((data or {}).get("instant") or {}).get("details")) if data else None
    next_6h_details = (((data or {}).get("next_6_hours") or {}).get("details")) if data else None
    main = row.get("main") if isinstance(row.get("main"), dict) else None
    measurements = row.get("measurements") if isinstance(row.get("measurements"), dict) else None
    candidates: list[dict[str, Any]] = [row]
    if day: candidates.append(day)
    if values: candidates.append(values)
    if data:
        candidates.append(data)
    if isinstance(instant_details, dict):
        candidates.append(instant_details)
    if isinstance(next_6h_details, dict):
        candidates.append(next_6h_details)
    if main:
        candidates.append(main)
    if measurements:
        candidates.append(measurements)
    temp = row.get("Temperature") or row.get("temperature")
    if isinstance(temp, dict):
        if temp.get("value") is not None:
            return float(temp["value"]), str(temp.get("unit") or temp.get("unitCode") or structure.unit).lower()
        if structure.measurement_kind == "high":
            nested = temp.get("Maximum") or temp.get("maximum")
        elif structure.measurement_kind == "low":
            nested = temp.get("Minimum") or temp.get("minimum")
        else:
            nested = temp.get("Metric") or temp.get("Imperial") or temp
        if isinstance(nested, dict) and nested.get("Value") is not None:
            return float(nested["Value"]), str(nested.get("Unit") or structure.unit).lower()
    key_groups = {
        "high": ("maxtemp_f", "maxtemp_c", "max_temp", "tmax", "TXK", "TX", "tre200s0", "ta", "temperaturaMaxima", "TEM_MAX", "Valor", "tempmax", "temperatureMax", "maxTemp", "temperature_2m_max", "temp_max", "air_temperature_max", "maxtempC", "maxtempF"),
        "low": ("mintemp_f", "mintemp_c", "min_temp", "tmin", "TNK", "TN", "tre200s0", "ta", "temperaturaMinima", "TEM_MIN", "Valor", "tempmin", "temperatureMin", "minTemp", "temperature_2m_min", "temp_min", "air_temperature_min", "mintempC", "mintempF"),
        "current": ("temp_f", "temp_c", "tempf", "tempc", "temp", "current", "temperature", "temperatura", "T", "TX", "TN", "tre200s0", "ta", "Valor", "value", "temperature_2m", "air_temperature", "temperatureC", "temperatureF"),
    }
    keys = key_groups.get(structure.measurement_kind, key_groups["current"]) + key_groups["current"]
    temperature_fields = {"temperature"}
    if structure.measurement_kind == "current":
        temperature_fields.add("current")
    for mapping in candidates:
        lowered = {str(k).lower(): (k, v) for k, v in mapping.items()}
        for key in keys:
            item = lowered.get(key.lower())
            if item is None:
                continue
            original_key, value = item
            if isinstance(value, dict) and str(original_key).lower() in temperature_fields:
                nested_value = value.get("value") or value.get("Value")
                if nested_value not in {None, "", "-"}:
                    unit = str(value.get("unit") or value.get("Unit") or value.get("unitCode") or structure.unit).lower()
                    return float(nested_value), unit
            if value is None or value == "" or value == "-" or isinstance(value, dict):
                continue
            key_lower = str(original_key).lower()
            unit = str(
                mapping.get("unit")
                or mapping.get("Unit")
                or ("F" if key_lower.endswith("_f") or key_lower.endswith("f") else "C" if key_lower.endswith("_c") or key_lower.endswith("c") or "temperature_2m" in key_lower or "air_temperature" in key_lower or key_lower in {"tre200s0", "ta"} else structure.unit)
            ).lower()
            numeric_value = float(value)
            if unit in {"0.1c", "1/10c", "deci_c", "decic"}:
                numeric_value = numeric_value / 10
                unit = "c"
            return numeric_value, unit
    return None


def _rows_from_columnar_daily(daily: dict[str, Any]) -> list[dict[str, Any]]:
    times = daily.get("time") or daily.get("date") or daily.get("dates")
    if not isinstance(times, list):
        return []
    rows: list[dict[str, Any]] = []
    for index, timestamp in enumerate(times):
        row: dict[str, Any] = {"date": timestamp}
        for key, value in daily.items():
            if isinstance(value, list) and index < len(value):
                row[key] = value[index]
        rows.append(row)
    return rows
