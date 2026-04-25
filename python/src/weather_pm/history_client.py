from __future__ import annotations

import json
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
    def __init__(self, *, timeout: float = 10.0) -> None:
        self.timeout = timeout

    def fetch_history_bundle(
        self,
        structure: MarketStructure,
        resolution: ResolutionMetadata,
        *,
        start_date: str,
        end_date: str,
    ) -> StationHistoryBundle:
        if resolution.provider == "noaa" and resolution.station_code:
            url = self._build_noaa_history_url(resolution.station_code, start_date=start_date, end_date=end_date)
            payload = self._fetch_json(url)
            points = self._parse_noaa_points(structure, payload)
            return self._bundle(resolution, url=url, points=points)

        if resolution.provider == "wunderground" and resolution.source_url and resolution.station_code:
            url = self._build_wunderground_history_url(resolution.source_url, start_date=start_date, end_date=end_date)
            payload = self._fetch_json(url)
            points = self._parse_wunderground_points(structure, payload)
            return self._bundle(resolution, url=url, points=points)

        raise ValueError(f"no direct history route for provider={resolution.provider!r}")

    def _build_noaa_history_url(self, station_code: str, *, start_date: str, end_date: str) -> str:
        query = urlencode({"start": f"{start_date}T00:00:00Z", "end": f"{end_date}T23:59:59Z"})
        return f"https://api.weather.gov/stations/{quote(station_code)}/observations?{query}"

    def _build_wunderground_history_url(self, source_url: str, *, start_date: str, end_date: str) -> str:
        if start_date != end_date:
            raise ValueError("Wunderground direct history currently supports a single day per request")
        return f"{source_url.rstrip('/')}/date/{start_date}"

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
            temperature = properties.get("temperature")
            if not isinstance(temperature, dict) or temperature.get("value") is None:
                continue
            timestamp = str(properties.get("timestamp") or "")
            value = _convert_temperature(float(temperature["value"]), from_unit="c", to_unit=structure.unit)
            points.append(StationHistoryPoint(timestamp=timestamp, value=round(value, 2), unit=structure.unit))
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

    def _bundle(self, resolution: ResolutionMetadata, *, url: str, points: list[StationHistoryPoint]) -> StationHistoryBundle:
        return StationHistoryBundle(
            source_provider=resolution.provider,
            station_code=resolution.station_code,
            source_url=url,
            latency_tier="direct",
            points=points,
            summary=_summarize(points),
        )

    def _fetch_json(self, url: str) -> dict[str, Any]:
        with urlopen(url, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))


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
