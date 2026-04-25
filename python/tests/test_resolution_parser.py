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


def test_parse_resolution_metadata_detects_iem_asos_station_source() -> None:
    result = parse_resolution_metadata(
        resolution_source="Iowa Environmental Mesonet ASOS archive for station KDEN",
        description="Official ASOS/METAR observed high temperature at Denver International Airport station KDEN.",
        rules="Source: https://mesonet.agron.iastate.edu/request/download.phtml ASOS one-minute station archive.",
    )

    assert result.provider == "iem_asos"
    assert result.source_url == "https://mesonet.agron.iastate.edu/request/download.phtml"
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


def test_parse_resolution_metadata_detects_commercial_weather_provider_names_and_domains() -> None:
    cases = [
        ("Weather.com / The Weather Channel", "https://weather.com/weather/today/l/Miami", "weather_com"),
        ("WeatherAPI.com current JSON", "https://api.weatherapi.com/v1/current.json?q=Miami", "weatherapi"),
        ("Visual Crossing timeline API", "https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/Miami", "visual_crossing"),
        ("Weatherbit daily history", "https://api.weatherbit.io/v2.0/history/daily?city=Miami", "weatherbit"),
        ("Tomorrow.io weather API", "https://api.tomorrow.io/v4/weather/history/recent?location=Miami", "tomorrow_io"),
        ("MeteoBlue basic day API", "https://my.meteoblue.com/packages/basic-day?lat=25.76&lon=-80.19", "meteoblue"),
    ]

    for name, url, provider in cases:
        result = parse_resolution_metadata(
            resolution_source=f"Resolution source: {name}",
            description="This market resolves to the highest temperature observed for Miami.",
            rules=f"Source: {url}",
        )

        assert result.provider == provider
        assert result.source_url == url
        assert result.wording_clear is True
        assert result.rules_clear is True
        assert result.manual_review_needed is (provider == "weather_com")


def test_parse_resolution_metadata_marks_commercial_api_without_url_for_manual_review() -> None:
    result = parse_resolution_metadata(
        resolution_source="Resolution source: WeatherAPI.com",
        description="This market resolves to the highest temperature observed for Miami.",
        rules="Use the commercial API result.",
    )

    assert result.provider == "weatherapi"
    assert result.source_url is None
    assert result.manual_review_needed is True
    assert result.revision_risk == "high"


def test_parse_resolution_metadata_detects_ecmwf_copernicus_domains() -> None:
    result = parse_resolution_metadata(
        resolution_source="Copernicus Climate Data Store reanalysis",
        description="This market resolves to the highest temperature recorded in Paris.",
        rules="Use https://cds.climate.copernicus.eu/api/reanalysis daily data from ECMWF.",
    )

    assert result.provider == "ecmwf_copernicus"
    assert result.source_url == "https://cds.climate.copernicus.eu/api/reanalysis"
    assert result.station_code is None
    assert result.wording_clear is True
    assert result.rules_clear is True


def test_parse_resolution_metadata_detects_meteo_france_source() -> None:
    result = parse_resolution_metadata(
        resolution_source="Météo-France official observations",
        description="This market resolves to the lowest temperature recorded in Paris.",
        rules="Source: https://meteofrance.com/api/observations daily official data.",
    )

    assert result.provider == "meteo_france"
    assert result.source_url == "https://meteofrance.com/api/observations"
    assert result.station_type == "unknown"
    assert result.wording_clear is True
    assert result.rules_clear is True


def test_parse_resolution_metadata_detects_uk_met_office_datapoint_source() -> None:
    result = parse_resolution_metadata(
        resolution_source="UK Met Office DataPoint observations",
        description="This market resolves to the highest temperature recorded in London.",
        rules="Source: https://www.metoffice.gov.uk/datapoint official site observations.",
    )

    assert result.provider == "uk_met_office"
    assert result.source_url == "https://www.metoffice.gov.uk/datapoint"
    assert result.wording_clear is True
    assert result.rules_clear is True


def test_parse_resolution_metadata_detects_dwd_opendata_source() -> None:
    result = parse_resolution_metadata(
        resolution_source="DWD Germany open-data observations for station 10384",
        description="This market resolves to the highest temperature recorded in Berlin.",
        rules="Source: https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/daily/kl/ station 10384.",
    )

    assert result.provider == "dwd"
    assert result.source_url == "https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/daily/kl/"
    assert result.station_code == "10384"
    assert result.station_type == "station"
    assert result.wording_clear is True
    assert result.rules_clear is True
    assert result.manual_review_needed is False


