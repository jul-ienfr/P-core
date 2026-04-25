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


def test_build_resolution_source_route_targets_iem_asos_station_archive_without_geocoding() -> None:
    structure = parse_market_question("Will the highest temperature in Denver be 64F or higher on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="IEM ASOS archive for station KDEN",
        description="Official ASOS/METAR observed high temperature at Denver International Airport station KDEN.",
        rules="Source: https://mesonet.agron.iastate.edu/request/download.phtml station KDEN.",
    )

    route = build_resolution_source_route(structure, resolution, start_date="2026-04-25", end_date="2026-04-25")

    assert route.provider == "iem_asos"
    assert route.station_code == "KDEN"
    assert route.direct is True
    assert route.supported is True
    assert route.latency_tier == "direct_history"
    assert route.latency_priority == "direct_source_official_open_data"
    assert route.latest_url is None
    assert route.history_url == "https://mesonet.agron.iastate.edu/request/download.phtml?station=KDEN&data=tmpf&year1=2026&month1=4&day1=25&year2=2026&month2=4&day2=25&tz=Etc%2FUTC&format=onlycomma&latlon=no&elev=no&missing=empty&trace=null&direct=no&report_type=1&report_type=2"
    assert route.polling_focus == "iem_asos_minute_archive"


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


def test_build_resolution_source_route_preserves_commercial_api_source_url() -> None:
    structure = parse_market_question("Will the highest temperature in Miami be 82F or higher on April 25?")
    cases = [
        ("weatherapi", "https://api.weatherapi.com/v1/forecast.json?q=Miami&days=1"),
        ("visual_crossing", "https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/Miami/2026-04-25"),
        ("weatherbit", "https://api.weatherbit.io/v2.0/history/daily?city=Miami&start_date=2026-04-25&end_date=2026-04-26"),
        ("tomorrow_io", "https://api.tomorrow.io/v4/weather/history/recent?location=Miami"),
        ("meteoblue", "https://my.meteoblue.com/packages/basic-day?lat=25.76&lon=-80.19"),
    ]

    for provider, source_url in cases:
        resolution = parse_resolution_metadata(
            resolution_source=source_url,
            description="This market resolves to the highest temperature observed for Miami.",
            rules="Use the linked commercial weather API payload.",
        )

        route = build_resolution_source_route(structure, resolution, start_date="2026-04-25", end_date="2026-04-25")

        assert route.provider == provider
        assert route.source_url == source_url
        assert route.latest_url == source_url
        assert route.history_url == source_url
        assert route.direct is True
        assert route.supported is True
        assert route.latency_tier == "direct_api"
        assert route.polling_focus == f"{provider}_injected_payload"


def test_build_resolution_source_route_preserves_weather_com_page_as_auditable_direct_target() -> None:
    structure = parse_market_question("Will the highest temperature in Miami be 82F or higher on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="https://weather.com/weather/tenday/l/Miami+FL",
        description="This market resolves to the highest temperature observed for Miami on The Weather Channel page.",
        rules="Source: Weather.com / The Weather Channel daily details page.",
    )

    route = build_resolution_source_route(structure, resolution, start_date="2026-04-25", end_date="2026-04-25")

    assert route.provider == "weather_com"
    assert route.source_url == "https://weather.com/weather/tenday/l/Miami+FL"
    assert route.latest_url == "https://weather.com/weather/tenday/l/Miami+FL"
    assert route.history_url == "https://weather.com/weather/tenday/l/Miami+FL"
    assert route.direct is False
    assert route.supported is True
    assert route.latency_tier == "scrape_target"
    assert route.latency_priority == "auditable_scrape_target"
    assert route.polling_focus == "weather_com_page_or_injected_payload"
    assert route.manual_review_needed is True


def test_build_resolution_source_route_marks_commercial_api_without_url_for_manual_review() -> None:
    structure = parse_market_question("Will the highest temperature in Miami be 82F or higher on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="WeatherAPI.com",
        description="This market resolves to the highest temperature observed for Miami.",
        rules="Use the commercial API result.",
    )

    route = build_resolution_source_route(structure, resolution, start_date="2026-04-25", end_date="2026-04-25")

    assert route.provider == "weatherapi"
    assert route.source_url is None
    assert route.direct is False
    assert route.supported is False
    assert route.latest_url is None
    assert route.history_url is None
    assert route.latency_tier == "api_key_required"
    assert route.latency_priority == "manual_review_required"
    assert route.polling_focus == "manual_review"
    assert route.manual_review_needed is True
    assert "explicit source_url" in route.reason


