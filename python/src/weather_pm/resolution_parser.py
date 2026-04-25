from __future__ import annotations

import re

from weather_pm.models import ResolutionMetadata

_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_STATION_RE = re.compile(r"\b([A-Z]{4})\b")
_NON_STATION_CODES = {"DATA", "NOAA", "JSON"}
_WUNDERGROUND_CODE_RE = re.compile(r"/history/daily/(?:[^/]+/)+([A-Z]{4})(?:[/?#]|$)", re.IGNORECASE)
_ACCUWEATHER_URL_RE = re.compile(r"https?://[^\s?#]*accuweather\.com/[^\s?#]+", re.IGNORECASE)
_ACCUWEATHER_LOCATION_NAME_RE = re.compile(r"accuweather\.com/(?:[^\s/?#]+/){2}(?P<name>[^\s/?#]+)/", re.IGNORECASE)
_ENVIRONMENT_CANADA_STATION_RE = re.compile(r"\bStationID=(\d+)\b|\bstation\s+id\s+(\d+)\b", re.IGNORECASE)
_STATION_NAME_PATTERNS = (
    re.compile(r"\b(?:recorded|observed|published)\s+at\s+(?:the\s+)?(?P<name>[A-Za-z0-9 .'-]+?)\s+Station\b", re.IGNORECASE),
    re.compile(r"\bfor\s+(?P<name>[A-Za-z0-9 .'-]+?)\s+station\s+[A-Z]{4}\b", re.IGNORECASE),
)
WEATHER_SOURCE_PROVIDER_CATALOG = {
    "noaa": {"category": "official_us", "route_support": "direct_latest"},
    "aviation_weather": {"category": "official_aviation", "route_support": "direct_latest"},
    "iem_asos": {"category": "official_aviation", "route_support": "direct_history"},
    "wunderground": {"category": "commercial_page", "route_support": "direct_latest"},
    "accuweather": {"category": "commercial_page", "route_support": "direct_or_injected"},
    "hong_kong_observatory": {"category": "official_asia_pacific", "route_support": "direct_latest"},
    "environment_canada": {"category": "official_national", "route_support": "direct_history"},
    "meteostat": {"category": "aggregator", "route_support": "fallback_history"},
    "ecmwf_copernicus": {"category": "reanalysis", "route_support": "fallback_reanalysis"},
    "meteo_france": {"category": "official_europe", "route_support": "direct_api"},
    "uk_met_office": {"category": "official_europe", "route_support": "direct_or_injected"},
    "dwd": {"category": "official_europe", "route_support": "direct_history"},
    "bom": {"category": "official_asia_pacific", "route_support": "direct_or_injected"},
    "jma": {"category": "official_asia_pacific", "route_support": "direct_or_injected"},
    "pagasa": {"category": "official_asia_pacific", "route_support": "direct_or_injected"},
    "imd": {"category": "official_asia_pacific", "route_support": "direct_or_injected"},
    "national_weather_service": {"category": "generic_official", "route_support": "manual_review"},
    "web_scrape": {"category": "auditable_scrape", "route_support": "scrape_review"},
    "local_official_weather_source": {"category": "generic_official", "route_support": "scrape_review"},
    "weather_com": {"category": "commercial_page", "route_support": "unsupported"},
    "weatherapi": {"category": "commercial_api", "route_support": "direct_api"},
    "visual_crossing": {"category": "commercial_api", "route_support": "direct_api"},
    "weatherbit": {"category": "commercial_api", "route_support": "direct_api"},
    "tomorrow_io": {"category": "commercial_api", "route_support": "direct_api"},
    "meteoblue": {"category": "commercial_api", "route_support": "direct_api"},
    "open_meteo": {"category": "commercial_api", "route_support": "direct_api"},
    "openweather": {"category": "commercial_api", "route_support": "direct_api"},
    "yr_no": {"category": "commercial_api", "route_support": "direct_api"},
    "world_weather_online": {"category": "commercial_api", "route_support": "direct_api"},
    "meteomatics": {"category": "commercial_api", "route_support": "direct_api"},
    "weatherlink": {"category": "commercial_api", "route_support": "direct_api"},
    "ambient_weather": {"category": "commercial_api", "route_support": "direct_api"},
    "netatmo": {"category": "commercial_api", "route_support": "direct_api"},
    "windy": {"category": "commercial_api", "route_support": "direct_api"},
    "aerisweather": {"category": "commercial_api", "route_support": "direct_api"},
    "meteoswiss": {"category": "official_europe", "route_support": "direct_history"},
    "smhi": {"category": "official_europe", "route_support": "direct_history"},
    "knmi": {"category": "official_europe", "route_support": "direct_history"},
    "aemet": {"category": "official_europe", "route_support": "direct_history"},
    "met_eireann": {"category": "official_europe", "route_support": "direct_history"},
    "dmi": {"category": "official_europe", "route_support": "direct_history"},
    "meteochile": {"category": "official_latin_america", "route_support": "direct_history"},
    "inmet": {"category": "official_latin_america", "route_support": "direct_history"},
    "senamhi_peru": {"category": "official_latin_america", "route_support": "direct_history"},
    "ideam_colombia": {"category": "official_latin_america", "route_support": "direct_history"},
    "smn_argentina": {"category": "official_latin_america", "route_support": "direct_history"},
    "smn_mexico": {"category": "official_latin_america", "route_support": "direct_history"},
    "south_african_weather_service": {"category": "official_africa_middle_east", "route_support": "direct_history"},
    "nimet_nigeria": {"category": "official_africa_middle_east", "route_support": "direct_history"},
    "egyptian_meteorological_authority": {"category": "official_africa_middle_east", "route_support": "direct_history"},
    "israel_meteorological_service": {"category": "official_africa_middle_east", "route_support": "direct_history"},
    "turkish_meteorological_service": {"category": "official_africa_middle_east", "route_support": "direct_history"},
    "saudi_ncm": {"category": "official_africa_middle_east", "route_support": "direct_history"},
    "kma_korea": {"category": "official_asia_pacific", "route_support": "direct_history"},
    "taiwan_cwa": {"category": "official_asia_pacific", "route_support": "direct_history"},
    "mss_singapore": {"category": "official_asia_pacific", "route_support": "direct_history"},
    "metmalaysia": {"category": "official_asia_pacific", "route_support": "direct_history"},
    "bmkg_indonesia": {"category": "official_asia_pacific", "route_support": "direct_history"},
    "tmd_thailand": {"category": "official_asia_pacific", "route_support": "direct_history"},
    "metservice_nz": {"category": "official_asia_pacific", "route_support": "direct_history"},
}

