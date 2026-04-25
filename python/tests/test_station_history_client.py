from __future__ import annotations

from datetime import datetime, timezone

from weather_pm.history_client import StationHistoryClient, build_station_history_bundle
from weather_pm.market_parser import parse_market_question
from weather_pm.models import ResolutionMetadata
from weather_pm.resolution_parser import parse_resolution_metadata


class _FakeStationHistoryClient(StationHistoryClient):
    def __init__(self, payloads: list[dict[str, object]], *, now_utc: datetime | None = None) -> None:
        super().__init__(timeout=0.1, now_utc=now_utc)
        self.requested_urls: list[str] = []
        self._payloads = list(payloads)

    def _fetch_json(self, url: str) -> dict[str, object]:
        self.requested_urls.append(url)
        if not self._payloads:
            raise AssertionError(f"unexpected extra fetch for {url}")
        return self._payloads.pop(0)


def test_station_latest_client_reports_source_lag_seconds_for_noaa_direct_latest() -> None:
    structure = parse_market_question("Will the current temperature in Denver be 64F or higher on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="Resolution source: NOAA latest station observation for station KDEN",
        description="Official current temperature at Denver International Airport station KDEN.",
        rules="Source: https://api.weather.gov/stations/KDEN/observations/latest station KDEN.",
    )
    client = _FakeStationHistoryClient(
        [
            {
                "properties": {
                    "timestamp": "2026-04-25T21:53:00+00:00",
                    "temperature": {"value": 20.0, "unitCode": "wmoUnit:degC"},
                }
            }
        ],
        now_utc=datetime(2026, 4, 25, 22, 3, tzinfo=timezone.utc),
    )

    bundle = client.fetch_latest_bundle(structure, resolution)

    assert client.requested_urls == ["https://api.weather.gov/stations/KDEN/observations/latest"]
    assert bundle.source_provider == "noaa"
    assert bundle.station_code == "KDEN"
    assert bundle.latency_tier == "direct_latest"
    assert bundle.source_lag_seconds == 600
    assert bundle.latency_diagnostics()["source_lag_seconds"] == 600



def test_station_latest_client_parses_world_meteorological_observation_payloads() -> None:
    structure = parse_market_question("Will the current temperature in Riyadh be 34C or higher on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="https://ncm.gov.sa/api/observations/station/40437",
        description="This market resolves to the current temperature at Saudi NCM station 40437 in Riyadh.",
        rules="Source: Saudi National Center for Meteorology official observations API.",
    )
    client = _FakeStationHistoryClient(
        [
            {
                "observations": [
                    {"station": "40437", "obs_time": "2026-04-25T12:00:00Z", "airTemperature": {"value": 33.7, "unit": "C"}},
                ]
            }
        ],
        now_utc=datetime(2026, 4, 25, 12, 10, tzinfo=timezone.utc),
    )

    bundle = client.fetch_latest_bundle(structure, resolution)

    assert client.requested_urls == ["https://ncm.gov.sa/api/observations/station/40437"]
    assert bundle.source_provider == "saudi_ncm"
    assert bundle.station_code == "40437"
    assert bundle.latency_tier == "direct_history"
    assert bundle.points[0].timestamp == "2026-04-25T12:00:00Z"
    assert bundle.points[0].value == 33.7
    assert bundle.source_lag_seconds == 600



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



def test_station_latest_client_reports_source_lag_seconds_for_wunderground_direct_latest() -> None:
    structure = parse_market_question("Will the current temperature in Miami be 80°F or higher on April 23?")
    resolution = parse_resolution_metadata(
        resolution_source="https://www.wunderground.com/history/daily/us/fl/miami/KMIA",
        description="This market resolves to the current temperature recorded at Miami Intl Airport Station KMIA.",
        rules="This market resolves based on the latest observation published at the resolution source.",
    )
    client = _FakeStationHistoryClient(
        [
            {
                "observations": [
                    {"stationID": "KMIA", "obsTimeUtc": "2026-04-23T11:43:00Z", "imperial": {"temp": 80.0}},
                    {"stationID": "KMIA", "obsTimeUtc": "2026-04-23T11:53:00Z", "imperial": {"temp": 81.0}},
                ]
            }
        ],
        now_utc=datetime(2026, 4, 23, 12, 3, tzinfo=timezone.utc),
    )

    bundle = client.fetch_latest_bundle(structure, resolution)

    assert bundle.source_provider == "wunderground"
    assert bundle.station_code == "KMIA"
    assert bundle.latency_tier == "direct_latest"
    assert bundle.points[0].timestamp == "2026-04-23T11:53:00Z"
    assert bundle.source_lag_seconds == 600
    assert bundle.latency_diagnostics()["source_lag_seconds"] == 600



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


