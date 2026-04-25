from __future__ import annotations

from weather_pm.history_client import StationHistoryClient, build_station_history_bundle
from weather_pm.market_parser import parse_market_question
from weather_pm.resolution_parser import parse_resolution_metadata


class _FakeStationHistoryClient(StationHistoryClient):
    def __init__(self, payloads: list[dict[str, object]]) -> None:
        super().__init__(timeout=0.1)
        self.requested_urls: list[str] = []
        self._payloads = list(payloads)

    def _fetch_json(self, url: str) -> dict[str, object]:
        self.requested_urls.append(url)
        if not self._payloads:
            raise AssertionError(f"unexpected extra fetch for {url}")
        return self._payloads.pop(0)


def test_station_history_client_fetches_noaa_station_observation_range() -> None:
    structure = parse_market_question("Will the highest temperature in Denver be 64F or higher on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="Resolution source: NOAA daily climate report for station KDEN",
        description="Official observed high temperature at Denver International Airport station KDEN.",
        rules="Source: https://www.weather.gov/wrh/climate?wfo=bou station KDEN.",
    )
    client = _FakeStationHistoryClient(
        [
            {
                "features": [
                    {"properties": {"timestamp": "2026-04-24T12:00:00+00:00", "temperature": {"value": 18.0, "unitCode": "wmoUnit:degC"}}},
                    {"properties": {"timestamp": "2026-04-25T12:00:00+00:00", "temperature": {"value": 20.0, "unitCode": "wmoUnit:degC"}}},
                ]
            }
        ]
    )

    bundle = client.fetch_history_bundle(structure, resolution, start_date="2026-04-24", end_date="2026-04-25")

    assert client.requested_urls == [
        "https://api.weather.gov/stations/KDEN/observations?start=2026-04-24T00%3A00%3A00Z&end=2026-04-25T23%3A59%3A59Z"
    ]
    assert bundle.source_provider == "noaa"
    assert bundle.station_code == "KDEN"
    assert bundle.latency_tier == "direct"
    assert [point.timestamp for point in bundle.points] == ["2026-04-24T12:00:00+00:00", "2026-04-25T12:00:00+00:00"]
    assert [point.value for point in bundle.points] == [64.4, 68.0]
    assert bundle.summary["max"] == 68.0
    assert bundle.summary["min"] == 64.4


def test_station_history_client_fetches_wunderground_history_url_for_station_and_day() -> None:
    structure = parse_market_question("Will the lowest temperature in Miami be 63°F or below on April 23?")
    resolution = parse_resolution_metadata(
        resolution_source="https://www.wunderground.com/history/daily/us/fl/miami/KMIA",
        description=(
            "This market will resolve to the temperature range that contains the lowest "
            "temperature recorded at the Miami Intl Airport Station in degrees Fahrenheit on 23 Apr '26."
        ),
        rules="This market resolves based on the final daily observation published at the resolution source.",
    )
    client = _FakeStationHistoryClient(
        [
            {
                "observations": [
                    {"obsTimeLocal": "2026-04-23 01:00:00", "metric": {"temp": 19.0}},
                    {"obsTimeLocal": "2026-04-23 06:00:00", "metric": {"temp": 17.0}},
                    {"obsTimeLocal": "2026-04-23 15:00:00", "metric": {"temp": 27.0}},
                ]
            }
        ]
    )

    bundle = client.fetch_history_bundle(structure, resolution, start_date="2026-04-23", end_date="2026-04-23")

    assert client.requested_urls == ["https://www.wunderground.com/history/daily/us/fl/miami/KMIA/date/2026-04-23"]
    assert bundle.source_provider == "wunderground"
    assert bundle.station_code == "KMIA"
    assert bundle.latency_tier == "direct"
    assert [point.value for point in bundle.points] == [66.2, 62.6, 80.6]
    assert bundle.summary["min"] == 62.6
    assert bundle.summary["max"] == 80.6


def test_build_station_history_bundle_returns_empty_fallback_when_source_has_no_direct_history_route() -> None:
    structure = parse_market_question("Will the highest temperature in Hong Kong be 31C or higher on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="https://www.weather.gov.hk/en/cis/climat.htm",
        description="This market resolves to the highest temperature recorded by the Hong Kong Observatory.",
        rules="The resolution source for this market will be information from the Hong Kong Observatory.",
    )

    bundle = build_station_history_bundle(structure, resolution, start_date="2026-04-24", end_date="2026-04-25")

    assert bundle.source_provider == "hong_kong_observatory"
    assert bundle.station_code is None
    assert bundle.latency_tier == "unsupported"
    assert bundle.points == []
    assert bundle.summary == {}