_COMMERCIAL_WEATHER_PROVIDERS = {
    provider
    for provider, metadata in WEATHER_SOURCE_PROVIDER_CATALOG.items()
    if str(metadata["category"]) in {"commercial_api", "commercial_page"}
    or provider
    in {
        "meteoswiss",
        "smhi",
        "knmi",
        "aemet",
        "met_eireann",
        "dmi",
        "meteochile",
        "inmet",
        "senamhi_peru",
        "ideam_colombia",
        "smn_argentina",
        "smn_mexico",
        "south_african_weather_service",
        "nimet_nigeria",
        "egyptian_meteorological_authority",
        "israel_meteorological_service",
        "turkish_meteorological_service",
        "saudi_ncm",
        "kma_korea",
        "taiwan_cwa",
        "mss_singapore",
        "metmalaysia",
        "bmkg_indonesia",
        "tmd_thailand",
        "metservice_nz",
    }
}


def parse_resolution_metadata(*, resolution_source: str | None, description: str | None, rules: str | None) -> ResolutionMetadata:
    source_text = resolution_source or ""
    description_text = description or ""
    rules_text = rules or ""
    combined = " ".join(part for part in [source_text, description_text, rules_text] if part).strip()
    lowered = combined.lower()

    source_url = _extract_url(combined)
    provider = _detect_provider(lowered, source_url=source_url)
    station_code = _extract_station_code(combined, provider=provider)
    station_name = _extract_station_name(description_text, station_code)
    if provider == "accuweather" and station_name == description_text.strip():
        station_name = _extract_accuweather_location_name(combined)
    if station_name == description_text.strip() and station_code and station_code.isdigit():
        station_name = _extract_numeric_station_name(description_text, station_code)
    station_type = _classify_station_type(combined, station_code, provider)
    wording_clear = _is_wording_clear(lowered, provider, station_code)
    rules_clear = _are_rules_clear(lowered, provider, station_code)
    manual_review_needed = _needs_manual_review(provider, source_url, station_code, station_name, wording_clear, rules_clear)
    revision_risk = "high" if manual_review_needed else "low"

    return ResolutionMetadata(
        provider=provider,
        source_url=source_url,
        station_code=station_code,
        station_name=station_name,
        station_type=station_type,
        wording_clear=wording_clear,
        rules_clear=rules_clear,
        manual_review_needed=manual_review_needed,
        revision_risk=revision_risk,
    )