def test_station_history_client_parses_weather_com_injected_daily_payload() -> None:
    structure = parse_market_question("Will the highest temperature in Miami be 82F or higher on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="https://weather.com/weather/tenday/l/Miami+FL",
        description="This market resolves to the highest temperature observed for Miami on The Weather Channel page.",
        rules="Source: Weather.com / The Weather Channel daily details page.",
    )
    client = _FakeStationHistoryClient(
        [
            {
                "daily": [
                    {"date": "2026-04-25", "temperatureMax": 84, "temperatureMin": 73, "unit": "F"},
                ]
            }
        ]
    )

    bundle = client.fetch_history_bundle(structure, resolution, start_date="2026-04-25", end_date="2026-04-25")

    assert client.requested_urls == ["https://weather.com/weather/tenday/l/Miami+FL"]
    assert bundle.source_provider == "weather_com"
    assert bundle.latency_tier == "scrape_target"
    assert bundle.polling_focus == "weather_com_page_or_injected_payload"
    assert bundle.points[0].timestamp == "2026-04-25"
    assert bundle.points[0].value == 84.0
    assert bundle.summary["max"] == 84.0


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


def test_station_history_client_fetches_iem_asos_minute_archive_for_station_day() -> None:
    structure = parse_market_question("Will the highest temperature in Denver be 64F or higher on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="IEM ASOS archive for station KDEN",
        description="Official ASOS/METAR observed high temperature at Denver International Airport station KDEN.",
        rules="Source: https://mesonet.agron.iastate.edu/request/download.phtml station KDEN.",
    )
    client = _FakeStationHistoryClient(
        [
            "station,valid,tmpf\n"
            "KDEN,2026-04-25 12:53,62.6\n"
            "KDEN,2026-04-25 21:53,71.1\n"
        ]
    )

    bundle = client.fetch_history_bundle(structure, resolution, start_date="2026-04-25", end_date="2026-04-25")

    assert client.requested_urls == [
        "https://mesonet.agron.iastate.edu/request/download.phtml?station=KDEN&data=tmpf&year1=2026&month1=4&day1=25&year2=2026&month2=4&day2=25&tz=Etc%2FUTC&format=onlycomma&latlon=no&elev=no&missing=empty&trace=null&direct=no&report_type=1&report_type=2"
    ]
    assert bundle.source_provider == "iem_asos"
    assert bundle.station_code == "KDEN"
    assert bundle.latency_tier == "direct_history"
    assert bundle.polling_focus == "iem_asos_minute_archive"
    assert [point.timestamp for point in bundle.points] == ["2026-04-25 12:53", "2026-04-25 21:53"]
    assert [point.value for point in bundle.points] == [62.6, 71.1]
    assert bundle.summary["max"] == 71.1


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


def test_station_history_client_parses_weatherapi_latest_and_forecastday_payloads() -> None:
    structure = parse_market_question("Will the highest temperature in Miami be 82F or higher on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="https://api.weatherapi.com/v1/forecast.json?q=Miami&days=1",
        description="This market resolves to the highest temperature observed for Miami.",
        rules="Source: WeatherAPI.com forecast JSON.",
    )
    client = _FakeStationHistoryClient(
        [
            {"location": {"localtime": "2026-04-25 10:00"}, "current": {"temp_f": 80.0, "temp_c": 26.7}},
            {"forecast": {"forecastday": [{"date": "2026-04-25", "day": {"maxtemp_f": 84.0, "mintemp_f": 73.0, "avgtemp_f": 78.0}}]}},
        ]
    )

    latest = client.fetch_latest_bundle(structure, resolution)
    history = client.fetch_history_bundle(structure, resolution, start_date="2026-04-25", end_date="2026-04-25")

    assert client.requested_urls == [resolution.source_url, resolution.source_url]
    assert latest.source_provider == "weatherapi"
    assert latest.latency_tier == "direct_api"
    assert latest.polling_focus == "weatherapi_injected_payload"
    assert latest.points[0].value == 80.0
    assert history.points[0].timestamp == "2026-04-25"
    assert history.points[0].value == 84.0
    assert history.summary["max"] == 84.0


def test_station_history_client_parses_visual_crossing_days_payload() -> None:
    structure = parse_market_question("Will the lowest temperature in Miami be 73F or below on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/Miami/2026-04-25?unitGroup=us",
        description="This market resolves to the lowest temperature observed for Miami.",
        rules="Source: Visual Crossing timeline API.",
    )
    client = _FakeStationHistoryClient(
        [
            {"currentConditions": {"datetime": "2026-04-25T10:00:00", "temp": 78.0}, "days": [{"datetime": "2026-04-25", "tempmax": 84.0, "tempmin": 72.0, "temp": 78.0}]},
        ]
    )

    bundle = client.fetch_history_bundle(structure, resolution, start_date="2026-04-25", end_date="2026-04-25")

    assert client.requested_urls == [resolution.source_url]
    assert bundle.source_provider == "visual_crossing"
    assert bundle.latency_tier == "direct_api"
    assert bundle.polling_focus == "visual_crossing_injected_payload"
    assert bundle.points[0].value == 72.0
    assert bundle.summary["min"] == 72.0


def test_station_history_client_parses_weatherbit_data_payload() -> None:
    structure = parse_market_question("Will the highest temperature in Miami be 82F or higher on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="https://api.weatherbit.io/v2.0/history/daily?city=Miami&start_date=2026-04-25&end_date=2026-04-26&units=I",
        description="This market resolves to the highest temperature observed for Miami.",
        rules="Source: Weatherbit history API.",
    )
    client = _FakeStationHistoryClient(
        [
            {"data": [{"datetime": "2026-04-25", "max_temp": 84.0, "min_temp": 73.0, "temp": 78.0}]},
        ]
    )

    bundle = client.fetch_history_bundle(structure, resolution, start_date="2026-04-25", end_date="2026-04-25")

    assert client.requested_urls == [resolution.source_url]
    assert bundle.source_provider == "weatherbit"
    assert bundle.latency_tier == "direct_api"
    assert bundle.points[0].value == 84.0
    assert bundle.summary["max"] == 84.0


