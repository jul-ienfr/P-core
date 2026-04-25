from __future__ import annotations

from weather_pm.market_parser import parse_market_question
from weather_pm.resolution_parser import parse_resolution_metadata
from weather_pm.source_routing import build_resolution_source_route


def test_build_resolution_source_route_targets_noaa_station_latest_and_history_directly() -> None:
    structure = parse_market_question("Will the highest temperature in Denver be 64F or higher on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="Resolution source: NOAA daily climate report for station KDEN",
        description="Official observed high temperature at Denver International Airport station KDEN.",
        rules="Source: https://www.weather.gov/wrh/climate?wfo=bou station KDEN.",
    )

    route = build_resolution_source_route(structure, resolution, start_date="2026-04-24", end_date="2026-04-25")

    assert route.provider == "noaa"
    assert route.station_code == "KDEN"
    assert route.direct is True
    assert route.latency_tier == "direct_latest"
    assert route.latency_priority == "direct_source_low_latency"
    assert route.latest_url == "https://api.weather.gov/stations/KDEN/observations/latest"
    assert route.history_url == "https://api.weather.gov/stations/KDEN/observations?start=2026-04-24T00%3A00%3A00Z&end=2026-04-25T23%3A59%3A59Z"
    assert route.polling_focus == "station_observations_latest"
    assert route.manual_review_needed is False


def test_build_resolution_source_route_targets_noaa_daily_summary_for_single_day_high_low_market() -> None:
    structure = parse_market_question("Will the highest temperature in Denver be 64F or higher on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="Resolution source: NOAA daily climate report for station KDEN",
        description="Official observed high temperature at Denver International Airport station KDEN.",
        rules="Source: NOAA/NWS daily climate summary for KDEN.",
    )

    route = build_resolution_source_route(structure, resolution, start_date="2026-04-25", end_date="2026-04-25")

    assert route.provider == "noaa"
    assert route.station_code == "KDEN"
    assert route.direct is True
    assert route.latency_tier == "direct_history"
    assert route.latest_url == "https://api.weather.gov/stations/KDEN/observations/latest"
    assert route.history_url == "https://www.ncei.noaa.gov/access/services/data/v1?dataset=daily-summaries&stations=KDEN&startDate=2026-04-25&endDate=2026-04-25&format=json&units=standard&includeAttributes=false"
    assert route.polling_focus == "noaa_official_daily_summary"


def test_build_resolution_source_route_targets_wunderground_station_without_geocoding() -> None:
    structure = parse_market_question("Will the lowest temperature in Miami be 63°F or below on April 23?")
    resolution = parse_resolution_metadata(
        resolution_source="https://www.wunderground.com/history/daily/us/fl/miami/KMIA",
        description=(
            "This market will resolve to the temperature range that contains the lowest "
            "temperature recorded at the Miami Intl Airport Station in degrees Fahrenheit on 23 Apr '26."
        ),
        rules="This market resolves based on the final daily observation published at the resolution source.",
    )

    route = build_resolution_source_route(structure, resolution, start_date="2026-04-23", end_date="2026-04-23")

    assert route.provider == "wunderground"
    assert route.station_code == "KMIA"
    assert route.direct is True
    assert route.latency_priority == "direct_source_low_latency"
    assert route.latest_url == "https://www.wunderground.com/history/daily/us/fl/miami/KMIA"
    assert route.history_url == "https://www.wunderground.com/history/daily/us/fl/miami/KMIA/date/2026-04-23"
    assert route.polling_focus == "station_history_page"


def test_build_resolution_source_route_targets_aviation_weather_station_api() -> None:
    structure = parse_market_question("Will the highest temperature in Denver be 64F or higher on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="METAR airport observations for station KDEN",
        description="Official observed high temperature at Denver International Airport station KDEN.",
        rules="Source: aviationweather.gov airport observations for station KDEN.",
    )

    route = build_resolution_source_route(structure, resolution, start_date="2026-04-25", end_date="2026-04-25")

    assert route.provider == "aviation_weather"
    assert route.station_code == "KDEN"
    assert route.direct is True
    assert route.supported is True
    assert route.latency_tier == "direct_latest"
    assert route.latency_priority == "direct_source_low_latency"
    assert route.latest_url == "https://aviationweather.gov/api/data/metar?ids=KDEN&format=json&taf=false"
    assert route.history_url == "https://aviationweather.gov/api/data/metar?ids=KDEN&format=json&taf=false&start=2026-04-25T00%3A00%3A00Z&end=2026-04-25T23%3A59%3A59Z"
    assert route.polling_focus == "aviation_weather_metar_observations"


