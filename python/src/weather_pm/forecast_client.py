from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import quote, urlencode
from urllib.request import urlopen

from weather_pm.models import ForecastBundle, MarketStructure, ResolutionMetadata


def build_forecast_bundle(
    structure: MarketStructure,
    *,
    live: bool = False,
    client: OpenMeteoForecastClient | None = None,
    resolution: ResolutionMetadata | None = None,
    direct_client: DirectStationForecastClient | None = None,
) -> ForecastBundle:
    if not live:
        return build_synthetic_forecast_bundle(structure)

    direct_target = _direct_resolution_target(resolution)
    if resolution is not None:
        station_client = direct_client or DirectStationForecastClient()
        try:
            return station_client.build_forecast_bundle(structure, resolution)
        except Exception:
            pass

    forecast_client = client or OpenMeteoForecastClient()
    try:
        bundle = forecast_client.build_forecast_bundle(structure)
        if direct_target is not None:
            return _bundle_with_resolution_target(bundle, direct_target)
        return bundle
    except Exception:
        bundle = build_synthetic_forecast_bundle(structure)
        if direct_target is not None:
            return _bundle_with_resolution_target(bundle, direct_target)
        return bundle


def build_synthetic_forecast_bundle(structure: MarketStructure) -> ForecastBundle:
    consensus_value = structure.target_value if structure.target_value is not None else ((structure.range_low or 0.0) + (structure.range_high or 0.0)) / 2
    if structure.is_threshold:
        threshold_shift = -0.2 if structure.threshold_direction == "below" else 0.2
        consensus_value += threshold_shift
    return ForecastBundle(
        source_count=3,
        consensus_value=consensus_value,
        dispersion=1.2 if structure.is_threshold else 1.8,
        historical_station_available=True,
    )


@dataclass(slots=True)
class _GeoPoint:
    latitude: float
    longitude: float
    timezone: str