def test_parse_resolution_metadata_detects_bom_station_source() -> None:
    result = parse_resolution_metadata(
        resolution_source="Bureau of Meteorology station 066062",
        description="This market resolves to the official highest temperature observed at Sydney Observatory Hill station 066062.",
        rules="Source: https://www.bom.gov.au/products/IDN60801/IDN60801.94768.shtml official BOM observations.",
    )

    assert result.provider == "bom"
    assert result.source_url == "https://www.bom.gov.au/products/IDN60801/IDN60801.94768.shtml"
    assert result.station_code == "066062"
    assert result.station_name == "Sydney Observatory Hill"
    assert result.station_type == "station"
    assert result.wording_clear is True
    assert result.rules_clear is True
    assert result.manual_review_needed is False


def test_parse_resolution_metadata_detects_jma_station_source() -> None:
    result = parse_resolution_metadata(
        resolution_source="Japan Meteorological Agency station 44132",
        description="This market resolves to the lowest temperature recorded at Tokyo station 44132.",
        rules="Source: https://www.jma.go.jp/bosai/amedas/ official JMA observations.",
    )

    assert result.provider == "jma"
    assert result.source_url == "https://www.jma.go.jp/bosai/amedas/"
    assert result.station_code == "44132"
    assert result.station_name == "Tokyo"
    assert result.station_type == "station"
    assert result.wording_clear is True
    assert result.rules_clear is True
    assert result.manual_review_needed is False


def test_parse_resolution_metadata_detects_pagasa_domain_for_manual_auditable_source() -> None:
    result = parse_resolution_metadata(
        resolution_source="PAGASA official page",
        description="This market resolves to the current observed temperature in Manila.",
        rules="Source: https://pagasa.dost.gov.ph/weather official observations.",
    )

    assert result.provider == "pagasa"
    assert result.source_url == "https://pagasa.dost.gov.ph/weather"
    assert result.station_code is None
    assert result.wording_clear is True
    assert result.rules_clear is True
    assert result.manual_review_needed is False


def test_parse_resolution_metadata_detects_imd_mausam_domain() -> None:
    result = parse_resolution_metadata(
        resolution_source="IMD station 42182",
        description="This market resolves to the highest temperature recorded at New Delhi station 42182.",
        rules="Source: https://mausam.imd.gov.in/ official IMD observations.",
    )

    assert result.provider == "imd"
    assert result.source_url == "https://mausam.imd.gov.in/"
    assert result.station_code == "42182"
    assert result.station_name == "New Delhi"
    assert result.station_type == "station"
    assert result.wording_clear is True
    assert result.rules_clear is True
    assert result.manual_review_needed is False


def test_parse_resolution_metadata_detects_environment_canada_official_source() -> None:
    result = parse_resolution_metadata(
        resolution_source="https://climate.weather.gc.ca/climateData/dailydata_e.html?StationID=51442",
        description="This market resolves to the highest temperature recorded in Toronto by Environment and Climate Change Canada.",
        rules="Use the finalized Environment Canada climateData daily row from climate.weather.gc.ca.",
    )

    assert result.provider == "environment_canada"
    assert result.source_url == "https://climate.weather.gc.ca/climateData/dailydata_e.html?StationID=51442"
    assert result.station_code == "51442"
    assert result.station_type == "station"
    assert result.wording_clear is True
    assert result.rules_clear is True
    assert result.manual_review_needed is False


def test_parse_resolution_metadata_detects_generic_official_national_weather_service_without_station_code() -> None:
    result = parse_resolution_metadata(
        resolution_source="Official national meteorological service for Mexico City",
        description="This market resolves to the highest temperature recorded by the local official weather service.",
        rules="Use the official national meteorological service report if available.",
    )

    assert result.provider == "national_weather_service"
    assert result.station_code is None
    assert result.station_type == "unknown"
    assert result.wording_clear is True
    assert result.rules_clear is True
    assert result.manual_review_needed is True


def test_parse_resolution_metadata_detects_local_official_weather_source_with_url() -> None:
    result = parse_resolution_metadata(
        resolution_source="Official local city weather station source: https://weather.example.gov/city/daily",
        description="This market resolves to the highest temperature recorded by the official local weather source.",
        rules="Use the linked country weather station DATA table after publication.",
    )

    assert result.provider == "local_official_weather_source"
    assert result.source_url == "https://weather.example.gov/city/daily"
    assert result.station_code is None
    assert result.station_type == "station"
    assert result.wording_clear is True
    assert result.rules_clear is True
    assert result.manual_review_needed is True


