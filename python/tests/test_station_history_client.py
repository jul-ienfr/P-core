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


def test_station_history_client_fetches_noaa_official_daily_summary_for_single_day_high() -> None:
    structure = parse_market_question("Will the highest temperature in Denver be 64F or higher on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="Resolution source: NOAA daily climate report for station KDEN",
        description="Official observed high temperature at Denver International Airport station KDEN.",
        rules="Source: NOAA/NWS daily climate summary for KDEN.",
    )
    client = _FakeStationHistoryClient(
        [
            [
                {"DATE": "2026-04-25", "STATION": "KDEN", "TMAX": "72", "TMIN": "39"},
            ]
        ]
    )

    bundle = client.fetch_history_bundle(structure, resolution, start_date="2026-04-25", end_date="2026-04-25")

    assert client.requested_urls == [
        "https://www.ncei.noaa.gov/access/services/data/v1?dataset=daily-summaries&stations=KDEN&startDate=2026-04-25&endDate=2026-04-25&format=json&units=standard&includeAttributes=false"
    ]
    assert bundle.source_provider == "noaa"
    assert bundle.station_code == "KDEN"
    assert bundle.latency_tier == "direct_history"
    assert bundle.polling_focus == "noaa_official_daily_summary"
    assert bundle.expected_lag_seconds == 86400
    assert bundle.points[0].timestamp == "2026-04-25"
    assert bundle.points[0].value == 72.0
    assert bundle.summary["max"] == 72.0
    assert bundle.summary["point_count"] == 1.0



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


def test_station_history_client_fetches_aviation_weather_latest_metar_observation() -> None:
    structure = parse_market_question("Will the highest temperature in Denver be 64F or higher on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="METAR airport observations for station KDEN",
        description="Official observed high temperature at Denver International Airport station KDEN.",
        rules="Source: aviationweather.gov airport observations for station KDEN.",
    )
    client = _FakeStationHistoryClient(
        [
            [
                {"obsTime": "2026-04-25T18:53:00Z", "temp": 20.0, "tempUnits": "C"},
            ]
        ]
    )

    bundle = client.fetch_latest_bundle(structure, resolution)

    assert client.requested_urls == ["https://aviationweather.gov/api/data/metar?ids=KDEN&format=json&taf=false"]
    assert bundle.source_provider == "aviation_weather"
    assert bundle.station_code == "KDEN"
    assert bundle.latency_tier == "direct_latest"
    assert bundle.polling_focus == "aviation_weather_metar_observations"
    assert bundle.points[0].timestamp == "2026-04-25T18:53:00Z"
    assert bundle.points[0].value == 68.0
    assert bundle.summary["latest"] == 68.0


def test_station_history_client_summarizes_aviation_weather_history_observations() -> None:
    structure = parse_market_question("Will the lowest temperature in Miami be 63°F or below on April 23?")
    resolution = parse_resolution_metadata(
        resolution_source="Aviation weather METAR observations for station KMIA",
        description="Official airport observations at Miami station KMIA.",
        rules="Source: aviationweather.gov METAR data for station KMIA.",
    )
    client = _FakeStationHistoryClient(
        [
            {"data": [
                {"reportTime": "2026-04-23T01:53:00Z", "temp_c": 19.0},
                {"reportTime": "2026-04-23T06:53:00Z", "temperature": {"value": 17.0, "unit": "C"}},
                {"reportTime": "2026-04-23T15:53:00Z", "temp_f": 80.6},
            ]}
        ]
    )

    bundle = client.fetch_history_bundle(structure, resolution, start_date="2026-04-23", end_date="2026-04-23")

    assert client.requested_urls == [
        "https://aviationweather.gov/api/data/metar?ids=KMIA&format=json&taf=false&start=2026-04-23T00%3A00%3A00Z&end=2026-04-23T23%3A59%3A59Z"
    ]
    assert bundle.source_provider == "aviation_weather"
    assert bundle.station_code == "KMIA"
    assert bundle.latency_tier == "direct_history"
    assert [point.timestamp for point in bundle.points] == ["2026-04-23T01:53:00Z", "2026-04-23T06:53:00Z", "2026-04-23T15:53:00Z"]
    assert [point.value for point in bundle.points] == [66.2, 62.6, 80.6]
    assert bundle.summary["min"] == 62.6
    assert bundle.summary["max"] == 80.6
    assert bundle.summary["latest"] == 80.6


