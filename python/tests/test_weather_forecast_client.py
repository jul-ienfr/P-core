from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from weather_pm.forecast_client import DirectStationForecastClient, OpenMeteoForecastClient, build_forecast_bundle
from weather_pm.market_parser import parse_market_question
from weather_pm.resolution_parser import parse_resolution_metadata


class _FakeOpenMeteoClient(OpenMeteoForecastClient):
    def __init__(self, payloads: list[dict[str, object]]) -> None:
        super().__init__(timeout=0.1)
        self._payloads = list(payloads)

    def _fetch_json(self, url: str) -> dict[str, object]:
        assert url.startswith("https://")
        if not self._payloads:
            raise AssertionError(f"unexpected extra fetch for {url}")
        return self._payloads.pop(0)


class _FailingOpenMeteoClient(OpenMeteoForecastClient):
    def __init__(self) -> None:
        super().__init__(timeout=0.1)

    def _fetch_json(self, url: str) -> dict[str, object]:
        raise RuntimeError(f"boom for {url}")


class _FakeDirectStationClient(DirectStationForecastClient):
    def __init__(self, payload: dict[str, object]) -> None:
        super().__init__(timeout=0.1)
        self.payload = payload
        self.requested_urls: list[str] = []

    def _fetch_json(self, url: str) -> dict[str, object]:
        self.requested_urls.append(url)
        return self.payload


def test_open_meteo_client_builds_high_temperature_bundle_for_denver_in_fahrenheit() -> None:
    structure = parse_market_question("Will the highest temperature in Denver be 64F or higher?")
    client = _FakeOpenMeteoClient(
        [
            {
                "results": [
                    {
                        "name": "Denver",
                        "latitude": 39.7392,
                        "longitude": -104.9903,
                        "timezone": "America/Denver",
                    }
                ]
            },
            {
                "daily": {
                    "time": ["2026-04-24"],
                    "temperature_2m_max": [20.0],
                    "temperature_2m_min": [10.0],
                }
            },
        ]
    )

    bundle = client.build_forecast_bundle(structure)

    assert bundle.source_count == 1
    assert bundle.consensus_value == 68.0
    assert bundle.dispersion == 4.5
    assert bundle.historical_station_available is False


def test_open_meteo_client_uses_market_date_to_select_matching_forecast_day() -> None:
    structure = parse_market_question("Will the highest temperature in Denver be 64F or higher on April 25?")
    client = _FakeOpenMeteoClient(
        [
            {
                "results": [
                    {
                        "name": "Denver",
                        "latitude": 39.7392,
                        "longitude": -104.9903,
                        "timezone": "America/Denver",
                    }
                ]
            },
            {
                "daily": {
                    "time": ["2026-04-24", "2026-04-25"],
                    "temperature_2m_max": [20.0, 24.0],
                    "temperature_2m_min": [10.0, 14.0],
                }
            },
        ]
    )

    bundle = client.build_forecast_bundle(structure)

    assert bundle.consensus_value == 75.2
    assert bundle.dispersion == 4.5



def test_open_meteo_client_falls_back_to_first_forecast_day_when_market_date_is_not_present() -> None:
    structure = parse_market_question("Will the highest temperature in Denver be 64F or higher on April 27?")
    client = _FakeOpenMeteoClient(
        [
            {
                "results": [
                    {
                        "name": "Denver",
                        "latitude": 39.7392,
                        "longitude": -104.9903,
                        "timezone": "America/Denver",
                    }
                ]
            },
            {
                "daily": {
                    "time": ["2026-04-24", "2026-04-25"],
                    "temperature_2m_max": [20.0, 24.0],
                    "temperature_2m_min": [10.0, 14.0],
                }
            },
        ]
    )

    bundle = client.build_forecast_bundle(structure)

    assert bundle.consensus_value == 68.0
    assert bundle.dispersion == 4.5



def test_build_forecast_bundle_falls_back_to_synthetic_surface_when_live_lookup_fails() -> None:
    structure = parse_market_question("Will the highest temperature in Denver be 64F or higher?")

    bundle = build_forecast_bundle(structure, live=True, client=_FailingOpenMeteoClient())

    assert bundle.source_count == 3
    assert bundle.consensus_value == 64.2
    assert bundle.dispersion == 1.2
    assert bundle.historical_station_available is True


def test_direct_station_client_builds_hong_kong_observatory_bundle_from_current_weather() -> None:
    structure = parse_market_question("Will the highest temperature in Hong Kong be 29°C or higher on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="https://www.hko.gov.hk/en/wxinfo/currwx/current.htm",
        description="This market resolves according to the official highest temperature recorded by the Hong Kong Observatory.",
        rules="Source: Hong Kong Observatory daily extract, finalized by weather.gov.hk.",
    )
    client = _FakeDirectStationClient(
        {
            "temperature": {
                "recordTime": "2026-04-25T17:00:00+08:00",
                "data": [
                    {"place": "King's Park", "value": 26, "unit": "C"},
                    {"place": "Hong Kong Observatory", "value": 25, "unit": "C"},
                ],
            }
        }
    )

    bundle = client.build_forecast_bundle(structure, resolution)

    assert client.requested_urls == ["https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=rhrread&lang=en"]
    assert bundle.source_count == 1
    assert bundle.consensus_value == 25.0
    assert bundle.dispersion == 0.8
    assert bundle.historical_station_available is True
    assert bundle.source_provider == "hong_kong_observatory"
    assert bundle.source_station_code is None
    assert bundle.source_url == "https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=rhrread&lang=en"
    assert bundle.source_latency_tier == "direct"