def _detect_provider(lowered: str, *, source_url: str | None) -> str:
    if any(token in lowered for token in ["iem asos", "iowa environmental mesonet", "mesonet.agron.iastate.edu", "asos archive"]):
        return "iem_asos"
    if any(token in lowered for token in ["hong kong observatory", "weather.gov.hk"]):
        return "hong_kong_observatory"
    if any(token in lowered for token in ["weather.gc.ca", "climate.weather.gc.ca", "environment and climate change canada", "environment canada"]):
        return "environment_canada"
    if any(token in lowered for token in ["official national meteorological service", "local official weather service", "local official meteorological service"]):
        return "national_weather_service"
    if any(token in lowered for token in ["ecmwf", "copernicus", "cds.climate.copernicus.eu"]):
        return "ecmwf_copernicus"
    if any(token in lowered for token in ["météo-france", "meteo-france", "meteofrance.com", "meteofrance.fr"]):
        return "meteo_france"
    if any(token in lowered for token in ["uk met office", "met office", "metoffice.gov.uk", "datapoint"]):
        return "uk_met_office"
    if any(token in lowered for token in ["dwd.de", "opendata.dwd.de", "dwd germany", "deutscher wetterdienst"]):
        return "dwd"
    if any(token in lowered for token in ["meteoswiss", "météosuisse", "meteoschweiz", "data.geo.admin.ch/ch.meteoschweiz"]):
        return "meteoswiss"
    if any(token in lowered for token in ["smhi", "opendata-download-metobs.smhi.se", "swedish meteorological and hydrological institute"]):
        return "smhi"
    if any(token in lowered for token in ["knmi", "dataplatform.knmi.nl", "koninklijk nederlands meteorologisch instituut"]):
        return "knmi"
    if any(token in lowered for token in ["aemet", "opendata.aemet.es", "agencia estatal de meteorología"]):
        return "aemet"
    if any(token in lowered for token in ["met éireann", "met eireann", "met.ie", "prodapi.metweb.ie"]):
        return "met_eireann"
    if any(token in lowered for token in ["dmigw.govcloud.dk", "dmi danish meteorological institute", "danish meteorological institute"]):
        return "dmi"
    if any(token in lowered for token in ["meteochile", "climatologia.meteochile.gob.cl", "dirección meteorológica de chile", "direccion meteorologica de chile"]):
        return "meteochile"
    if any(token in lowered for token in ["inmet", "apitempo.inmet.gov.br", "portal.inmet.gov.br", "instituto nacional de meteorologia"]):
        return "inmet"
    if any(token in lowered for token in ["senamhi", "senamhi.gob.pe"]):
        return "senamhi_peru"
    if any(token in lowered for token in ["ideam", "ideam.gov.co"]):
        return "ideam_colombia"
    if any(token in lowered for token in ["smn argentina", "smn.gob.ar", "servicio meteorológico nacional argentina", "servicio meteorologico nacional argentina"]):
        return "smn_argentina"
    if any(token in lowered for token in ["smn conagua", "smn.conagua.gob.mx", "conagua"]):
        return "smn_mexico"
    if any(token in lowered for token in ["south african weather service", "weathersa.co.za", "saws"]):
        return "south_african_weather_service"
    if any(token in lowered for token in ["nigerian meteorological agency", "nimet", "nimet.gov.ng"]):
        return "nimet_nigeria"
    if any(token in lowered for token in ["egyptian meteorological authority", "ema.gov.eg"]):
        return "egyptian_meteorological_authority"
    if any(token in lowered for token in ["israel meteorological service", "ims.gov.il"]):
        return "israel_meteorological_service"
    if any(token in lowered for token in ["turkish state meteorological service", "turkish meteorological service", "mgm.gov.tr"]):
        return "turkish_meteorological_service"
    if any(token in lowered for token in ["saudi national center for meteorology", "ncm.gov.sa", "saudi ncm"]):
        return "saudi_ncm"
    if any(token in lowered for token in ["korea meteorological administration", "apihub.kma.go.kr", "kma korea", "kma_korea"]):
        return "kma_korea"
    if any(token in lowered for token in ["central weather administration", "opendata.cwa.gov.tw", "taiwan cwa", "taiwan_cwa"]):
        return "taiwan_cwa"
    if any(token in lowered for token in ["meteorological service singapore", "api.data.gov.sg/v1/environment", "mss singapore", "mss_singapore"]):
        return "mss_singapore"
    if any(token in lowered for token in ["metmalaysia", "api.met.gov.my", "malaysian meteorological department"]):
        return "metmalaysia"
    if any(token in lowered for token in ["bmkg", "data.bmkg.go.id", "bmkg indonesia", "bmkg_indonesia"]):
        return "bmkg_indonesia"
    if any(token in lowered for token in ["thai meteorological department", "data.tmd.go.th", "tmd thailand", "tmd_thailand"]):
        return "tmd_thailand"
    if any(token in lowered for token in ["metservice new zealand", "api.metservice.com", "metservice nz", "metservice_nz"]):
        return "metservice_nz"
    if any(token in lowered for token in ["bom.gov.au", "bureau of meteorology"]):
        return "bom"
    if any(token in lowered for token in ["jma.go.jp", "japan meteorological agency"]):
        return "jma"
    if any(token in lowered for token in ["pagasa.dost.gov.ph", "pagasa"]):
        return "pagasa"
    if any(token in lowered for token in ["mausam.imd.gov.in", "india meteorological department"]):
        return "imd"
    if re.search(r"\bimd\b", lowered):
        return "imd"
    if any(token in lowered for token in ["api.met.no", "yr.no", "met norway", "norwegian meteorological institute"]):
        return "yr_no"
    if any(token in lowered for token in ["weatherapi.com", "weatherapi json", "weatherapi payload"]):
        return "weatherapi"
    if any(token in lowered for token in ["visual crossing", "visualcrossing.com", "weather.visualcrossing.com"]):
        return "visual_crossing"
    if any(token in lowered for token in ["weatherbit", "weatherbit.io"]):
        return "weatherbit"
    if any(token in lowered for token in ["tomorrow.io", "tomorrow io", "tomorrowio"]):
        return "tomorrow_io"
    if any(token in lowered for token in ["meteoblue", "meteo blue"]):
        return "meteoblue"
    if any(token in lowered for token in ["open-meteo", "openmeteo", "api.open-meteo.com"]):
        return "open_meteo"
    if any(token in lowered for token in ["openweathermap", "open weather map", "api.openweathermap.org", "openweather"]):
        return "openweather"
    if any(token in lowered for token in ["worldweatheronline", "world weather online", "api.worldweatheronline.com"]):
        return "world_weather_online"
    if any(token in lowered for token in ["meteomatics", "api.meteomatics.com"]):
        return "meteomatics"
    if any(token in lowered for token in ["weatherlink", "weatherlink.com", "api.weatherlink.com"]):
        return "weatherlink"
    if any(token in lowered for token in ["ambientweather", "ambient weather", "api.ambientweather.net"]):
        return "ambient_weather"
    if any(token in lowered for token in ["netatmo", "api.netatmo.com"]):
        return "netatmo"
    if any(token in lowered for token in ["windy.com", "api.windy.com", "windy api"]):
        return "windy"
    if any(token in lowered for token in ["aerisweather", "aeris weather", "api.aerisapi.com"]):
        return "aerisweather"
    if any(token in lowered for token in ["wunderground", "weather underground"]):
        return "wunderground"
    if any(token in lowered for token in ["accuweather"]):
        return "accuweather"
    if any(token in lowered for token in ["weather.com", "the weather channel"]):
        return "weather_com"
    if source_url and _mentions_local_official_weather_source(lowered):
        return "local_official_weather_source"
    if source_url and _mentions_scrape_target(lowered):
        return "web_scrape"
    if "noaa" in lowered or "national weather service" in lowered or re.search(r"(?<!aviation)weather\.gov", lowered):
        return "noaa"
    if any(token in lowered for token in ["aviationweather.gov", "metar", "aviation weather", "airport observations"]):
        return "aviation_weather"
    if any(token in lowered for token in ["meteostat", "meteostat.net"]):
        return "meteostat"
    return "unknown"