class DirectStationForecastClient:
    def __init__(self, *, timeout: float = 10.0) -> None:
        self.timeout = timeout

    def build_forecast_bundle(self, structure: MarketStructure, resolution: ResolutionMetadata) -> ForecastBundle:
        if resolution.provider == "noaa" and resolution.station_code:
            url = f"https://api.weather.gov/stations/{resolution.station_code}/observations/latest"
            payload = self._fetch_json(url)
            value = self._extract_noaa_value(structure, payload)
            return self._bundle(structure, resolution, value=value, url=url)

        if resolution.provider == "wunderground" and resolution.source_url and resolution.station_code:
            payload = self._fetch_json(resolution.source_url)
            value = self._extract_wunderground_value(structure, payload)
            return self._bundle(structure, resolution, value=value, url=resolution.source_url)

        if resolution.provider == "hong_kong_observatory":
            url = "https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=rhrread&lang=en"
            payload = self._fetch_json(url)
            value = self._extract_hko_value(structure, payload)
            return self._bundle(structure, resolution, value=value, url=url)

        if resolution.provider == "aviation_weather" and resolution.station_code:
            from weather_pm.history_client import StationHistoryClient

            url = f"https://aviationweather.gov/api/data/metar?ids={quote(resolution.station_code)}&format=json&taf=false"
            payload = self._fetch_json(url)
            points = StationHistoryClient()._parse_aviation_weather_points(structure, payload)
            if not points:
                raise ValueError("AviationWeather payload missing parseable temperature")
            return self._bundle(structure, resolution, value=points[-1].value, url=url)

        if resolution.provider in _DIRECT_API_FORECAST_PROVIDERS and resolution.source_url:
            from weather_pm.history_client import StationHistoryClient

            payload = self._fetch_json(resolution.source_url)
            points = StationHistoryClient()._parse_generic_weather_points(structure, resolution, payload, latest=True)
            if not points:
                raise ValueError(f"{resolution.provider} direct API payload missing parseable temperature")
            return self._bundle(structure, resolution, value=points[-1].value, url=resolution.source_url, latency_tier="direct_api")

        if resolution.provider in _DIRECT_OFFICIAL_FORECAST_PROVIDERS and resolution.source_url:
            from weather_pm.history_client import StationHistoryClient, _latency_tier_for_provider

            payload = self._fetch_json(resolution.source_url)
            points = StationHistoryClient()._parse_generic_weather_points(structure, resolution, payload, latest=True)
            if not points:
                raise ValueError(f"{resolution.provider} official source payload missing parseable temperature")
            return self._bundle(
                structure,
                resolution,
                value=points[-1].value,
                url=resolution.source_url,
                latency_tier=_latency_tier_for_provider(resolution.provider),
            )

        raise ValueError(f"no direct station route for provider={resolution.provider!r}")

    def _bundle(self, structure: MarketStructure, resolution: ResolutionMetadata, *, value: float, url: str, latency_tier: str = "direct") -> ForecastBundle:
        return ForecastBundle(
            source_count=1,
            consensus_value=round(value, 2),
            dispersion=0.8 if structure.unit == "c" else 1.5,
            historical_station_available=True,
            source_provider=resolution.provider,
            source_station_code=resolution.station_code,
            source_url=url,
            source_latency_tier=latency_tier,
        )

    def _extract_noaa_value(self, structure: MarketStructure, payload: dict[str, Any]) -> float:
        properties = payload.get("properties")
        if not isinstance(properties, dict):
            raise ValueError("NOAA payload missing properties")
        if structure.measurement_kind == "low":
            raw_value = self._extract_unit_value(properties, "minTemperatureLast24Hours")
            if raw_value is not None:
                return _convert_temperature(raw_value, from_unit="c", to_unit=structure.unit)
        raw_value = self._extract_unit_value(properties, "temperature")
        if raw_value is None:
            raise ValueError("NOAA payload missing temperature")
        return _convert_temperature(raw_value, from_unit="c", to_unit=structure.unit)

    def _extract_wunderground_value(self, structure: MarketStructure, payload: dict[str, Any]) -> float:
        observations = payload.get("observations")
        if not isinstance(observations, list) or not observations:
            raise ValueError("Wunderground payload missing observations")
        metric_values: list[float] = []
        imperial_values: list[float] = []
        metric_key = "tempLow" if structure.measurement_kind == "low" else "tempHigh"
        imperial_key = "tempLow" if structure.measurement_kind == "low" else "tempHigh"
        for observation in observations:
            if not isinstance(observation, dict):
                continue
            metric = observation.get("metric")
            if isinstance(metric, dict) and metric.get(metric_key) is not None:
                metric_values.append(float(metric[metric_key]))
            imperial = observation.get("imperial")
            if isinstance(imperial, dict) and imperial.get(imperial_key) is not None:
                imperial_values.append(float(imperial[imperial_key]))
        if imperial_values:
            source_unit = "f"
            value = min(imperial_values) if structure.measurement_kind == "low" else max(imperial_values)
        elif metric_values:
            source_unit = "c"
            value = min(metric_values) if structure.measurement_kind == "low" else max(metric_values)
        else:
            raise ValueError("Wunderground payload missing temperature extrema")
        return _convert_temperature(value, from_unit=source_unit, to_unit=structure.unit)

    def _extract_hko_value(self, structure: MarketStructure, payload: dict[str, Any]) -> float:
        temperature = payload.get("temperature")
        if not isinstance(temperature, dict):
            raise ValueError("HKO payload missing temperature")
        observations = temperature.get("data")
        if not isinstance(observations, list) or not observations:
            raise ValueError("HKO payload missing temperature observations")
        fallback_values: list[float] = []
        for observation in observations:
            if not isinstance(observation, dict):
                continue
            if observation.get("value") is None:
                continue
            value = _convert_temperature(float(observation["value"]), from_unit=str(observation.get("unit") or "C").lower(), to_unit=structure.unit)
            if str(observation.get("place") or "").strip().lower() == "hong kong observatory":
                return value
            fallback_values.append(value)
        if not fallback_values:
            raise ValueError("HKO payload missing numeric temperature observations")
        return min(fallback_values) if structure.measurement_kind == "low" else max(fallback_values)

    def _extract_unit_value(self, properties: dict[str, Any], key: str) -> float | None:
        entry = properties.get(key)
        if not isinstance(entry, dict) or entry.get("value") is None:
            return None
        return float(entry["value"])

    def _fetch_json(self, url: str) -> dict[str, Any]:
        with urlopen(url, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))