def test_station_history_client_parses_tomorrow_io_timelines_payload() -> None:
    structure = parse_market_question("Will the lowest temperature in Miami be 73F or below on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="https://api.tomorrow.io/v4/weather/history/recent?location=Miami&units=imperial",
        description="This market resolves to the lowest temperature observed for Miami.",
        rules="Source: Tomorrow.io timelines API.",
    )
    client = _FakeStationHistoryClient(
        [
            {"data": {"timelines": [{"intervals": [{"startTime": "2026-04-25T00:00:00Z", "values": {"temperatureMax": 84.0, "temperatureMin": 72.0, "temperature": 78.0}}]}]}},
        ]
    )

    bundle = client.fetch_history_bundle(structure, resolution, start_date="2026-04-25", end_date="2026-04-25")

    assert client.requested_urls == [resolution.source_url]
    assert bundle.source_provider == "tomorrow_io"
    assert bundle.latency_tier == "direct_api"
    assert bundle.points[0].value == 72.0
    assert bundle.summary["min"] == 72.0


def test_station_history_client_parses_meteoblue_simple_payloads() -> None:
    structure = parse_market_question("Will the highest temperature in Miami be 28C or higher on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="https://my.meteoblue.com/packages/basic-day?lat=25.76&lon=-80.19&units=metric",
        description="This market resolves to the highest temperature observed for Miami.",
        rules="Source: MeteoBlue basic day API.",
    )
    client = _FakeStationHistoryClient(
        [
            {"current": {"time": "2026-04-25T10:00:00Z", "temperature": 27.0}},
            {"history": [{"date": "2026-04-25", "temperatureMax": 29.0, "temperatureMin": 23.0, "temperature": 26.0}]},
        ]
    )

    latest = client.fetch_latest_bundle(structure, resolution)
    history = client.fetch_history_bundle(structure, resolution, start_date="2026-04-25", end_date="2026-04-25")

    assert client.requested_urls == [resolution.source_url, resolution.source_url]
    assert latest.source_provider == "meteoblue"
    assert latest.points[0].value == 27.0
    assert history.latency_tier == "direct_api"
    assert history.polling_focus == "meteoblue_injected_payload"
    assert history.points[0].value == 29.0


def test_station_history_client_parses_ecmwf_copernicus_reanalysis_daily_payload() -> None:
    structure = parse_market_question("Will the highest temperature in Paris be 20C or higher on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="Copernicus Climate Data Store reanalysis",
        description="This market resolves to the highest temperature recorded in Paris.",
        rules="Use ECMWF ERA5 reanalysis from cds.climate.copernicus.eu.",
    )
    client = _FakeStationHistoryClient(
        [
            {
                "daily": [
                    {"date": "2026-04-24", "tmax": 18.2, "tmin": 9.1},
                    {"date": "2026-04-25", "tmax": 21.4, "tmin": 10.0},
                ]
            }
        ]
    )

    bundle = client.fetch_history_bundle(structure, resolution, start_date="2026-04-24", end_date="2026-04-25")

    assert client.requested_urls == ["ecmwf_copernicus://reanalysis?city=Paris&start=2026-04-24&end=2026-04-25"]
    assert bundle.source_provider == "ecmwf_copernicus"
    assert bundle.latency_tier == "fallback_reanalysis"
    assert bundle.polling_focus == "ecmwf_copernicus_reanalysis_daily"
    assert [point.timestamp for point in bundle.points] == ["2026-04-24", "2026-04-25"]
    assert [point.value for point in bundle.points] == [18.2, 21.4]
    assert bundle.summary["max"] == 21.4


def test_station_history_client_parses_meteo_france_latest_and_daily_payloads_from_explicit_source() -> None:
    structure = parse_market_question("Will the lowest temperature in Paris be 8C or below on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="https://meteofrance.com/api/observations/paris",
        description="This market resolves to the lowest temperature recorded in Paris.",
        rules="Source: Météo-France official API endpoint supplied by operator.",
    )
    client = _FakeStationHistoryClient(
        [
            {"observations": [{"time": "2026-04-25T08:00:00+02:00", "temperature": {"value": 9.5, "unit": "C"}}]},
            {"daily": [{"date": "2026-04-25", "tmax": 16.1, "tmin": 7.2}]},
        ]
    )

    latest = client.fetch_latest_bundle(structure, resolution)
    history = client.fetch_history_bundle(structure, resolution, start_date="2026-04-25", end_date="2026-04-25")

    assert client.requested_urls == [
        "https://meteofrance.com/api/observations/paris",
        "https://meteofrance.com/api/observations/paris",
    ]
    assert latest.source_provider == "meteo_france"
    assert latest.latency_tier == "direct_latest"
    assert latest.points[0].timestamp == "2026-04-25T08:00:00+02:00"
    assert latest.points[0].value == 9.5
    assert history.latency_tier == "direct_history"
    assert history.polling_focus == "meteo_france_daily_payload"
    assert history.points[0].timestamp == "2026-04-25"
    assert history.points[0].value == 7.2


