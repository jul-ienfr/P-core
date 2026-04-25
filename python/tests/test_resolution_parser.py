from __future__ import annotations

from weather_pm.resolution_parser import parse_resolution_metadata


def test_parse_resolution_metadata_detects_clear_noaa_station_source() -> None:
    result = parse_resolution_metadata(
        resolution_source="Resolution source: NOAA daily climate report for station KDEN",
        description="This market resolves according to the official observed high temperature at Denver International Airport.",
        rules="Source: https://www.weather.gov/wrh/climate?wfo=bou station KDEN.",
    )

    assert result.provider == "noaa"
    assert result.station_code == "KDEN"
    assert result.station_type == "airport"
    assert result.manual_review_needed is False
    assert result.rules_clear is True
    assert result.revision_risk == "low"


def test_parse_resolution_metadata_detects_aviation_weather_metar_station_source() -> None:
    result = parse_resolution_metadata(
        resolution_source="Resolution source: METAR airport observations for station KDEN",
        description="Official observed high temperature at Denver International Airport station KDEN.",
        rules="Source: https://aviationweather.gov/data/api/ station KDEN aviation weather observations.",
    )

    assert result.provider == "aviation_weather"
    assert result.source_url == "https://aviationweather.gov/data/api/"
    assert result.station_code == "KDEN"
    assert result.station_type == "airport"
    assert result.wording_clear is True
    assert result.rules_clear is True
    assert result.manual_review_needed is False


def test_parse_resolution_metadata_keeps_noaa_provider_when_noaa_and_metar_are_both_mentioned() -> None:
    result = parse_resolution_metadata(
        resolution_source="Resolution source: NOAA daily climate report for station KMIA",
        description="Official observed high temperature at Miami airport station KMIA, not METAR.",
        rules="Source: https://www.weather.gov/wrh/climate?wfo=mfl station KMIA.",
    )

    assert result.provider == "noaa"
    assert result.station_code == "KMIA"


def test_parse_resolution_metadata_marks_ambiguous_source_for_manual_review() -> None:
    result = parse_resolution_metadata(
        resolution_source="Resolution source: local weather station data",
        description="This market uses station data if available.",
        rules="Data may come from a public weather page.",
    )

    assert result.provider == "unknown"
    assert result.station_code is None
    assert result.manual_review_needed is True
    assert result.rules_clear is False
    assert result.revision_risk == "high"


def test_parse_resolution_metadata_classifies_icao_code_as_airport_even_with_station_wording() -> None:
    result = parse_resolution_metadata(
        resolution_source="Resolution source: station EGLL observed temperature",
        description="Official station reading for London Heathrow.",
        rules="Use station EGLL as published on weather.gov mirror page.",
    )

    assert result.station_code == "EGLL"
    assert result.station_type == "airport"


def test_parse_resolution_metadata_extracts_clean_station_details_from_wunderground_event_payload() -> None:
    result = parse_resolution_metadata(
        resolution_source="https://www.wunderground.com/history/daily/us/fl/miami/KMIA",
        description=(
            "This market will resolve to the temperature range that contains the lowest "
            "temperature recorded at the Miami Intl Airport Station in degrees Fahrenheit "
            "on 23 Apr '26."
        ),
        rules=(
            "This market resolves based on the final daily observation published at the "
            "resolution source."
        ),
    )

    assert result.provider == "wunderground"
    assert result.source_url == "https://www.wunderground.com/history/daily/us/fl/miami/KMIA"
    assert result.station_code == "KMIA"
    assert result.station_name == "Miami Intl Airport"
    assert result.station_type == "airport"


def test_parse_resolution_metadata_uses_wunderground_url_station_code_when_description_has_no_code() -> None:
    result = parse_resolution_metadata(
        resolution_source="https://www.wunderground.com/history/daily/jp/tokyo/RJTT",
        description=(
            "This market resolves to the highest temperature recorded at the Tokyo Haneda "
            "Airport Station in degrees Celsius."
        ),
        rules="Use the linked Wunderground daily history page.",
    )

    assert result.provider == "wunderground"
    assert result.station_code == "RJTT"
    assert result.station_name == "Tokyo Haneda Airport"
    assert result.station_type == "airport"


def test_parse_resolution_metadata_extracts_clean_hong_kong_observatory_station_name() -> None:
    result = parse_resolution_metadata(
        resolution_source="https://www.weather.gov.hk/en/cis/climat.htm",
        description=(
            "This market will resolve to the temperature range that contains the highest "
            "temperature recorded by the Hong Kong Observatory in degrees Celsius on 1 Apr '26.'"
        ),
        rules=(
            "This market resolves based on the finalized Hong Kong Observatory Daily Extract."
        ),
    )

    assert result.provider == "hong_kong_observatory"
    assert result.station_code is None
    assert result.station_name == "Hong Kong Observatory"
    assert result.station_type == "station"
    assert result.wording_clear is True
    assert result.rules_clear is True
    assert result.manual_review_needed is False
    assert result.revision_risk == "low"


def test_parse_resolution_metadata_extracts_accuweather_location_key_from_url() -> None:
    result = parse_resolution_metadata(
        resolution_source="https://www.accuweather.com/en/us/miami/33128/daily-weather-forecast/347936",
        description=(
            "This market resolves to the highest temperature observed for Miami on "
            "the linked AccuWeather page."
        ),
        rules="Source: AccuWeather daily forecast page for location key 347936.",
    )

    assert result.provider == "accuweather"
    assert result.source_url == "https://www.accuweather.com/en/us/miami/33128/daily-weather-forecast/347936"
    assert result.station_code == "347936"
    assert result.station_name == "Miami"
    assert result.station_type == "location"
    assert result.wording_clear is True
    assert result.rules_clear is True
    assert result.manual_review_needed is False


def test_parse_resolution_metadata_detects_meteostat_from_resolution_text() -> None:
    result = parse_resolution_metadata(
        resolution_source="Resolution source: Meteostat daily data for station 72565",
        description="This market resolves to the highest temperature recorded in Denver.",
        rules="Use the Meteostat daily tmax/tmin row published at https://meteostat.net/en/station/72565.",
    )

    assert result.provider == "meteostat"
    assert result.source_url == "https://meteostat.net/en/station/72565."
    assert result.station_code == "72565"
    assert result.station_type == "station"
    assert result.wording_clear is True
    assert result.rules_clear is True
    assert result.manual_review_needed is False
