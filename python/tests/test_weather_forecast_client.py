from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from weather_pm.forecast_client import OpenMeteoForecastClient, build_forecast_bundle
from weather_pm.market_parser import parse_market_question


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