def test_station_history_client_fetches_hko_monthly_daily_maximum_extract_for_requested_day() -> None:
    structure = parse_market_question("Will the highest temperature in Hong Kong be 29°C or higher on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="https://www.hko.gov.hk/en/wxinfo/currwx/current.htm",
        description="This market resolves according to the official highest temperature recorded by the Hong Kong Observatory.",
        rules="Source: Hong Kong Observatory daily extract, finalized by weather.gov.hk.",
    )
    client = _FakeStationHistoryClient(
        [
            {
                "data": [
                    {"date": "20260424", "value": "28.4"},
                    {"date": "20260425", "value": "29.6"},
                ]
            }
        ]
    )

    bundle = client.fetch_history_bundle(structure, resolution, start_date="2026-04-25", end_date="2026-04-25")

    assert client.requested_urls == [
        "https://data.weather.gov.hk/weatherAPI/opendata/opendata.php?dataType=CLMMAXT&rformat=json&station=HKO&year=2026&month=4"
    ]
    assert bundle.source_provider == "hong_kong_observatory"
    assert bundle.station_code == "HKO"
    assert bundle.latency_tier == "direct_history"
    assert bundle.points[0].timestamp == "2026-04-25"
    assert bundle.points[0].value == 29.6
    assert bundle.summary["max"] == 29.6


def test_station_history_client_fetches_hko_latest_temperature_from_current_weather_api() -> None:
    structure = parse_market_question("Will the highest temperature in Hong Kong be 29°C or higher on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="https://www.hko.gov.hk/en/wxinfo/currwx/current.htm",
        description="This market resolves according to the official highest temperature recorded by the Hong Kong Observatory.",
        rules="Source: Hong Kong Observatory current weather and daily extract, finalized by weather.gov.hk.",
    )
    client = _FakeStationHistoryClient(
        [
            {
                "temperature": {"data": [{"place": "Hong Kong Observatory", "value": 29.2, "unit": "C"}]},
                "updateTime": "2026-04-25T08:45:00+08:00",
            }
        ]
    )

    bundle = client.fetch_latest_bundle(structure, resolution)

    assert client.requested_urls == [
        "https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=rhrread&lang=en"
    ]
    assert bundle.source_provider == "hong_kong_observatory"
    assert bundle.station_code == "HKO"
    assert bundle.latency_tier == "direct_latest"
    assert bundle.points[0].timestamp == "2026-04-25T08:45:00+08:00"
    assert bundle.points[0].value == 29.2
    assert bundle.summary["latest"] == 29.2


def test_station_history_client_parses_accuweather_daily_high_low_payload() -> None:
    structure = parse_market_question("Will the highest temperature in Miami be 82F or higher on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="https://www.accuweather.com/en/us/miami/33128/daily-weather-forecast/347936",
        description="This market resolves to the highest temperature observed for Miami on the linked AccuWeather page.",
        rules="Source: AccuWeather daily forecast page for location key 347936.",
    )
    client = _FakeStationHistoryClient(
        [
            {
                "DailyForecasts": [
                    {
                        "Date": "2026-04-25T07:00:00-04:00",
                        "Temperature": {"Minimum": {"Value": 73, "Unit": "F"}, "Maximum": {"Value": 84, "Unit": "F"}},
                    }
                ]
            }
        ]
    )

    bundle = client.fetch_history_bundle(structure, resolution, start_date="2026-04-25", end_date="2026-04-25")

    assert client.requested_urls == ["https://www.accuweather.com/en/us/miami/33128/daily-weather-forecast/347936?details=true"]
    assert bundle.source_provider == "accuweather"
    assert bundle.station_code == "347936"
    assert bundle.latency_tier == "direct_history"
    assert bundle.polling_focus == "accuweather_daily_payload"
    assert bundle.points[0].timestamp == "2026-04-25"
    assert bundle.points[0].value == 84.0
    assert bundle.summary["max"] == 84.0


