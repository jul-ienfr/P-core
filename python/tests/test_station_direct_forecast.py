from __future__ import annotations

from weather_pm.forecast_client import DirectStationForecastClient, build_forecast_bundle
from weather_pm.market_parser import parse_market_question
from weather_pm.resolution_parser import parse_resolution_metadata


class _FakeDirectStationClient(DirectStationForecastClient):
    def __init__(self, payloads: list[dict[str, object]]) -> None:
        super().__init__(timeout=0.1)
        self.requested_urls: list[str] = []
        self._payloads = list(payloads)

    def _fetch_json(self, url: str) -> dict[str, object]:
        self.requested_urls.append(url)
        if not self._payloads:
            raise AssertionError(f"unexpected extra fetch for {url}")
        return self._payloads.pop(0)


def test_direct_station_client_routes_noaa_station_to_station_observation_endpoint() -> None:
    structure = parse_market_question("Will the highest temperature in Denver be 64F or higher on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="Resolution source: NOAA daily climate report for station KDEN",
        description="Official observed high temperature at Denver International Airport station KDEN.",
        rules="Source: https://www.weather.gov/wrh/climate?wfo=bou station KDEN.",
    )
    client = _FakeDirectStationClient(
        [
            {
                "properties": {
                    "temperature": {"value": 20.0, "unitCode": "wmoUnit:degC"},
                    "minTemperatureLast24Hours": {"value": 7.0, "unitCode": "wmoUnit:degC"},
                    "timestamp": "2026-04-25T21:53:00+00:00",
                }
            }
        ]
    )

    bundle = client.build_forecast_bundle(structure, resolution)

    assert client.requested_urls == ["https://api.weather.gov/stations/KDEN/observations/latest"]
    assert bundle.consensus_value == 68.0
    assert bundle.source_count == 1
    assert bundle.historical_station_available is True
    assert bundle.source_provider == "noaa"
    assert bundle.source_station_code == "KDEN"
    assert bundle.source_latency_tier == "direct"


def test_direct_station_client_routes_wunderground_station_to_history_url_without_geocoding() -> None:
    structure = parse_market_question("Will the lowest temperature in Miami be 63°F or below on April 23?")
    resolution = parse_resolution_metadata(
        resolution_source="https://www.wunderground.com/history/daily/us/fl/miami/KMIA",
        description=(
            "This market will resolve to the temperature range that contains the lowest "
            "temperature recorded at the Miami Intl Airport Station in degrees Fahrenheit on 23 Apr '26."
        ),
        rules="This market resolves based on the final daily observation published at the resolution source.",
    )
    client = _FakeDirectStationClient(
        [
            {
                "observations": [
                    {"metric": {"tempHigh": 27.0, "tempLow": 17.0}, "obsTimeLocal": "2026-04-23 23:59:00"}
                ]
            }
        ]
    )

    bundle = client.build_forecast_bundle(structure, resolution)

    assert client.requested_urls == ["https://www.wunderground.com/history/daily/us/fl/miami/KMIA"]
    assert bundle.consensus_value == 62.6
    assert bundle.source_provider == "wunderground"
    assert bundle.source_station_code == "KMIA"
    assert bundle.source_latency_tier == "direct"


def test_build_forecast_bundle_prefers_direct_resolution_station_before_city_geocoding() -> None:
    structure = parse_market_question("Will the highest temperature in Denver be 64F or higher on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="Resolution source: NOAA daily climate report for station KDEN",
        description="Official observed high temperature at Denver International Airport station KDEN.",
        rules="Source: https://www.weather.gov/wrh/climate?wfo=bou station KDEN.",
    )
    client = _FakeDirectStationClient(
        [
            {
                "properties": {
                    "temperature": {"value": 20.0, "unitCode": "wmoUnit:degC"},
                    "timestamp": "2026-04-25T21:53:00+00:00",
                }
            }
        ]
    )

    bundle = build_forecast_bundle(structure, live=True, resolution=resolution, direct_client=client)

    assert client.requested_urls == ["https://api.weather.gov/stations/KDEN/observations/latest"]
    assert bundle.consensus_value == 68.0
    assert bundle.source_provider == "noaa"
    assert bundle.source_station_code == "KDEN"


def test_direct_station_client_routes_open_meteo_explicit_payload_without_city_geocoding() -> None:
    structure = parse_market_question("Will the highest temperature in Miami be 28C or higher on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="https://api.open-meteo.com/v1/forecast?latitude=25.76&longitude=-80.19&daily=temperature_2m_max,temperature_2m_min&current_weather=true",
        description="This market resolves to the highest temperature observed for Miami.",
        rules="Source: Open-Meteo API JSON payload.",
    )
    client = _FakeDirectStationClient(
        [
            {"current_weather": {"time": "2026-04-25T10:00", "temperature": 27.0}},
        ]
    )

    bundle = client.build_forecast_bundle(structure, resolution)

    assert client.requested_urls == [resolution.source_url]
    assert bundle.consensus_value == 27.0
    assert bundle.source_count == 1
    assert bundle.historical_station_available is True
    assert bundle.source_provider == "open_meteo"
    assert bundle.source_station_code is None
    assert bundle.source_url == resolution.source_url
    assert bundle.source_latency_tier == "direct_api"


def test_direct_station_client_routes_aviation_weather_metar_station_without_city_geocoding() -> None:
    structure = parse_market_question("Will the current temperature in Denver be 64F or higher on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="Resolution source: METAR airport observations for station KDEN",
        description="Official current temperature at Denver International Airport station KDEN.",
        rules="Source: https://aviationweather.gov/data/api/ station KDEN aviation weather observations.",
    )
    client = _FakeDirectStationClient(
        [
            {
                "data": [
                    {"obsTime": "2026-04-25T21:53:00Z", "temp_c": 20.0},
                ]
            }
        ]
    )

    bundle = client.build_forecast_bundle(structure, resolution)

    assert client.requested_urls == ["https://aviationweather.gov/api/data/metar?ids=KDEN&format=json&taf=false"]
    assert bundle.consensus_value == 68.0
    assert bundle.source_count == 1
    assert bundle.historical_station_available is True
    assert bundle.source_provider == "aviation_weather"
    assert bundle.source_station_code == "KDEN"
    assert bundle.source_latency_tier == "direct"


def test_build_forecast_bundle_preserves_direct_resolution_target_when_fetch_falls_back() -> None:
    class _FailingDirectClient(DirectStationForecastClient):
        def build_forecast_bundle(self, structure, resolution):
            raise RuntimeError("direct station unavailable")

    class _FailingCityClient:
        def build_forecast_bundle(self, structure):
            raise RuntimeError("city fallback unavailable")

    structure = parse_market_question("Will the highest temperature in Denver be 64F or higher on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="Resolution source: NOAA daily climate report for station KDEN",
        description="Official observed high temperature at Denver International Airport station KDEN.",
        rules="Source: https://www.weather.gov/wrh/climate?wfo=bou station KDEN.",
    )

    bundle = build_forecast_bundle(
        structure,
        live=True,
        resolution=resolution,
        direct_client=_FailingDirectClient(),
        client=_FailingCityClient(),
    )

    assert bundle.consensus_value == 64.2
    assert bundle.source_provider == "noaa"
    assert bundle.source_station_code == "KDEN"
    assert bundle.source_latency_tier == "resolution_direct_target"