def test_build_resolution_source_route_preserves_weather_com_page_as_manual_review_scrape_target() -> None:
    structure = parse_market_question("Will the highest temperature in Miami be 82F or higher on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="https://weather.com/weather/today/l/Miami",
        description="This market resolves to the highest temperature observed for Miami on The Weather Channel.",
        rules="Source: Weather.com page.",
    )

    route = build_resolution_source_route(structure, resolution)

    assert route.provider == "weather_com"
    assert route.source_url == "https://weather.com/weather/today/l/Miami"
    assert route.direct is False
    assert route.supported is True
    assert route.latest_url == "https://weather.com/weather/today/l/Miami"
    assert route.history_url == "https://weather.com/weather/today/l/Miami"
    assert route.latency_tier == "scrape_target"
    assert route.latency_priority == "auditable_scrape_target"
    assert route.polling_focus == "weather_com_page_or_injected_payload"
    assert route.manual_review_needed is True
    assert "manual review" in route.reason


def test_build_resolution_source_route_marks_ecmwf_copernicus_as_reanalysis_fallback() -> None:
    structure = parse_market_question("Will the highest temperature in Paris be 20C or higher on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="Copernicus Climate Data Store reanalysis",
        description="This market resolves to the highest temperature recorded in Paris.",
        rules="Use ECMWF ERA5 reanalysis from cds.climate.copernicus.eu.",
    )

    route = build_resolution_source_route(structure, resolution, start_date="2026-04-25", end_date="2026-04-25")

    assert route.provider == "ecmwf_copernicus"
    assert route.direct is False
    assert route.supported is True
    assert route.latency_tier == "fallback_reanalysis"
    assert route.latency_priority == "fallback_reanalysis_not_low_latency"
    assert route.polling_focus == "ecmwf_copernicus_reanalysis_manual_or_injected_payload"
    assert route.latest_url is None
    assert route.history_url == "ecmwf_copernicus://reanalysis?city=Paris&start=2026-04-25&end=2026-04-25"
    assert "reanalysis" in route.reason


def test_build_resolution_source_route_requires_explicit_meteo_france_api_source() -> None:
    structure = parse_market_question("Will the lowest temperature in Paris be 8C or below on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="Météo-France official observations",
        description="This market resolves to the lowest temperature recorded in Paris.",
        rules="Use official Météo-France observations.",
    )

    route = build_resolution_source_route(structure, resolution, start_date="2026-04-25", end_date="2026-04-25")

    assert route.provider == "meteo_france"
    assert route.direct is False
    assert route.supported is False
    assert route.latency_tier == "unsupported"
    assert route.latency_priority == "manual_review_required"
    assert route.polling_focus == "manual_review_api_key_required"
    assert route.manual_review_needed is True
    assert "api_key_required" in route.reason


def test_build_resolution_source_route_preserves_explicit_uk_met_office_source_url_without_key() -> None:
    structure = parse_market_question("Will the highest temperature in London be 17C or higher on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="https://www.metoffice.gov.uk/datapoint",
        description="This market resolves to the highest temperature recorded in London.",
        rules="Source: UK Met Office DataPoint endpoint supplied by operator.",
    )

    route = build_resolution_source_route(structure, resolution, start_date="2026-04-25", end_date="2026-04-25")

    assert route.provider == "uk_met_office"
    assert route.direct is True
    assert route.supported is True
    assert route.latest_url == "https://www.metoffice.gov.uk/datapoint"
    assert route.history_url == "https://www.metoffice.gov.uk/datapoint"
    assert route.polling_focus == "uk_met_office_injected_payload_or_explicit_endpoint"
    assert "API key" in route.reason
    assert "api_key" not in route.latest_url.lower()


def test_build_resolution_source_route_targets_dwd_open_data_source_url_directly() -> None:
    structure = parse_market_question("Will the highest temperature in Berlin be 18C or higher on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="DWD Germany open-data observations for station 10384",
        description="This market resolves to the highest temperature recorded in Berlin.",
        rules="Source: https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/daily/kl/ station 10384.",
    )

    route = build_resolution_source_route(structure, resolution, start_date="2026-04-25", end_date="2026-04-25")

    assert route.provider == "dwd"
    assert route.station_code == "10384"
    assert route.direct is True
    assert route.supported is True
    assert route.latency_tier == "direct_history"
    assert route.latency_priority == "direct_source_official_open_data"
    assert route.latest_url == "https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/daily/kl/"
    assert route.history_url == "https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/daily/kl/"
    assert route.polling_focus == "dwd_open_data_daily_observations"