def test_build_resolution_source_route_targets_meteostat_station_history_fallback() -> None:
    structure = parse_market_question("Will the highest temperature in Denver be 64F or higher on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="Resolution source: Meteostat daily data for station 72565",
        description="This market resolves to the highest temperature recorded in Denver.",
        rules="Use Meteostat daily tmax/tmin rows for station 72565.",
    )

    route = build_resolution_source_route(structure, resolution, start_date="2026-04-25", end_date="2026-04-25")

    assert route.provider == "meteostat"
    assert route.station_code == "72565"
    assert route.direct is False
    assert route.supported is True
    assert route.latency_tier == "fallback_history"
    assert route.latency_priority == "fallback_daily_history"
    assert route.history_url == "meteostat://daily?station=72565&start=2026-04-25&end=2026-04-25"
    assert route.polling_focus == "meteostat_daily_history"
    assert route.manual_review_needed is False


def test_build_resolution_source_route_targets_meteostat_city_history_fallback_without_station_code() -> None:
    structure = parse_market_question("Will the lowest temperature in Paris be 8C or below on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="Meteostat historical daily data",
        description="This market resolves to the lowest temperature in Paris.",
        rules="Use Meteostat daily tmax/tmin rows.",
    )

    route = build_resolution_source_route(structure, resolution, start_date="2026-04-25", end_date="2026-04-25")

    assert route.provider == "meteostat"
    assert route.station_code is None
    assert route.direct is False
    assert route.supported is True
    assert route.latency_tier == "fallback_history"
    assert route.latency_priority == "fallback_city_daily_history"
    assert route.history_url == "meteostat://daily?city=Paris&start=2026-04-25&end=2026-04-25"
    assert route.polling_focus == "meteostat_city_daily_history"
    assert route.manual_review_needed is False


def test_build_resolution_source_route_marks_unknown_source_as_unsupported_focus() -> None:
    structure = parse_market_question("Will the highest temperature in Paris be 20C or higher on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="local weather station data",
        description="This market uses station data if available.",
        rules="Data may come from a public weather page.",
    )

    route = build_resolution_source_route(structure, resolution)

    assert route.direct is False
    assert route.supported is False
    assert route.latest_url is None
    assert route.history_url is None
    assert route.latency_tier == "unsupported"
    assert route.latency_priority == "manual_review_required"
    assert route.manual_review_needed is True
    assert "No direct route" in route.reason


def test_build_resolution_source_route_targets_accuweather_source_url_without_secret() -> None:
    structure = parse_market_question("Will the highest temperature in Miami be 82F or higher on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="https://www.accuweather.com/en/us/miami/33128/daily-weather-forecast/347936",
        description="This market resolves to the highest temperature observed for Miami on the linked AccuWeather page.",
        rules="Source: AccuWeather daily forecast page for location key 347936.",
    )

    route = build_resolution_source_route(structure, resolution, start_date="2026-04-25", end_date="2026-04-25")

    assert route.provider == "accuweather"
    assert route.station_code == "347936"
    assert route.direct is True
    assert route.supported is True
    assert route.latency_priority == "direct_source_low_latency"
    assert route.latest_url == "https://www.accuweather.com/en/us/miami/33128/daily-weather-forecast/347936"
    assert route.history_url == "https://www.accuweather.com/en/us/miami/33128/daily-weather-forecast/347936?details=true"
    assert route.polling_focus == "accuweather_location_page_or_injected_json"
    assert "API key" in route.reason
    assert "apikey" not in route.latest_url.lower()
    assert "apikey" not in route.history_url.lower()


def test_build_resolution_source_route_targets_hko_official_monthly_opendata_for_high_temperature() -> None:
    structure = parse_market_question("Will the highest temperature in Hong Kong be 29°C or higher on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="https://www.hko.gov.hk/en/wxinfo/currwx/current.htm",
        description="This market resolves according to the official highest temperature recorded by the Hong Kong Observatory.",
        rules="Source: Hong Kong Observatory daily extract, finalized by weather.gov.hk.",
    )

    route = build_resolution_source_route(structure, resolution, start_date="2026-04-25", end_date="2026-04-25")

    assert route.direct is True
    assert route.provider == "hong_kong_observatory"
    assert route.latest_url == "https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=rhrread&lang=en"
    assert route.history_url == "https://data.weather.gov.hk/weatherAPI/opendata/opendata.php?dataType=CLMMAXT&rformat=json&station=HKO&year=2026&month=4"
    assert route.polling_focus == "hko_current_weather_and_daily_extract"


def test_build_resolution_source_route_targets_hko_official_monthly_opendata_for_low_temperature() -> None:
    structure = parse_market_question("Will the lowest temperature in Hong Kong be 20°C or below on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="https://www.weather.gov.hk/en/wxinfo/dailywx/extract.htm",
        description="This market resolves according to the official lowest temperature recorded by the Hong Kong Observatory.",
        rules="Source: Hong Kong Observatory daily extract, finalized by weather.gov.hk.",
    )

    route = build_resolution_source_route(structure, resolution, start_date="2026-04-25", end_date="2026-04-25")

    assert route.history_url == "https://data.weather.gov.hk/weatherAPI/opendata/opendata.php?dataType=CLMMINT&rformat=json&station=HKO&year=2026&month=4"