def _extract_url(text: str) -> str | None:
    match = _URL_RE.search(text)
    return match.group(0) if match else None


def _extract_station_code(text: str, *, provider: str) -> str | None:
    if provider in {"web_scrape", "local_official_weather_source"}:
        return None

    wunderground_match = _WUNDERGROUND_CODE_RE.search(text)
    if wunderground_match:
        return wunderground_match.group(1).upper()

    environment_canada_match = _ENVIRONMENT_CANADA_STATION_RE.search(text)
    if environment_canada_match:
        return environment_canada_match.group(1) or environment_canada_match.group(2)

    accuweather_key_from_url = _extract_accuweather_location_key(text)
    if accuweather_key_from_url:
        return accuweather_key_from_url

    accuweather_key_match = re.search(r"\blocation\s+key\s+(\d+)\b", text, re.IGNORECASE)
    if accuweather_key_match:
        return accuweather_key_match.group(1)

    station_keyword_match = re.search(r"station\s+([A-Z0-9]{4,8})\b", text, re.IGNORECASE)
    if station_keyword_match:
        raw_code = station_keyword_match.group(1)
        code = raw_code.upper()
        if code.isdigit():
            return code
        if raw_code == code and _STATION_RE.fullmatch(code) and code not in _NON_STATION_CODES:
            return code

    for match in _STATION_RE.finditer(text):
        code = match.group(1)
        if code not in _NON_STATION_CODES:
            return code
    return None