def test_build_resolution_source_route_targets_bom_source_url_and_station() -> None:
    structure = parse_market_question("Will the highest temperature in Sydney be 25C or higher on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="Bureau of Meteorology station 066062",
        description="This market resolves to the official highest temperature observed at Sydney Observatory Hill station 066062.",
        rules="Source: https://www.bom.gov.au/products/IDN60801/IDN60801.94768.shtml official BOM observations.",
    )

    route = build_resolution_source_route(structure, resolution, start_date="2026-04-25", end_date="2026-04-25")

    assert route.provider == "bom"
    assert route.station_code == "066062"
    assert route.direct is True
    assert route.supported is True
    assert route.latest_url == "https://www.bom.gov.au/products/IDN60801/IDN60801.94768.shtml"
    assert route.history_url == "https://www.bom.gov.au/products/IDN60801/IDN60801.94768.shtml"
    assert route.polling_focus == "bom_official_observations_or_injected_payload"
    assert route.manual_review_needed is False


def test_build_resolution_source_route_targets_jma_official_source_url() -> None:
    structure = parse_market_question("Will the lowest temperature in Tokyo be 12C or below on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="Japan Meteorological Agency station 44132",
        description="This market resolves to the lowest temperature recorded at Tokyo station 44132.",
        rules="Source: https://www.jma.go.jp/bosai/amedas/ official JMA observations.",
    )

    route = build_resolution_source_route(structure, resolution, start_date="2026-04-25", end_date="2026-04-25")

    assert route.provider == "jma"
    assert route.station_code == "44132"
    assert route.direct is True
    assert route.supported is True
    assert route.latest_url == "https://www.jma.go.jp/bosai/amedas/"
    assert route.history_url == "https://www.jma.go.jp/bosai/amedas/"
    assert route.polling_focus == "jma_official_amedas_or_injected_payload"


def test_build_resolution_source_route_marks_pagasa_without_endpoint_as_manual_review() -> None:
    structure = parse_market_question("Will the highest temperature in Manila be 34C or higher on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="PAGASA official observations",
        description="This market resolves to the highest temperature observed in Manila.",
        rules="Use PAGASA public bulletins when available.",
    )

    route = build_resolution_source_route(structure, resolution, start_date="2026-04-25", end_date="2026-04-25")

    assert route.provider == "pagasa"
    assert route.direct is False
    assert route.supported is False
    assert route.latest_url is None
    assert route.history_url is None
    assert route.polling_focus == "manual_review"
    assert route.manual_review_needed is True
    assert "source_url" in route.reason


def test_build_resolution_source_route_targets_imd_source_url_without_api_key() -> None:
    structure = parse_market_question("Will the highest temperature in Delhi be 38C or higher on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="IMD station 42182",
        description="This market resolves to the highest temperature recorded at New Delhi station 42182.",
        rules="Source: https://mausam.imd.gov.in/ official IMD observations.",
    )

    route = build_resolution_source_route(structure, resolution, start_date="2026-04-25", end_date="2026-04-25")

    assert route.provider == "imd"
    assert route.station_code == "42182"
    assert route.direct is True
    assert route.supported is True
    assert route.latest_url == "https://mausam.imd.gov.in/"
    assert route.history_url == "https://mausam.imd.gov.in/"
    assert route.polling_focus == "imd_official_observations_or_injected_payload"
    assert "API key" not in route.reason


def test_build_resolution_source_route_targets_environment_canada_source_url() -> None:
    structure = parse_market_question("Will the highest temperature in Toronto be 18°C or higher on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="https://climate.weather.gc.ca/climateData/dailydata_e.html?StationID=51442",
        description="This market resolves to the highest temperature recorded in Toronto by Environment and Climate Change Canada.",
        rules="Use the finalized Environment Canada climateData daily row from climate.weather.gc.ca.",
    )

    route = build_resolution_source_route(structure, resolution, start_date="2026-04-25", end_date="2026-04-25")

    assert route.provider == "environment_canada"
    assert route.station_code == "51442"
    assert route.direct is True
    assert route.supported is True
    assert route.source_url == "https://climate.weather.gc.ca/climateData/dailydata_e.html?StationID=51442"
    assert route.latest_url == "https://climate.weather.gc.ca/climateData/dailydata_e.html?StationID=51442"
    assert route.history_url == "https://climate.weather.gc.ca/climateData/dailydata_e.html?StationID=51442&timeframe=2&StartYear=1840&EndYear=2026&Year=2026&Month=4&Day=25"
    assert route.polling_focus == "environment_canada_official_history"
    assert route.manual_review_needed is False