def test_parse_resolution_metadata_detects_generic_web_scrape_page_with_url() -> None:
    result = parse_resolution_metadata(
        resolution_source="Public website page: https://example.com/weather/history.html",
        description="This market resolves from the temperature table on the linked HTML page.",
        rules="Scrape the table on the source website after the daily data is posted.",
    )

    assert result.provider == "web_scrape"
    assert result.source_url == "https://example.com/weather/history.html"
    assert result.station_code is None
    assert result.station_type == "unknown"
    assert result.wording_clear is True
    assert result.rules_clear is True
    assert result.manual_review_needed is True



def test_parse_resolution_metadata_detects_additional_global_api_and_iot_sources() -> None:
    cases = [
        ("Open-Meteo forecast API", "https://api.open-meteo.com/v1/forecast?latitude=25.76&longitude=-80.19", "open_meteo"),
        ("OpenWeatherMap One Call API", "https://api.openweathermap.org/data/3.0/onecall?lat=25.76&lon=-80.19", "openweather"),
        ("MET Norway api.met.no locationforecast", "https://api.met.no/weatherapi/locationforecast/2.0/compact?lat=59.9&lon=10.7", "yr_no"),
        ("World Weather Online historical API", "https://api.worldweatheronline.com/premium/v1/past-weather.ashx?q=Miami", "world_weather_online"),
        ("Meteomatics timeseries API", "https://api.meteomatics.com/2026-04-25T00:00:00Z/t_2m:C/25.76,-80.19/json", "meteomatics"),
        ("WeatherLink station API", "https://api.weatherlink.com/v2/current/12345", "weatherlink"),
        ("Ambient Weather station API", "https://api.ambientweather.net/v1/devices", "ambient_weather"),
        ("Netatmo weather station API", "https://api.netatmo.com/api/getmeasure", "netatmo"),
        ("Windy API point forecast", "https://api.windy.com/api/point-forecast/v2", "windy"),
        ("AerisWeather observations API", "https://api.aerisapi.com/observations/miami,fl", "aerisweather"),
    ]

    for name, url, provider in cases:
        result = parse_resolution_metadata(
            resolution_source=f"Resolution source: {name}",
            description="This market resolves to the highest temperature observed for Miami.",
            rules=f"Source: {url} JSON payload.",
        )

        assert result.provider == provider
        assert result.source_url == url
        assert result.wording_clear is True
        assert result.rules_clear is True
        assert result.manual_review_needed is False


def test_parse_resolution_metadata_detects_additional_european_official_sources() -> None:
    cases = [
        ("MeteoSwiss official station data", "https://data.geo.admin.ch/ch.meteoschweiz.messwerte-aktuell/VQHA80.csv", "meteoswiss"),
        ("SMHI Open Data observations", "https://opendata-download-metobs.smhi.se/api/version/latest/parameter/1/station/98210/period/latest-day/data.json", "smhi"),
        ("KNMI Data Platform daily observations", "https://api.dataplatform.knmi.nl/open-data/v1/datasets/etmaalgegevensKNMIstations/versions/1/files", "knmi"),
        ("AEMET OpenData observations", "https://opendata.aemet.es/opendata/api/observacion/convencional/datos/estacion/3195", "aemet"),
        ("Met Éireann observations", "https://prodapi.metweb.ie/observations/phoenix-park/today", "met_eireann"),
        ("DMI Danish Meteorological Institute observations", "https://dmigw.govcloud.dk/v2/metObs/collections/observation/items?stationId=06181", "dmi"),
    ]

    for name, url, provider in cases:
        result = parse_resolution_metadata(
            resolution_source=f"Resolution source: {name}",
            description="This market resolves to the highest temperature observed by the official service.",
            rules=f"Source: {url} official JSON/CSV payload.",
        )

        assert result.provider == provider
        assert result.source_url == url
        assert result.wording_clear is True
        assert result.rules_clear is True
        assert result.manual_review_needed is False


def test_parse_resolution_metadata_detects_latin_american_official_sources() -> None:
    cases = [
        ("MeteoChile official observations", "https://climatologia.meteochile.gob.cl/application/diario/visorDeDatos", "meteochile"),
        ("INMET Brazil official station data", "https://apitempo.inmet.gov.br/estacao/2026-04-25/2026-04-25/A701", "inmet"),
        ("SENAMHI Peru official observations", "https://www.senamhi.gob.pe/mapas/mapa-estaciones-2/", "senamhi_peru"),
        ("IDEAM Colombia official observations", "https://www.ideam.gov.co/web/tiempo-y-clima/consulta-y-descarga-de-datos-hidrometeorologicos", "ideam_colombia"),
        ("SMN Argentina official observations", "https://www.smn.gob.ar/descarga-de-datos", "smn_argentina"),
        ("SMN CONAGUA Mexico official observations", "https://smn.conagua.gob.mx/tools/RESOURCES/Diarios/", "smn_mexico"),
    ]

    for name, url, provider in cases:
        result = parse_resolution_metadata(
            resolution_source=f"Resolution source: {name}",
            description="This market resolves to the highest temperature observed by the official weather service.",
            rules=f"Source: {url} official station payload.",
        )

        assert result.provider == provider
        assert result.source_url == url
        assert result.wording_clear is True
        assert result.rules_clear is True
        assert result.manual_review_needed is False