def _extract_accuweather_location_key(text: str) -> str | None:
    for url_match in _ACCUWEATHER_URL_RE.finditer(text):
        path = url_match.group(0).split("?", 1)[0].rstrip("/.,)")
        numeric_segments = re.findall(r"/(\d+)(?=/|$)", path)
        if numeric_segments:
            return numeric_segments[-1]
    return None


def _extract_station_name(description: str, station_code: str | None) -> str | None:
    if not description.strip():
        return None

    hong_kong_observatory_match = re.search(r"\bthe\s+(Hong Kong Observatory)\b|\b(Hong Kong Observatory)\b", description, re.IGNORECASE)
    if hong_kong_observatory_match:
        return _clean_station_name(hong_kong_observatory_match.group(1) or hong_kong_observatory_match.group(2))

    for pattern in _STATION_NAME_PATTERNS:
        match = pattern.search(description)
        if match:
            return _clean_station_name(match.group("name"))

    if station_code and station_code in description:
        station_name_match = re.search(rf"(?:recorded|observed|published)\s+at\s+(?:the\s+)?(?P<name>[A-Za-z0-9 .'-]+?)\s+station\s+{re.escape(station_code)}\b", description, re.IGNORECASE)
        if not station_name_match:
            station_name_match = re.search(rf"(?:at|for)\s+(?P<name>[A-Za-z0-9 .'-]+?)\s+station\s+{re.escape(station_code)}\b", description, re.IGNORECASE)
        if station_name_match:
            return _clean_station_name(station_name_match.group("name"))

    return description.strip() or None