def test_station_history_client_parses_uk_met_office_daily_payload_from_explicit_source() -> None:
    structure = parse_market_question("Will the highest temperature in London be 17C or higher on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="https://www.metoffice.gov.uk/datapoint",
        description="This market resolves to the highest temperature recorded in London.",
        rules="Source: UK Met Office DataPoint endpoint supplied by operator.",
    )
    client = _FakeStationHistoryClient(
        [
            {
                "SiteRep": {
                    "DV": {
                        "Location": {
                            "Period": [
                                {"value": "2026-04-25Z", "Rep": [{"T": "14.1"}, {"T": "18.3"}, {"T": "12.2"}]}
                            ]
                        }
                    }
                }
            }
        ]
    )

    bundle = client.fetch_history_bundle(structure, resolution, start_date="2026-04-25", end_date="2026-04-25")

    assert client.requested_urls == ["https://www.metoffice.gov.uk/datapoint"]
    assert bundle.source_provider == "uk_met_office"
    assert bundle.latency_tier == "direct_history"
    assert bundle.polling_focus == "uk_met_office_daily_payload"
    assert bundle.points[0].timestamp == "2026-04-25"
    assert bundle.points[0].value == 18.3


def test_station_history_client_parses_dwd_open_data_daily_payload_from_source_url() -> None:
    structure = parse_market_question("Will the highest temperature in Berlin be 18C or higher on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="DWD Germany open-data observations for station 10384",
        description="This market resolves to the highest temperature recorded in Berlin.",
        rules="Source: https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/daily/kl/ station 10384.",
    )
    client = _FakeStationHistoryClient(
        [
            {
                "observations": [
                    {"MESS_DATUM": "20260424", "TXK": "17.8", "TNK": "7.3"},
                    {"MESS_DATUM": "20260425", "TXK": "19.6", "TNK": "8.1"},
                ]
            }
        ]
    )

    bundle = client.fetch_history_bundle(structure, resolution, start_date="2026-04-24", end_date="2026-04-25")

    assert client.requested_urls == ["https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/daily/kl/"]
    assert bundle.source_provider == "dwd"
    assert bundle.station_code == "10384"
    assert bundle.latency_tier == "direct_history"
    assert bundle.polling_focus == "dwd_open_data_daily_observations"
    assert [point.timestamp for point in bundle.points] == ["2026-04-24", "2026-04-25"]
    assert [point.value for point in bundle.points] == [17.8, 19.6]


def test_station_history_client_parses_bom_daily_json_payload() -> None:
    structure = parse_market_question("Will the highest temperature in Sydney be 25C or higher on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="Bureau of Meteorology station 066062",
        description="This market resolves to the official highest temperature observed at Sydney Observatory Hill station 066062.",
        rules="Source: https://www.bom.gov.au/products/IDN60801/IDN60801.94768.shtml official BOM observations.",
    )
    client = _FakeStationHistoryClient(
        [
            {
                "observations": [
                    {"date": "2026-04-25", "station": "066062", "max_temp": 25.6, "min_temp": 14.2, "unit": "C"},
                ]
            }
        ]
    )

    bundle = client.fetch_history_bundle(structure, resolution, start_date="2026-04-25", end_date="2026-04-25")

    assert client.requested_urls == ["https://www.bom.gov.au/products/IDN60801/IDN60801.94768.shtml"]
    assert bundle.source_provider == "bom"
    assert bundle.station_code == "066062"
    assert bundle.latency_tier == "direct_history"
    assert bundle.polling_focus == "bom_official_observations_or_injected_payload"
    assert bundle.points[0].timestamp == "2026-04-25"
    assert bundle.points[0].value == 25.6
    assert bundle.summary["max"] == 25.6


def test_station_history_client_parses_jma_daily_csv_payload() -> None:
    structure = parse_market_question("Will the lowest temperature in Tokyo be 12C or below on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="Japan Meteorological Agency station 44132",
        description="This market resolves to the lowest temperature recorded at Tokyo station 44132.",
        rules="Source: https://www.jma.go.jp/bosai/amedas/ official JMA observations.",
    )
    client = _FakeStationHistoryClient(
        [
            "date,station,tmax,tmin,current\n2026-04-25,44132,19.8,11.4,17.2\n",
        ]
    )

    bundle = client.fetch_history_bundle(structure, resolution, start_date="2026-04-25", end_date="2026-04-25")

    assert client.requested_urls == ["https://www.jma.go.jp/bosai/amedas/"]
    assert bundle.source_provider == "jma"
    assert bundle.station_code == "44132"
    assert bundle.latency_tier == "direct_history"
    assert bundle.polling_focus == "jma_official_amedas_or_injected_payload"
    assert bundle.points[0].timestamp == "2026-04-25"
    assert bundle.points[0].value == 11.4
    assert bundle.summary["min"] == 11.4


