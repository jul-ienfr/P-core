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