def _extract_numeric_station_name(description: str, station_code: str) -> str | None:
    patterns = (
        rf"(?:at|for)\s+(?:the\s+)?(?P<name>[A-Za-z0-9 .'-]+?)\s+station\s+{re.escape(station_code)}\b",
        rf"(?P<name>[A-Za-z0-9 .'-]+?)\s+station\s+{re.escape(station_code)}\b",
    )
    for pattern in patterns:
        match = re.search(pattern, description, re.IGNORECASE)
        if match:
            return _clean_station_name(match.group("name"))
    return None


def _clean_station_name(name: str) -> str | None:
    cleaned = re.sub(r"\s+", " ", name).strip(" .,")
    cleaned = re.sub(r"\bthe\b\s+", "", cleaned, flags=re.IGNORECASE)
    return cleaned or None


def _extract_accuweather_location_name(text: str) -> str | None:
    match = _ACCUWEATHER_LOCATION_NAME_RE.search(text)
    if not match:
        return None
    name = match.group("name").replace("-", " ").title()
    return _clean_station_name(name)


def _classify_station_type(text: str, station_code: str | None, provider: str) -> str:
    if provider == "accuweather" and station_code:
        return "location"
    if provider == "environment_canada" and station_code:
        return "station"
    lowered = text.lower()
    if station_code and len(station_code) == 4 and not station_code.isdigit():
        return "airport"
    if "airport" in lowered:
        return "airport"
    if "station" in lowered or "observatory" in lowered:
        return "station"
    return "unknown"


def _is_wording_clear(lowered: str, provider: str, station_code: str | None) -> bool:
    markers = ["official", "observed", "resolves according to", "highest temperature", "lowest temperature", "recorded by", "recorded in", "current observed"]
    if station_code is not None:
        return any(marker in lowered for marker in markers)
    if provider == "hong_kong_observatory":
        return "hong kong observatory" in lowered and any(marker in lowered for marker in markers)
    if provider in {"accuweather", "bom", "jma", "pagasa", "imd", "ecmwf_copernicus", "meteo_france", "uk_met_office", "dwd", "environment_canada", "national_weather_service"}:
        return any(marker in lowered for marker in markers)
    if provider in _COMMERCIAL_WEATHER_PROVIDERS:
        return any(marker in lowered for marker in markers)
    if provider == "meteostat":
        return any(marker in lowered for marker in markers)
    if provider in {"web_scrape", "local_official_weather_source"}:
        return any(marker in lowered for marker in markers) or _mentions_scrape_target(lowered)
    return False