def test_station_history_client_parses_pagasa_latest_json_payload_when_source_url_is_present() -> None:
    structure = parse_market_question("Will the current temperature in Manila be 31C or higher on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="PAGASA official page",
        description="This market resolves to the current observed temperature at NAIA station 98429.",
        rules="Source: https://pagasa.dost.gov.ph/weather official observations.",
    )
    client = _FakeStationHistoryClient(
        [
            {"data": [{"timestamp": "2026-04-25T14:00:00+08:00", "station": "98429", "current": 32.1, "unit": "C"}]}
        ]
    )

    bundle = client.fetch_latest_bundle(structure, resolution)

    assert client.requested_urls == ["https://pagasa.dost.gov.ph/weather"]
    assert bundle.source_provider == "pagasa"
    assert bundle.station_code == "98429"
    assert bundle.latency_tier == "direct_latest"
    assert bundle.polling_focus == "pagasa_official_observations_or_injected_payload"
    assert bundle.points[0].timestamp == "2026-04-25T14:00:00+08:00"
    assert bundle.points[0].value == 32.1
    assert bundle.summary["latest"] == 32.1


def test_station_history_client_parses_imd_daily_json_payload() -> None:
    structure = parse_market_question("Will the highest temperature in Delhi be 38C or higher on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="IMD station 42182",
        description="This market resolves to the highest temperature recorded at New Delhi station 42182.",
        rules="Source: https://mausam.imd.gov.in/ official IMD observations.",
    )
    client = _FakeStationHistoryClient(
        [
            {"records": [{"date": "2026-04-25", "station_id": "42182", "tmax": 39.3, "tmin": 24.8, "unit": "C"}]}
        ]
    )

    bundle = client.fetch_history_bundle(structure, resolution, start_date="2026-04-25", end_date="2026-04-25")

    assert client.requested_urls == ["https://mausam.imd.gov.in/"]
    assert bundle.source_provider == "imd"
    assert bundle.station_code == "42182"
    assert bundle.latency_tier == "direct_history"
    assert bundle.polling_focus == "imd_official_observations_or_injected_payload"
    assert bundle.points[0].timestamp == "2026-04-25"
    assert bundle.points[0].value == 39.3
    assert bundle.summary["max"] == 39.3


def test_station_history_client_parses_environment_canada_climate_data_high_row() -> None:
    structure = parse_market_question("Will the highest temperature in Toronto be 18°C or higher on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="https://climate.weather.gc.ca/climateData/dailydata_e.html?StationID=51442",
        description="This market resolves to the highest temperature recorded in Toronto by Environment and Climate Change Canada.",
        rules="Use the finalized Environment Canada climateData daily row from climate.weather.gc.ca.",
    )
    client = _FakeStationHistoryClient(
        [
            {
                "climateData": [
                    {"date": "2026-04-24", "maxTemp": "17.4", "minTemp": "8.1", "meanTemp": "12.8"},
                    {"date": "2026-04-25", "maxTemp": "18.6", "minTemp": "7.9", "meanTemp": "13.3"},
                ]
            }
        ]
    )

    bundle = client.fetch_history_bundle(structure, resolution, start_date="2026-04-25", end_date="2026-04-25")

    assert client.requested_urls == [
        "https://climate.weather.gc.ca/climateData/dailydata_e.html?StationID=51442&timeframe=2&StartYear=1840&EndYear=2026&Year=2026&Month=4&Day=25"
    ]
    assert bundle.source_provider == "environment_canada"
    assert bundle.station_code == "51442"
    assert bundle.latency_tier == "direct_history"
    assert bundle.polling_focus == "environment_canada_official_history"
    assert bundle.points[0].timestamp == "2026-04-25"
    assert bundle.points[0].value == 18.6
    assert bundle.summary["max"] == 18.6


def test_station_history_client_parses_environment_canada_latest_climate_data_row() -> None:
    structure = parse_market_question("Will the lowest temperature in Toronto be 8°C or below on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="https://climate.weather.gc.ca/climateData/dailydata_e.html?StationID=51442",
        description="This market resolves to the lowest temperature recorded in Toronto by Environment Canada.",
        rules="Use the finalized Environment Canada climateData daily row from climate.weather.gc.ca.",
    )
    client = _FakeStationHistoryClient(
        [
            {
                "climateData": [
                    {"date": "2026-04-24", "maxTemp": "17.4", "minTemp": "8.1"},
                    {"date": "2026-04-25", "maxTemp": "18.6", "minTemp": "7.9"},
                ]
            }
        ]
    )

    bundle = client.fetch_latest_bundle(structure, resolution)

    assert client.requested_urls == ["https://climate.weather.gc.ca/climateData/dailydata_e.html?StationID=51442"]
    assert bundle.source_provider == "environment_canada"
    assert bundle.latency_tier == "direct_latest"
    assert bundle.polling_focus == "environment_canada_official_observation"
    assert bundle.points[0].timestamp == "2026-04-25"
    assert bundle.points[0].value == 7.9
    assert bundle.summary["latest"] == 7.9