def test_build_resolution_source_route_marks_generic_national_service_as_manual_review_with_source_url() -> None:
    structure = parse_market_question("Will the highest temperature in Mexico City be 28°C or higher on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="https://example.test/official-weather/mexico-city",
        description="This market resolves to the highest temperature recorded by the local official weather service.",
        rules="Use the official national meteorological service report if available.",
    )

    route = build_resolution_source_route(structure, resolution, start_date="2026-04-25", end_date="2026-04-25")

    assert route.provider == "national_weather_service"
    assert route.direct is False
    assert route.supported is False
    assert route.source_url == "https://example.test/official-weather/mexico-city"
    assert route.latest_url == "https://example.test/official-weather/mexico-city"
    assert route.history_url is None
    assert route.latency_tier == "manual_review"
    assert route.polling_focus == "manual_review_official_national_service"
    assert route.manual_review_needed is True


def test_build_resolution_source_route_marks_web_scrape_url_as_auditable_scrape_target() -> None:
    structure = parse_market_question("Will the highest temperature in Madrid be 28C or higher on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="Public website page: https://example.com/weather/history.html",
        description="This market resolves from the temperature table on the linked HTML page.",
        rules="Scrape the table on the source website after the daily data is posted.",
    )

    route = build_resolution_source_route(structure, resolution, start_date="2026-04-25", end_date="2026-04-25")

    assert route.provider == "web_scrape"
    assert route.direct is False
    assert route.supported is True
    assert route.latest_url == "https://example.com/weather/history.html"
    assert route.history_url == "https://example.com/weather/history.html"
    assert route.latency_tier == "scrape_target"
    assert route.latency_priority == "auditable_scrape_target"
    assert route.polling_focus == "manual_html_extraction"
    assert route.manual_review_needed is True


def test_build_resolution_source_route_marks_local_official_source_url_for_review() -> None:
    structure = parse_market_question("Will the lowest temperature in Reykjavík be 1C or below on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="Official local city weather station source: https://weather.example.gov/city/daily",
        description="This market resolves to the lowest temperature recorded by the official local weather source.",
        rules="Use the linked country weather station table after publication.",
    )

    route = build_resolution_source_route(structure, resolution, start_date="2026-04-25", end_date="2026-04-25")

    assert route.provider == "local_official_weather_source"
    assert route.direct is False
    assert route.supported is True
    assert route.latest_url == "https://weather.example.gov/city/daily"
    assert route.history_url == "https://weather.example.gov/city/daily"
    assert route.latency_tier == "scrape_target"
    assert route.latency_priority == "auditable_scrape_target"
    assert route.polling_focus == "local_official_source_review"
    assert route.manual_review_needed is True



def test_build_resolution_source_route_preserves_additional_api_and_iot_source_urls() -> None:
    structure = parse_market_question("Will the highest temperature in Miami be 82F or higher on April 25?")
    cases = [
        ("open_meteo", "https://api.open-meteo.com/v1/forecast?latitude=25.76&longitude=-80.19"),
        ("openweather", "https://api.openweathermap.org/data/3.0/onecall?lat=25.76&lon=-80.19"),
        ("yr_no", "https://api.met.no/weatherapi/locationforecast/2.0/compact?lat=59.9&lon=10.7"),
        ("world_weather_online", "https://api.worldweatheronline.com/premium/v1/past-weather.ashx?q=Miami"),
        ("meteomatics", "https://api.meteomatics.com/2026-04-25T00:00:00Z/t_2m:C/25.76,-80.19/json"),
        ("weatherlink", "https://api.weatherlink.com/v2/current/12345"),
        ("ambient_weather", "https://api.ambientweather.net/v1/devices"),
        ("netatmo", "https://api.netatmo.com/api/getmeasure"),
        ("windy", "https://api.windy.com/api/point-forecast/v2"),
        ("aerisweather", "https://api.aerisapi.com/observations/miami,fl"),
    ]

    for provider, source_url in cases:
        resolution = parse_resolution_metadata(
            resolution_source=provider,
            description="This market resolves to the highest temperature observed for Miami.",
            rules=f"Source: {source_url} JSON payload.",
        )
        route = build_resolution_source_route(structure, resolution, start_date="2026-04-25", end_date="2026-04-25")

        assert route.provider == provider
        assert route.direct is True
        assert route.supported is True
        assert route.latest_url == source_url
        assert route.history_url == source_url
        assert route.polling_focus == f"{provider}_injected_payload"
        assert route.reason.startswith(f"{provider} source URL found")