def test_station_history_client_parses_accuweather_current_observation_payload() -> None:
    structure = parse_market_question("Will the lowest temperature in Miami be 73F or below on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="https://www.accuweather.com/en/us/miami/33128/current-weather/347936",
        description="This market resolves to the current observed temperature for Miami on AccuWeather.",
        rules="Source: AccuWeather current conditions page for location key 347936.",
    )
    client = _FakeStationHistoryClient(
        [
            {
                "LocalObservationDateTime": "2026-04-25T10:30:00-04:00",
                "Temperature": {"Imperial": {"Value": 75, "Unit": "F"}, "Metric": {"Value": 23.9, "Unit": "C"}},
            }
        ]
    )

    bundle = client.fetch_latest_bundle(structure, resolution)

    assert client.requested_urls == ["https://www.accuweather.com/en/us/miami/33128/current-weather/347936"]
    assert bundle.source_provider == "accuweather"
    assert bundle.station_code == "347936"
    assert bundle.latency_tier == "direct_latest"
    assert bundle.polling_focus == "accuweather_current_payload"
    assert bundle.points[0].timestamp == "2026-04-25T10:30:00-04:00"
    assert bundle.points[0].value == 75.0
    assert bundle.summary["latest"] == 75.0


def test_station_history_client_fetches_meteostat_daily_rows_for_station_high_in_market_unit() -> None:
    structure = parse_market_question("Will the highest temperature in Denver be 64F or higher on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="Resolution source: Meteostat daily data for station 72565",
        description="This market resolves to the highest temperature recorded in Denver.",
        rules="Use Meteostat daily tmax/tmin rows for station 72565.",
    )
    client = _FakeStationHistoryClient(
        [
            {
                "data": [
                    {"date": "2026-04-24", "tmax": 18.0, "tmin": 5.0},
                    {"date": "2026-04-25", "tmax": 20.0, "tmin": 7.0},
                ]
            }
        ]
    )

    bundle = client.fetch_history_bundle(structure, resolution, start_date="2026-04-24", end_date="2026-04-25")

    assert client.requested_urls == ["meteostat://daily?station=72565&start=2026-04-24&end=2026-04-25"]
    assert bundle.source_provider == "meteostat"
    assert bundle.station_code == "72565"
    assert bundle.latency_tier == "fallback_history"
    assert bundle.polling_focus == "meteostat_daily_history"
    assert [point.timestamp for point in bundle.points] == ["2026-04-24", "2026-04-25"]
    assert [point.value for point in bundle.points] == [64.4, 68.0]
    assert bundle.summary["max"] == 68.0


def test_station_history_client_fetches_meteostat_daily_rows_for_city_low_in_market_unit() -> None:
    structure = parse_market_question("Will the lowest temperature in Paris be 8C or below on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="Meteostat historical daily data",
        description="This market resolves to the lowest temperature in Paris.",
        rules="Use Meteostat daily tmax/tmin rows.",
    )
    client = _FakeStationHistoryClient(
        [
            {
                "data": [
                    {"time": "2026-04-25", "tmax": 16.2, "tmin": 7.4},
                ]
            }
        ]
    )

    bundle = client.fetch_history_bundle(structure, resolution, start_date="2026-04-25", end_date="2026-04-25")

    assert client.requested_urls == ["meteostat://daily?city=Paris&start=2026-04-25&end=2026-04-25"]
    assert bundle.source_provider == "meteostat"
    assert bundle.station_code is None
    assert bundle.latency_tier == "fallback_history"
    assert bundle.polling_focus == "meteostat_city_daily_history"
    assert bundle.points[0].timestamp == "2026-04-25"
    assert bundle.points[0].value == 7.4
    assert bundle.summary["min"] == 7.4


def test_build_station_history_bundle_returns_empty_fallback_when_source_has_no_direct_history_route() -> None:
    structure = parse_market_question("Will the highest temperature in Unknownville be 31C or higher on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="local weather station data",
        description="This market resolves to a local station only if public data is available.",
        rules="Data may come from a public weather page.",
    )

    bundle = build_station_history_bundle(structure, resolution, start_date="2026-04-24", end_date="2026-04-25")

    assert bundle.source_provider == "unknown"
    assert bundle.station_code is None
    assert bundle.latency_tier == "unsupported"
    assert bundle.points == []
    assert bundle.summary == {}