def test_station_history_client_parses_web_scrape_injected_table_like_history_payload() -> None:
    structure = parse_market_question("Will the highest temperature in Madrid be 28C or higher on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="Public website page: https://example.com/weather/history.html",
        description="This market resolves from the temperature table on the linked HTML page.",
        rules="Scrape the table on the source website after the daily data is posted.",
    )
    client = _FakeStationHistoryClient(
        [
            {
                "rows": [
                    {"date": "2026-04-24", "tmax": 26.1, "tmin": 12.4},
                    {"date": "2026-04-25", "tmax": 28.4, "tmin": 13.2},
                ]
            }
        ]
    )

    bundle = client.fetch_history_bundle(structure, resolution, start_date="2026-04-25", end_date="2026-04-25")

    assert client.requested_urls == ["https://example.com/weather/history.html"]
    assert bundle.source_provider == "web_scrape"
    assert bundle.latency_tier == "scrape_target"
    assert bundle.polling_focus == "manual_html_extraction"
    assert bundle.points[0].timestamp == "2026-04-25"
    assert bundle.points[0].value == 28.4
    assert bundle.summary["max"] == 28.4


def test_station_history_client_parses_local_official_injected_latest_payload() -> None:
    structure = parse_market_question("Will the lowest temperature in Reykjavík be 1C or below on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="Official local city weather station source: https://weather.example.gov/city/daily",
        description="This market resolves to the lowest temperature recorded by the official local weather source.",
        rules="Use the linked country weather station table after publication.",
    )
    client = _FakeStationHistoryClient(
        [
            {
                "observations": [
                    {"timestamp": "2026-04-25T07:00:00+00:00", "temp": 0.8, "unit": "C"},
                    {"timestamp": "2026-04-25T13:00:00+00:00", "temp": 4.1, "unit": "C"},
                ]
            }
        ]
    )

    bundle = client.fetch_latest_bundle(structure, resolution)

    assert client.requested_urls == ["https://weather.example.gov/city/daily"]
    assert bundle.source_provider == "local_official_weather_source"
    assert bundle.latency_tier == "scrape_target"
    assert bundle.polling_focus == "local_official_source_review"
    assert bundle.points[0].timestamp == "2026-04-25T13:00:00+00:00"
    assert bundle.points[0].value == 4.1
    assert bundle.summary["latest"] == 4.1


def test_build_station_history_bundle_returns_empty_fallback_when_generic_payload_is_not_table_like() -> None:
    structure = parse_market_question("Will the highest temperature in Madrid be 28C or higher on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="Public website page: https://example.com/weather/history.html",
        description="This market resolves from the temperature table on the linked HTML page.",
        rules="Scrape the table on the source website after the daily data is posted.",
    )
    client = _FakeStationHistoryClient([{"content": "daily weather narrative without rows"}])

    bundle = build_station_history_bundle(structure, resolution, start_date="2026-04-25", end_date="2026-04-25", client=client)

    assert bundle.source_provider == "web_scrape"
    assert bundle.station_code is None
    assert bundle.latency_tier == "unsupported"
    assert bundle.points == []
    assert bundle.summary == {}



def test_station_history_client_parses_open_meteo_columnar_daily_and_current_payloads() -> None:
    structure = parse_market_question("Will the highest temperature in Miami be 28C or higher on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="https://api.open-meteo.com/v1/forecast?latitude=25.76&longitude=-80.19&daily=temperature_2m_max,temperature_2m_min&current_weather=true",
        description="This market resolves to the highest temperature observed for Miami.",
        rules="Source: Open-Meteo API JSON payload.",
    )
    client = _FakeStationHistoryClient(
        [
            {"current_weather": {"time": "2026-04-25T10:00", "temperature": 27.0}},
            {"daily": {"time": ["2026-04-25"], "temperature_2m_max": [29.0], "temperature_2m_min": [23.0]}},
        ]
    )

    latest = client.fetch_latest_bundle(structure, resolution)
    history = client.fetch_history_bundle(structure, resolution, start_date="2026-04-25", end_date="2026-04-25")

    assert client.requested_urls == [resolution.source_url, resolution.source_url]
    assert latest.source_provider == "open_meteo"
    assert latest.latency_tier == "direct_api"
    assert latest.polling_focus == "open_meteo_injected_payload"
    assert latest.points[0].value == 27.0
    assert history.points[0].timestamp == "2026-04-25"
    assert history.points[0].value == 29.0


def test_station_history_client_parses_openweather_main_payload() -> None:
    structure = parse_market_question("Will the highest temperature in Miami be 82F or higher on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="https://api.openweathermap.org/data/3.0/onecall?lat=25.76&lon=-80.19&units=imperial",
        description="This market resolves to the highest temperature observed for Miami.",
        rules="Source: OpenWeatherMap JSON payload.",
    )
    client = _FakeStationHistoryClient(
        [
            {"dt_txt": "2026-04-25 10:00:00", "main": {"temp": 80.0, "temp_max": 84.0, "temp_min": 73.0}},
        ]
    )

    bundle = client.fetch_history_bundle(structure, resolution, start_date="2026-04-25", end_date="2026-04-25")

    assert client.requested_urls == [resolution.source_url]
    assert bundle.source_provider == "openweather"
    assert bundle.latency_tier == "direct_api"
    assert bundle.polling_focus == "openweather_injected_payload"
    assert bundle.points[0].value == 84.0