def _are_rules_clear(lowered: str, provider: str, station_code: str | None) -> bool:
    if provider == "unknown":
        return False
    if provider == "hong_kong_observatory":
        clarity_tokens = ["source", "observatory", "daily extract", "weather.gov.hk", "finalized"]
        return any(token in lowered for token in clarity_tokens)
    if provider == "environment_canada":
        clarity_tokens = ["source", "environment canada", "environment and climate change canada", "climatedata", "weather.gc.ca", "finalized"]
        return any(token in lowered for token in clarity_tokens)
    if provider == "national_weather_service":
        clarity_tokens = ["official national meteorological service", "local official weather service", "official weather service", "source"]
        return any(token in lowered for token in clarity_tokens)
    if provider in _COMMERCIAL_WEATHER_PROVIDERS:
        clarity_tokens = ["source", "api", "json", "payload", "weather.com", "weatherapi", "visual crossing", "weatherbit", "tomorrow.io", "meteoblue", "open-meteo", "openweathermap", "api.met.no", "yr.no", "worldweatheronline", "meteomatics", "weatherlink", "ambient weather", "netatmo", "windy", "aerisweather", "the weather channel"]
        return any(token in lowered for token in clarity_tokens)
    if provider == "accuweather":
        clarity_tokens = ["source", "accuweather", "location key", "daily forecast", "current conditions"]
        return any(token in lowered for token in clarity_tokens)
    if provider == "meteostat":
        clarity_tokens = ["source", "meteostat", "daily", "tmax", "tmin"]
        return any(token in lowered for token in clarity_tokens)
    if provider == "ecmwf_copernicus":
        clarity_tokens = ["source", "ecmwf", "copernicus", "cds.climate.copernicus.eu", "reanalysis", "era5", "daily"]
        return any(token in lowered for token in clarity_tokens)
    if provider == "meteo_france":
        clarity_tokens = ["source", "météo-france", "meteo-france", "meteofrance.com", "meteofrance.fr", "official"]
        return any(token in lowered for token in clarity_tokens)
    if provider == "uk_met_office":
        clarity_tokens = ["source", "uk met office", "met office", "metoffice.gov.uk", "datapoint", "official"]
        return any(token in lowered for token in clarity_tokens)
    if provider == "dwd":
        clarity_tokens = ["source", "dwd", "opendata.dwd.de", "dwd.de", "open-data", "open data", "station"]
        return any(token in lowered for token in clarity_tokens)
    if provider in {"bom", "jma", "pagasa", "imd"}:
        clarity_tokens = ["source", "official", "observations", "station", "bom", "jma", "pagasa", "imd"]
        return any(token in lowered for token in clarity_tokens)
    if provider in {"web_scrape", "local_official_weather_source"}:
        clarity_tokens = ["source", "website", "page", "html", "table", "scrape", "data"]
        return any(token in lowered for token in clarity_tokens)
    if station_code is None:
        return False
    if provider in {"aviation_weather", "iem_asos"}:
        clarity_tokens = ["source", "station", "official", "aviationweather.gov", "metar", "aviation weather", "airport observations"]
        if provider == "iem_asos":
            clarity_tokens.extend(["mesonet", "asos", "iem"])
        return any(token in lowered for token in clarity_tokens)
    clarity_tokens = ["source", "station", "official", "weather.gov", "daily climate report"]
    return any(token in lowered for token in clarity_tokens)


def _needs_manual_review(provider: str, source_url: str | None, station_code: str | None, station_name: str | None, wording_clear: bool, rules_clear: bool) -> bool:
    if provider in {"web_scrape", "local_official_weather_source"}:
        return True
    if provider == "unknown" or not wording_clear or not rules_clear:
        return True
    if provider in _COMMERCIAL_WEATHER_PROVIDERS:
        return source_url is None
    if provider == "national_weather_service":
        return True
    if station_code is not None:
        return False
    return station_name is None


def _mentions_local_official_weather_source(lowered: str) -> bool:
    official_marker = any(token in lowered for token in ["official local", "official city", "official country", "local official", "official weather source"])
    weather_marker = any(token in lowered for token in ["weather station", "weather source", "weather service", "meteorological", "observatory"])
    local_marker = any(token in lowered for token in ["local", "city", "country"])
    return weather_marker and (official_marker or ("official" in lowered and local_marker))


def _mentions_scrape_target(lowered: str) -> bool:
    return any(token in lowered for token in ["website", "web page", " webpage", "page", "html", "table", "scrape"])