def test_parse_resolution_metadata_detects_africa_middle_east_official_sources() -> None:
    cases = [
        ("South African Weather Service observations", "https://www.weathersa.co.za/home/historicalrain", "south_african_weather_service"),
        ("Nigerian Meteorological Agency observations", "https://nimet.gov.ng/weather-data", "nimet_nigeria"),
        ("Egyptian Meteorological Authority observations", "https://ema.gov.eg/wp/climate", "egyptian_meteorological_authority"),
        ("Israel Meteorological Service observations", "https://ims.gov.il/en/ObservationData", "israel_meteorological_service"),
        ("Turkish State Meteorological Service observations", "https://www.mgm.gov.tr/eng/forecast-cities.aspx", "turkish_meteorological_service"),
        ("Saudi National Center for Meteorology observations", "https://ncm.gov.sa/Ar/Weather/Pages/LocalWeather.aspx", "saudi_ncm"),
    ]

    for name, url, provider in cases:
        result = parse_resolution_metadata(
            resolution_source=f"Resolution source: {name}",
            description="This market resolves to the highest temperature observed by the official meteorological service.",
            rules=f"Source: {url} official station payload.",
        )

        assert result.provider == provider
        assert result.source_url == url
        assert result.wording_clear is True
        assert result.rules_clear is True
        assert result.manual_review_needed is False


def test_parse_resolution_metadata_detects_asia_pacific_official_sources() -> None:
    cases = [
        ("Korea Meteorological Administration official observations", "https://apihub.kma.go.kr/api/typ01/url/kma_sfctm.php?tm=20260425&stn=108", "kma_korea"),
        ("Taiwan Central Weather Administration observations", "https://opendata.cwa.gov.tw/api/v1/rest/datastore/O-A0001-001", "taiwan_cwa"),
        ("Meteorological Service Singapore observations", "https://api.data.gov.sg/v1/environment/air-temperature", "mss_singapore"),
        ("MetMalaysia official observations", "https://api.met.gov.my/v2/data?datasetid=OBSERVATION_HOURLY", "metmalaysia"),
        ("BMKG Indonesia official observations", "https://data.bmkg.go.id/DataMKG/TEWS/autogempa.json", "bmkg_indonesia"),
        ("Thai Meteorological Department observations", "https://data.tmd.go.th/api/WeatherToday/V2/", "tmd_thailand"),
        ("MetService New Zealand official observations", "https://api.metservice.com/publicData/localObs/auckland", "metservice_nz"),
        ("Hong Kong Observatory observations", "https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=rhrread&lang=en", "hong_kong_observatory"),
        ("Japan Meteorological Agency AMeDAS observations", "https://www.jma.go.jp/bosai/amedas/data/latest_time.txt", "jma"),
        ("PAGASA official observations", "https://www.pagasa.dost.gov.ph/weather/weather-observation-station", "pagasa"),
        ("India Meteorological Department observations", "https://mausam.imd.gov.in/imd_latest/contents/aws_awsdata.php", "imd"),
        ("Australian Bureau of Meteorology observations", "https://reg.bom.gov.au/fwo/IDN60901/IDN60901.94767.json", "bom"),
    ]

    for name, url, provider in cases:
        result = parse_resolution_metadata(
            resolution_source=f"Resolution source: {name}",
            description="This market resolves to the highest temperature observed by the official meteorological service.",
            rules=f"Source: {url} official station payload.",
        )

        assert result.provider == provider
        assert result.source_url == url
        assert result.wording_clear is True
        assert result.rules_clear is True
        assert result.manual_review_needed is False


def test_parse_resolution_metadata_detects_synoptic_mesowest_station_api_source() -> None:
    result = parse_resolution_metadata(
        resolution_source="Synoptic/MesoWest station observations for station KDEN",
        description="This market resolves to the highest temperature observed at Denver station KDEN.",
        rules="Source: https://api.synopticdata.com/v2/stations/timeseries?stid=KDEN official JSON payload.",
    )

    assert result.provider == "synoptic_mesowest"
    assert result.source_url == "https://api.synopticdata.com/v2/stations/timeseries?stid=KDEN"
    assert result.station_code == "KDEN"
    assert result.station_type == "airport"
    assert result.wording_clear is True
    assert result.rules_clear is True
    assert result.manual_review_needed is False