def test_station_history_client_parses_yr_no_timeseries_payload() -> None:
    structure = parse_market_question("Will the lowest temperature in Oslo be 4C or below on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="https://api.met.no/weatherapi/locationforecast/2.0/compact?lat=59.9&lon=10.7",
        description="This market resolves to the lowest temperature observed for Oslo.",
        rules="Source: api.met.no JSON payload.",
    )
    client = _FakeStationHistoryClient(
        [
            {"properties": {"timeseries": [{"time": "2026-04-25T00:00:00Z", "data": {"instant": {"details": {"air_temperature": 3.5}}}}]}},
        ]
    )

    bundle = client.fetch_history_bundle(structure, resolution, start_date="2026-04-25", end_date="2026-04-25")

    assert bundle.source_provider == "yr_no"
    assert bundle.polling_focus == "yr_no_injected_payload"
    assert bundle.points[0].value == 3.5


def test_station_history_client_parses_iot_station_measurement_payloads() -> None:
    structure = parse_market_question("Will the current temperature in Miami be 80F or higher on April 25?")
    cases = [
        ("WeatherLink station API", "https://api.weatherlink.com/v2/current/12345", "weatherlink", {"data": [{"ts": "2026-04-25T10:00:00Z", "temp_f": 80.5}]}),
        ("Ambient Weather station API", "https://api.ambientweather.net/v1/devices", "ambient_weather", {"data": [{"dateutc": "2026-04-25T10:00:00Z", "tempf": 80.5}]}),
        ("Netatmo weather station API", "https://api.netatmo.com/api/getmeasure", "netatmo", {"body": [{"time": "2026-04-25T10:00:00Z", "temperature": 80.5, "unit": "F"}]}),
    ]

    for name, url, provider, payload in cases:
        resolution = parse_resolution_metadata(
            resolution_source=name,
            description="This market resolves to the current temperature observed for Miami.",
            rules=f"Source: {url} JSON payload.",
        )
        client = _FakeStationHistoryClient([payload])

        bundle = client.fetch_latest_bundle(structure, resolution)

        assert resolution.provider == provider
        assert bundle.source_provider == provider
        assert bundle.latency_tier == "direct_api"
        assert bundle.polling_focus == f"{provider}_injected_payload"
        assert bundle.points[0].value == 80.5


def test_station_history_client_parses_additional_european_official_payload_shapes() -> None:
    client = StationHistoryClient()
    structure = parse_market_question("Will the highest temperature in Zurich be 25C or higher on April 25?")
    cases = [
        ("meteoswiss", {"features": [{"properties": {"reference_ts": "2026-04-25T12:00:00Z", "tre200s0": 25.4, "station": "SMA"}}]}),
        ("smhi", {"value": [{"date": "2026-04-25", "value": 25.1, "station": "98210"}]}),
        ("knmi", {"records": [{"date": "2026-04-25", "TX": 251, "unit": "0.1C"}]}),
        ("aemet", [{"fint": "2026-04-25T18:00:00", "ta": 25.7}]),
        ("met_eireann", [{"date": "2026-04-25", "temperature": 25.2, "station": "phoenix-park"}]),
        ("dmi", {"features": [{"properties": {"observed": "2026-04-25T12:00:00Z", "value": 25.6, "parameterId": "temp_dry"}}]}),
    ]

    for provider, payload in cases:
        resolution = ResolutionMetadata(
            provider=provider,
            source_url=f"https://example.test/{provider}",
            station_code=None,
            station_name=None,
            station_type="unknown",
            wording_clear=True,
            rules_clear=True,
            manual_review_needed=False,
            revision_risk="low",
        )
        client._fetch_json = lambda url, payload=payload: payload  # type: ignore[method-assign]

        bundle = client.fetch_history_bundle(structure, resolution, start_date="2026-04-25", end_date="2026-04-25")

        assert bundle.source_provider == provider
        assert bundle.latency_tier == "direct_history"
        assert bundle.polling_focus == f"{provider}_official_observations"
        assert bundle.points
        assert bundle.points[-1].unit == "c"


def test_station_history_client_parses_latin_american_official_payload_shapes() -> None:
    client = StationHistoryClient()
    structure = parse_market_question("Will the highest temperature in São Paulo be 30C or higher on April 25?")
    cases = [
        ("meteochile", [{"fecha": "2026-04-25", "temperaturaMaxima": 30.4, "estacion": "330007"}]),
        ("inmet", [{"DT_MEDICAO": "2026-04-25", "TEM_MAX": 30.1, "CD_ESTACAO": "A701"}]),
        ("senamhi_peru", {"data": [{"fecha": "2026-04-25", "tmax": 30.3, "estacion": "Lima"}]}),
        ("ideam_colombia", {"records": [{"Fecha": "2026-04-25", "Valor": 30.6, "Variable": "Temperatura máxima"}]}),
        ("smn_argentina", [{"fecha": "2026-04-25", "temperatura": 30.2, "nombre": "Buenos Aires"}]),
        ("smn_mexico", {"datos": [{"fecha": "2026-04-25", "tmax": 30.7, "estacion": "Observatorio"}]}),
    ]

    for provider, payload in cases:
        resolution = ResolutionMetadata(
            provider=provider,
            source_url=f"https://example.test/{provider}",
            station_code=None,
            station_name=None,
            station_type="unknown",
            wording_clear=True,
            rules_clear=True,
            manual_review_needed=False,
            revision_risk="low",
        )
        client._fetch_json = lambda url, payload=payload: payload  # type: ignore[method-assign]

        bundle = client.fetch_history_bundle(structure, resolution, start_date="2026-04-25", end_date="2026-04-25")

        assert bundle.source_provider == provider
        assert bundle.latency_tier == "direct_history"
        assert bundle.polling_focus == f"{provider}_official_observations"
        assert bundle.points
        assert bundle.summary["max"] >= 30.1