_DIRECT_API_FORECAST_PROVIDERS = {
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
_DIRECT_OFFICIAL_FORECAST_PROVIDERS = {
    "environment_canada",
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
    "south_african_weather_service",
    "nimet_nigeria",
    "egyptian_meteorological_authority",
    "israel_meteorological_service",
    "turkish_meteorological_service",
    "saudi_ncm",
    "kma_korea",
    "taiwan_cwa",
    "mss_singapore",
    "metmalaysia",
    "bmkg_indonesia",
    "tmd_thailand",
    "metservice_nz",
}


def _direct_resolution_target(resolution: ResolutionMetadata | None) -> ResolutionMetadata | None:
    if resolution is None:
        return None
    if resolution.provider in ({"noaa", "wunderground", "hong_kong_observatory", "aviation_weather"} | _DIRECT_API_FORECAST_PROVIDERS | _DIRECT_OFFICIAL_FORECAST_PROVIDERS) and (resolution.station_code or resolution.source_url or resolution.provider == "hong_kong_observatory"):
        return resolution
    return None


def _bundle_with_resolution_target(bundle: ForecastBundle, resolution: ResolutionMetadata) -> ForecastBundle:
    return ForecastBundle(
        source_count=bundle.source_count,
        consensus_value=bundle.consensus_value,
        dispersion=bundle.dispersion,
        historical_station_available=bundle.historical_station_available,
        source_provider=bundle.source_provider or resolution.provider,
        source_station_code=bundle.source_station_code or resolution.station_code,
        source_url=bundle.source_url or resolution.source_url,
        source_latency_tier=bundle.source_latency_tier if bundle.source_latency_tier != "fallback" else "resolution_direct_target",
    )


class OpenMeteoForecastClient:

    def __init__(self, *, timeout: float = 10.0) -> None:
        self.timeout = timeout

    def build_forecast_bundle(self, structure: MarketStructure) -> ForecastBundle:
        geo = self._lookup_city(structure.city)
        daily = self._fetch_daily_forecast(geo)
        day_index = self._resolve_forecast_day_index(structure, daily)
        consensus_value = self._extract_consensus_value(structure, daily, day_index=day_index)
        dispersion = self._extract_dispersion(structure, daily, day_index=day_index)
        return ForecastBundle(
            source_count=1,
            consensus_value=round(consensus_value, 2),
            dispersion=round(dispersion, 2),
            historical_station_available=False,
        )

    def _lookup_city(self, city: str) -> _GeoPoint:
        query = urlencode({"name": city, "count": 1, "language": "en", "format": "json"})
        payload = self._fetch_json(f"https://geocoding-api.open-meteo.com/v1/search?{query}")
        results = payload.get("results")
        if not isinstance(results, list) or not results:
            raise ValueError(f"no geocoding result for city: {city}")
        first = results[0]
        return _GeoPoint(
            latitude=float(first["latitude"]),
            longitude=float(first["longitude"]),
            timezone=str(first.get("timezone") or "UTC"),
        )

    def _fetch_daily_forecast(self, geo: _GeoPoint) -> dict[str, Any]:
        query = urlencode(
            {
                "latitude": geo.latitude,
                "longitude": geo.longitude,
                "daily": "temperature_2m_max,temperature_2m_min",
                "forecast_days": 16,
                "timezone": geo.timezone,
            }
        )
        payload = self._fetch_json(f"https://api.open-meteo.com/v1/forecast?{query}")
        daily = payload.get("daily")
        if not isinstance(daily, dict):
            raise ValueError("open-meteo daily forecast payload missing")
        return daily

    def _resolve_forecast_day_index(self, structure: MarketStructure, daily: dict[str, Any]) -> int:
        if not structure.date_local:
            return 0
        series = daily.get("time")
        if not isinstance(series, list) or not series:
            return 0
        target = _normalize_market_date(structure.date_local)
        if target is None:
            return 0
        for index, raw_value in enumerate(series):
            if raw_value == target:
                return index
        return 0

    def _extract_consensus_value(self, structure: MarketStructure, daily: dict[str, Any], *, day_index: int) -> float:
        key = "temperature_2m_max" if structure.measurement_kind == "high" else "temperature_2m_min"
        series = daily.get(key)
        if not isinstance(series, list) or not series:
            raise ValueError(f"open-meteo series missing: {key}")
        safe_index = min(day_index, len(series) - 1)
        value_c = float(series[safe_index])
        return _convert_temperature(value_c, from_unit="c", to_unit=structure.unit)

    def _extract_dispersion(self, structure: MarketStructure, daily: dict[str, Any], *, day_index: int) -> float:
        highs = daily.get("temperature_2m_max")
        lows = daily.get("temperature_2m_min")
        if not isinstance(highs, list) or not highs or not isinstance(lows, list) or not lows:
            return 3.0 if structure.unit == "f" else 1.7
        high_index = min(day_index, len(highs) - 1)
        low_index = min(day_index, len(lows) - 1)
        daily_range_c = max(float(highs[high_index]) - float(lows[low_index]), 0.0)
        daily_range_in_unit = _convert_temperature_delta(daily_range_c, from_unit="c", to_unit=structure.unit)
        return max(daily_range_in_unit / 4.0, 0.8 if structure.unit == "c" else 1.5)

    def _fetch_json(self, url: str) -> dict[str, Any]:
        with urlopen(url, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))


def _normalize_market_date(raw_value: str, *, fallback_year: int = 2026) -> str | None:
    normalized = raw_value.strip()
    candidates = (
        (normalized, "%B %d, %Y"),
        (f"{normalized} {fallback_year}", "%B %d %Y"),
        (f"{normalized}, {fallback_year}", "%B %d, %Y"),
    )
    for candidate, pattern in candidates:
        try:
            parsed = datetime.strptime(candidate, pattern)
            return parsed.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None



def _convert_temperature(value: float, *, from_unit: str, to_unit: str) -> float:
    if from_unit == to_unit:
        return value
    if from_unit == "c" and to_unit == "f":
        return (value * 9.0 / 5.0) + 32.0
    if from_unit == "f" and to_unit == "c":
        return (value - 32.0) * 5.0 / 9.0
    raise ValueError(f"unsupported temperature conversion: {from_unit} -> {to_unit}")


def _convert_temperature_delta(value: float, *, from_unit: str, to_unit: str) -> float:
    if from_unit == to_unit:
        return value
    if from_unit == "c" and to_unit == "f":
        return value * 9.0 / 5.0
    if from_unit == "f" and to_unit == "c":
        return value * 5.0 / 9.0
    raise ValueError(f"unsupported delta conversion: {from_unit} -> {to_unit}")