def test_build_resolution_source_route_preserves_synoptic_mesowest_station_api_source_url() -> None:
    structure = parse_market_question("Will the highest temperature in Denver be 64F or higher on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="Synoptic/MesoWest station observations for station KDEN",
        description="This market resolves to the highest temperature observed at Denver station KDEN.",
        rules="Source: https://api.synopticdata.com/v2/stations/timeseries?stid=KDEN official JSON payload.",
    )

    route = build_resolution_source_route(structure, resolution, start_date="2026-04-25", end_date="2026-04-25")

    assert route.provider == "synoptic_mesowest"
    assert route.station_code == "KDEN"
    assert route.direct is True
    assert route.supported is True
    assert route.latest_url == "https://api.synopticdata.com/v2/stations/timeseries?stid=KDEN"
    assert route.history_url == "https://api.synopticdata.com/v2/stations/timeseries?stid=KDEN"
    assert route.latency_tier == "direct_api"
    assert route.latency_priority == "direct_source_low_latency"
    assert route.polling_focus == "synoptic_mesowest_injected_payload"


def test_build_resolution_source_route_preserves_additional_european_official_source_urls() -> None:
    structure = parse_market_question("Will the highest temperature in Zurich be 25C or higher on April 25?")
    cases = [
        ("meteoswiss", "https://data.geo.admin.ch/ch.meteoschweiz.messwerte-aktuell/VQHA80.csv", "meteoswiss_official_observations"),
        ("smhi", "https://opendata-download-metobs.smhi.se/api/version/latest/parameter/1/station/98210/period/latest-day/data.json", "smhi_official_observations"),
        ("knmi", "https://api.dataplatform.knmi.nl/open-data/v1/datasets/etmaalgegevensKNMIstations/versions/1/files", "knmi_official_observations"),
        ("aemet", "https://opendata.aemet.es/opendata/api/observacion/convencional/datos/estacion/3195", "aemet_official_observations"),
        ("met_eireann", "https://prodapi.metweb.ie/observations/phoenix-park/today", "met_eireann_official_observations"),
        ("dmi", "https://dmigw.govcloud.dk/v2/metObs/collections/observation/items?stationId=06181", "dmi_official_observations"),
    ]

    for provider, source_url, polling_focus in cases:
        resolution = parse_resolution_metadata(
            resolution_source=f"Resolution source: {provider} official observations",
            description="Official observed high temperature.",
            rules=f"Source: {source_url} official payload.",
        )

        route = build_resolution_source_route(structure, resolution, start_date="2026-04-25", end_date="2026-04-25")

        assert route.provider == provider
        assert route.source_url == source_url
        assert route.latest_url == source_url
        assert route.history_url == source_url
        assert route.direct is True
        assert route.supported is True
        assert route.latency_tier == "direct_history"
        assert route.latency_priority == "direct_source_official_open_data"
        assert route.polling_focus == polling_focus


def test_build_resolution_source_route_preserves_latin_american_official_source_urls() -> None:
    structure = parse_market_question("Will the highest temperature in São Paulo be 30C or higher on April 25?")
    cases = [
        ("meteochile", "https://climatologia.meteochile.gob.cl/application/diario/visorDeDatos", "meteochile_official_observations"),
        ("inmet", "https://apitempo.inmet.gov.br/estacao/2026-04-25/2026-04-25/A701", "inmet_official_observations"),
        ("senamhi_peru", "https://www.senamhi.gob.pe/mapas/mapa-estaciones-2/", "senamhi_peru_official_observations"),
        ("ideam_colombia", "https://www.ideam.gov.co/web/tiempo-y-clima/consulta-y-descarga-de-datos-hidrometeorologicos", "ideam_colombia_official_observations"),
        ("smn_argentina", "https://www.smn.gob.ar/descarga-de-datos", "smn_argentina_official_observations"),
        ("smn_mexico", "https://smn.conagua.gob.mx/tools/RESOURCES/Diarios/", "smn_mexico_official_observations"),
    ]

    for provider, source_url, polling_focus in cases:
        resolution = parse_resolution_metadata(
            resolution_source=f"Resolution source: {provider} official observations",
            description="Official observed high temperature.",
            rules=f"Source: {source_url} official payload.",
        )

        route = build_resolution_source_route(structure, resolution, start_date="2026-04-25", end_date="2026-04-25")

        assert route.provider == provider
        assert route.latest_url == source_url
        assert route.history_url == source_url
        assert route.direct is True
        assert route.supported is True
        assert route.latency_tier == "direct_history"
        assert route.latency_priority == "direct_source_official_open_data"
        assert route.polling_focus == polling_focus