def test_station_history_client_parses_africa_middle_east_official_payload_shapes() -> None:
    client = StationHistoryClient()
    structure = parse_market_question("Will the highest temperature in Johannesburg be 28C or higher on April 25?")
    cases = [
        ("south_african_weather_service", [{"date": "2026-04-25", "maximum_temperature": 28.4, "station": "Johannesburg"}]),
        ("nimet_nigeria", {"data": [{"date": "2026-04-25", "maxTemp": 34.1, "station": "Lagos"}]}),
        ("egyptian_meteorological_authority", {"records": [{"date": "2026-04-25", "max_temperature": 31.6, "station": "Cairo"}]}),
        ("israel_meteorological_service", [{"date": "2026-04-25", "TD": 29.2, "station": "Tel Aviv"}]),
        ("turkish_meteorological_service", {"data": [{"tarih": "2026-04-25", "maksimumSicaklik": 28.7, "istasyon": "Istanbul"}]}),
        ("saudi_ncm", {"observations": [{"date": "2026-04-25", "max_temperature": 39.3, "station": "Riyadh"}]}),
    ]

    for provider, payload in cases:
        resolution = ResolutionMetadata(
            provider=provider,
            source_url=f"https://example.test/{provider}",
            station_code=None,
            station_name=None,
            station_type="unknown",
            wording_clear=True,
            rules_clear=True,
            manual_review_needed=False,
            revision_risk="low",
        )
        client._fetch_json = lambda url, payload=payload: payload  # type: ignore[method-assign]

        bundle = client.fetch_history_bundle(structure, resolution, start_date="2026-04-25", end_date="2026-04-25")

        assert bundle.source_provider == provider
        assert bundle.latency_tier == "direct_history"
        assert bundle.polling_focus == f"{provider}_official_observations"
        assert bundle.points
        assert bundle.summary["max"] >= 28.4


def test_station_history_client_parses_asia_pacific_official_payload_shapes() -> None:
    client = StationHistoryClient()
    structure = parse_market_question("Will the highest temperature in Seoul be 25C or higher on April 25?")
    cases = [
        ("kma_korea", [{"tm": "2026-04-25 15:00", "TA": 25.4, "stnId": "108"}]),
        ("taiwan_cwa", {"records": {"Station": [{"ObsTime": {"DateTime": "2026-04-25T14:00:00+08:00"}, "WeatherElement": {"AirTemperature": 26.1}, "StationName": "Taipei"}]}}),
        ("mss_singapore", {"items": [{"timestamp": "2026-04-25T14:00:00+08:00", "readings": [{"station_id": "S109", "value": 31.2}]}]}),
        ("metmalaysia", {"results": [{"date": "2026-04-25", "temperature": 33.1, "stationid": "WMKK"}]}),
        ("bmkg_indonesia", {"data": [{"datetime": "2026-04-25T12:00:00+07:00", "t": 30.8, "id_stasiun": "96745"}]}),
        ("tmd_thailand", {"WeatherToday": [{"DateTime": "2026-04-25T13:00:00+07:00", "Temperature": 35.2, "StationNameThai": "Bangkok"}]}),
        ("metservice_nz", {"observations": [{"time": "2026-04-25T12:00:00+12:00", "temperature": 18.7, "station": "Auckland"}]}),
        ("jma", {"latestTime": "2026-04-25T12:00:00+09:00", "temp": [{"station": "44132", "time": "2026-04-25T12:00:00+09:00", "temp": 24.9}]}, "jma_official_amedas_or_injected_payload"),
        ("pagasa", {"observations": [{"datetime": "2026-04-25T12:00:00+08:00", "temperature": 33.4, "station": "NCR"}]}, "pagasa_official_observations_or_injected_payload"),
        ("imd", {"aws": [{"date": "2026-04-25", "MAX_TEMP": 36.5, "station_id": "42182"}]}, "imd_official_observations_or_injected_payload"),
        ("bom", {"observations": {"data": [{"local_date_time_full": "20260425120000", "air_temp": 27.2, "name": "Sydney"}]}}, "bom_official_observations_or_injected_payload"),
    ]

    for case in cases:
        provider, payload = case[:2]
        expected_focus = case[2] if len(case) == 3 else f"{provider}_official_observations"
        resolution = ResolutionMetadata(
            provider=provider,
            source_url=f"https://example.test/{provider}",
            station_code=None,
            station_name=None,
            station_type="unknown",
            wording_clear=True,
            rules_clear=True,
            manual_review_needed=False,
            revision_risk="low",
        )
        client._fetch_json = lambda url, payload=payload: payload  # type: ignore[method-assign]

        bundle = client.fetch_history_bundle(structure, resolution, start_date="2026-04-25", end_date="2026-04-25")

        assert bundle.source_provider == provider
        assert bundle.latency_tier == "direct_history"
        assert bundle.polling_focus == expected_focus
        assert bundle.points
        assert bundle.summary["max"] >= 18.7