def test_build_resolution_source_route_preserves_africa_middle_east_official_source_urls() -> None:
    structure = parse_market_question("Will the highest temperature in Johannesburg be 28C or higher on April 25?")
    cases = [
        ("south_african_weather_service", "https://www.weathersa.co.za/home/historicalrain", "south_african_weather_service_official_observations"),
        ("nimet_nigeria", "https://nimet.gov.ng/weather-data", "nimet_nigeria_official_observations"),
        ("egyptian_meteorological_authority", "https://ema.gov.eg/wp/climate", "egyptian_meteorological_authority_official_observations"),
        ("israel_meteorological_service", "https://ims.gov.il/en/ObservationData", "israel_meteorological_service_official_observations"),
        ("turkish_meteorological_service", "https://www.mgm.gov.tr/eng/forecast-cities.aspx", "turkish_meteorological_service_official_observations"),
        ("saudi_ncm", "https://ncm.gov.sa/Ar/Weather/Pages/LocalWeather.aspx", "saudi_ncm_official_observations"),
    ]

    for provider, source_url, polling_focus in cases:
        resolution = parse_resolution_metadata(
            resolution_source=f"Resolution source: {provider} official observations",
            description="Official observed high temperature.",
            rules=f"Source: {source_url} official payload.",
        )

        route = build_resolution_source_route(structure, resolution, start_date="2026-04-25", end_date="2026-04-25")

        assert route.provider == provider
        assert route.latest_url == source_url
        assert route.history_url == source_url
        assert route.direct is True
        assert route.supported is True
        assert route.latency_tier == "direct_history"
        assert route.latency_priority == "direct_source_official_open_data"
        assert route.polling_focus == polling_focus


def test_build_resolution_source_route_preserves_asia_pacific_official_source_urls() -> None:
    structure = parse_market_question("Will the highest temperature in Seoul be 25C or higher on April 25?")
    cases = [
        ("kma_korea", "https://apihub.kma.go.kr/api/typ01/url/kma_sfctm.php?tm=20260425&stn=108", "kma_korea_official_observations"),
        ("taiwan_cwa", "https://opendata.cwa.gov.tw/api/v1/rest/datastore/O-A0001-001", "taiwan_cwa_official_observations"),
        ("mss_singapore", "https://api.data.gov.sg/v1/environment/air-temperature", "mss_singapore_official_observations"),
        ("metmalaysia", "https://api.met.gov.my/v2/data?datasetid=OBSERVATION_HOURLY", "metmalaysia_official_observations"),
        ("bmkg_indonesia", "https://data.bmkg.go.id/DataMKG/TEWS/autogempa.json", "bmkg_indonesia_official_observations"),
        ("tmd_thailand", "https://data.tmd.go.th/api/WeatherToday/V2/", "tmd_thailand_official_observations"),
        ("metservice_nz", "https://api.metservice.com/publicData/localObs/auckland", "metservice_nz_official_observations"),
        ("jma", "https://www.jma.go.jp/bosai/amedas/data/latest_time.txt", "jma_official_amedas_or_injected_payload"),
        ("pagasa", "https://www.pagasa.dost.gov.ph/weather/weather-observation-station", "pagasa_official_observations_or_injected_payload"),
        ("imd", "https://mausam.imd.gov.in/imd_latest/contents/aws_awsdata.php", "imd_official_observations_or_injected_payload"),
        ("bom", "https://reg.bom.gov.au/fwo/IDN60901/IDN60901.94767.json", "bom_official_observations_or_injected_payload"),
    ]

    for provider, source_url, polling_focus in cases:
        resolution = parse_resolution_metadata(
            resolution_source=f"Resolution source: {provider} official observations",
            description="Official observed high temperature.",
            rules=f"Source: {source_url} official payload.",
        )

        route = build_resolution_source_route(structure, resolution, start_date="2026-04-25", end_date="2026-04-25")

        assert route.provider == provider
        assert route.latest_url == source_url
        assert route.history_url == source_url
        assert route.direct is True
        assert route.supported is True
        assert route.latency_tier == "direct_history"
        assert route.latency_priority == "direct_source_official_open_data"
        assert route.polling_focus == polling_focus
