from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from weather_pm.models import MarketStructure, ResolutionMetadata

_COMMERCIAL_API_PROVIDERS = {
    "weatherapi",
    "visual_crossing",
    "weatherbit",
    "tomorrow_io",
    "meteoblue",
    "open_meteo",
    "openweather",
    "yr_no",
    "world_weather_online",
    "meteomatics",
    "weatherlink",
    "ambient_weather",
    "netatmo",
    "windy",
    "aerisweather",
}
_DIRECT_OFFICIAL_URL_PROVIDERS = {
    "uk_met_office": "uk_met_office_injected_payload_or_explicit_endpoint",
    "dwd": "dwd_open_data_daily_observations",
    "bom": "bom_official_observations_or_injected_payload",
    "jma": "jma_official_amedas_or_injected_payload",
    "pagasa": "pagasa_official_observations_or_injected_payload",
    "imd": "imd_official_observations_or_injected_payload",
}


@dataclass(slots=True)
class ResolutionSourceRoute:
    provider: str
    station_code: str | None
    station_name: str | None
    source_url: str | None
    latest_url: str | None
    history_url: str | None
    direct: bool
    supported: bool
    latency_tier: str
    latency_priority: str
    polling_focus: str
    manual_review_needed: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_resolution_source_route(
    structure: MarketStructure,
    resolution: ResolutionMetadata,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> ResolutionSourceRoute:
    """Describe the lowest-latency source path implied by a market's resolution rules."""
    if resolution.provider == "noaa" and resolution.station_code:
        latest_url = _noaa_latest_url(resolution.station_code)
        history_url = _noaa_history_url(structure, resolution.station_code, start_date=start_date, end_date=end_date)
        daily_summary = _uses_noaa_daily_summary(structure, start_date=start_date, end_date=end_date)
        return _route(
            structure,
            resolution,
            latest_url=latest_url,
            history_url=history_url,
            direct=True,
            supported=True,
            latency_tier="direct_history" if daily_summary else "direct_latest",
            latency_priority="direct_source_low_latency",
            polling_focus="noaa_official_daily_summary" if daily_summary else "station_observations_latest",
            reason=(
                "NOAA station code found in resolution rules; poll NOAA/NCEI daily summaries for official daily high/low."
                if daily_summary
                else "NOAA station code found in resolution rules; poll weather.gov station observations directly."
            ),
        )

    if resolution.provider == "wunderground" and resolution.source_url and resolution.station_code:
        history_url = _wunderground_history_url(resolution.source_url, start_date=start_date, end_date=end_date)
        return _route(structure, resolution, latest_url=resolution.source_url, history_url=history_url, direct=True, supported=True, latency_tier="direct_latest", latency_priority="direct_source_low_latency", polling_focus="station_history_page", reason="Wunderground station page found in resolution rules; poll the station page directly without city geocoding.")

    if resolution.provider == "accuweather" and resolution.source_url:
        return _route(structure, resolution, latest_url=resolution.source_url, history_url=_accuweather_history_url(resolution.source_url), direct=True, supported=True, latency_tier="direct_latest", latency_priority="direct_source_low_latency", polling_focus="accuweather_location_page_or_injected_json", reason="AccuWeather source URL found in resolution rules; route directly to the auditable page and parse injected JSON payloads. Live AccuWeather API use requires an API key supplied outside tests.")

    if resolution.provider == "aviation_weather" and resolution.station_code:
        return _route(structure, resolution, latest_url=_aviation_weather_url(resolution.station_code), history_url=_aviation_weather_url(resolution.station_code, start_date=start_date, end_date=end_date), direct=True, supported=True, latency_tier="direct_latest", latency_priority="direct_source_low_latency", polling_focus="aviation_weather_metar_observations", reason="AviationWeather METAR station code found in resolution rules; poll station observations directly.")

    if resolution.provider == "hong_kong_observatory":
        latest_url = _hko_latest_url(resolution.source_url)
        history_url = _hko_daily_extract_url(structure, start_date=start_date, end_date=end_date)
        return _route(structure, resolution, station_code=resolution.station_code or "HKO", station_name=resolution.station_name or "Hong Kong Observatory", latest_url=latest_url, history_url=history_url, direct=True, supported=True, latency_tier="direct_latest", latency_priority="direct_source_low_latency", polling_focus="hko_current_weather_and_daily_extract", reason="Hong Kong Observatory source found in resolution rules; poll HKO current weather and official monthly daily extract directly.")

    if resolution.provider == "meteostat" and (resolution.station_code or structure.city):
        history_url = _meteostat_history_url(structure, resolution, start_date=start_date, end_date=end_date)
        has_station = resolution.station_code is not None
        return _route(structure, resolution, latest_url=None, history_url=history_url, direct=False, supported=True, latency_tier="fallback_history", latency_priority="fallback_daily_history" if has_station else "fallback_city_daily_history", polling_focus="meteostat_daily_history" if has_station else "meteostat_city_daily_history", reason="Meteostat historical daily data is available as a fallback; use injected daily tmax/tmin payloads rather than direct official station polling.")

    if resolution.provider in _COMMERCIAL_API_PROVIDERS:
        if resolution.source_url:
            return _route(structure, resolution, latest_url=resolution.source_url, history_url=resolution.source_url, direct=True, supported=True, latency_tier="direct_api", latency_priority="direct_source_low_latency", polling_focus=f"{resolution.provider}_injected_payload", reason=f"{resolution.provider} source URL found; use explicit API/payload URL. Live API access may require an API key supplied outside tests.")
        return _unsupported(structure, resolution, latency_tier="api_key_required", polling_focus="manual_review", reason=f"{resolution.provider} requires an explicit source_url/API endpoint before automated polling; manual review required.")

    if resolution.provider == "weather_com":
        return _unsupported(structure, resolution, latency_tier="scraping_unsupported", polling_focus="manual_review", reason="Weather.com/The Weather Channel pages require browser scraping or an API key; manual scraping review required.")

    if resolution.provider == "ecmwf_copernicus":
        history_url = None
        if start_date and end_date:
            history_url = f"ecmwf_copernicus://reanalysis?{urlencode({'city': structure.city, 'start': start_date, 'end': end_date})}"
        return _route(structure, resolution, latest_url=None, history_url=history_url, direct=False, supported=True, latency_tier="fallback_reanalysis", latency_priority="fallback_reanalysis_not_low_latency", polling_focus="ecmwf_copernicus_reanalysis_manual_or_injected_payload", reason="ECMWF/Copernicus ERA5 is a reanalysis fallback, not a low-latency direct official station source.")

    if resolution.provider == "meteo_france" and not resolution.source_url:
        return _unsupported(structure, resolution, latency_tier="unsupported", polling_focus="manual_review_api_key_required", reason="Météo-France observations need an explicit API/source_url; api_key_required/manual review before automated polling.")

    if resolution.provider == "meteo_france" and resolution.source_url:
        return _route(structure, resolution, latest_url=resolution.source_url, history_url=resolution.source_url, direct=True, supported=True, latency_tier="direct_api", latency_priority="direct_source_low_latency", polling_focus="meteo_france_daily_payload", reason="Explicit Météo-France endpoint supplied; parse the injected official payload directly.")

    if resolution.provider == "environment_canada" and resolution.source_url:
        history_url = _environment_canada_history_url(resolution.source_url, start_date=start_date, end_date=end_date)
        return _route(structure, resolution, latest_url=resolution.source_url, history_url=history_url, direct=True, supported=True, latency_tier="direct_history", latency_priority="direct_source_official_open_data", polling_focus="environment_canada_official_history", reason="Environment Canada climateData URL found; poll the official daily climate rows directly.")

    if resolution.provider in _DIRECT_OFFICIAL_URL_PROVIDERS:
        if resolution.source_url:
            latency_priority = "direct_source_official_open_data" if resolution.provider == "dwd" else "direct_source_low_latency"
            key_note = " API key may be required outside route metadata." if resolution.provider == "uk_met_office" else ""
            return _route(structure, resolution, latest_url=resolution.source_url, history_url=resolution.source_url, direct=True, supported=True, latency_tier="direct_history", latency_priority=latency_priority, polling_focus=_DIRECT_OFFICIAL_URL_PROVIDERS[resolution.provider], reason=f"{resolution.provider} explicit official source URL found; parse official/injected observations directly.{key_note}")
        return _unsupported(structure, resolution, latency_tier="unsupported", polling_focus="manual_review", reason=f"{resolution.provider} requires an explicit source_url before automated polling; manual review required.")

    if resolution.provider == "national_weather_service":
        return _route(structure, resolution, latest_url=resolution.source_url, history_url=None, direct=False, supported=False, latency_tier="manual_review", latency_priority="manual_review_required", polling_focus="manual_review_official_national_service", manual_review_needed=True, reason="Generic national meteorological service identified; manual review required to map the exact endpoint/station.")

    if resolution.provider == "web_scrape" and resolution.source_url:
        return _route(structure, resolution, latest_url=resolution.source_url, history_url=resolution.source_url, direct=False, supported=True, latency_tier="scrape_target", latency_priority="auditable_scrape_target", polling_focus="manual_html_extraction", manual_review_needed=True, reason="Auditable HTML/table scrape target found; parse table-like payloads only with manual review.")

    if resolution.provider == "local_official_weather_source" and resolution.source_url:
        return _route(structure, resolution, latest_url=resolution.source_url, history_url=resolution.source_url, direct=False, supported=True, latency_tier="scrape_target", latency_priority="auditable_scrape_target", polling_focus="local_official_source_review", manual_review_needed=True, reason="Local official source URL found; supported as an auditable scrape target pending manual source review.")

    return _unsupported(structure, resolution, latency_tier="unsupported", polling_focus="manual_review", reason=f"No direct route for provider={resolution.provider!r} station={resolution.station_code!r}; manual source review required.")


def _route(structure: MarketStructure, resolution: ResolutionMetadata, *, latest_url: str | None, history_url: str | None, direct: bool, supported: bool, latency_tier: str, latency_priority: str, polling_focus: str, reason: str, station_code: str | None = None, station_name: str | None = None, manual_review_needed: bool | None = None) -> ResolutionSourceRoute:
    del structure
    return ResolutionSourceRoute(provider=resolution.provider, station_code=resolution.station_code if station_code is None else station_code, station_name=resolution.station_name if station_name is None else station_name, source_url=resolution.source_url, latest_url=latest_url, history_url=history_url, direct=direct, supported=supported, latency_tier=latency_tier, latency_priority=latency_priority, polling_focus=polling_focus, manual_review_needed=resolution.manual_review_needed if manual_review_needed is None else manual_review_needed, reason=reason)


def _unsupported(structure: MarketStructure, resolution: ResolutionMetadata, *, latency_tier: str, polling_focus: str, reason: str) -> ResolutionSourceRoute:
    return _route(structure, resolution, latest_url=None, history_url=None, direct=False, supported=False, latency_tier=latency_tier, latency_priority="manual_review_required", polling_focus=polling_focus, manual_review_needed=True, reason=reason)


def _noaa_latest_url(station_code: str) -> str:
    return f"https://api.weather.gov/stations/{quote(station_code)}/observations/latest"


def _noaa_history_url(structure: MarketStructure, station_code: str, *, start_date: str | None, end_date: str | None) -> str | None:
    if not start_date or not end_date:
        return None
    if _uses_noaa_daily_summary(structure, start_date=start_date, end_date=end_date):
        query = urlencode({"dataset": "daily-summaries", "stations": station_code, "startDate": start_date, "endDate": end_date, "format": "json", "units": "standard", "includeAttributes": "false"})
        return f"https://www.ncei.noaa.gov/access/services/data/v1?{query}"
    query = urlencode({"start": f"{start_date}T00:00:00Z", "end": f"{end_date}T23:59:59Z"})
    return f"https://api.weather.gov/stations/{quote(station_code)}/observations?{query}"


def _uses_noaa_daily_summary(structure: MarketStructure, *, start_date: str | None, end_date: str | None) -> bool:
    return start_date is not None and start_date == end_date and structure.measurement_kind in {"high", "low"}


def _wunderground_history_url(source_url: str, *, start_date: str | None, end_date: str | None) -> str | None:
    if not start_date or not end_date or start_date != end_date:
        return None
    return f"{source_url.rstrip('/')}/date/{start_date}"


def _accuweather_history_url(source_url: str) -> str:
    separator = "&" if "?" in source_url else "?"
    return f"{source_url}{separator}details=true"


def _aviation_weather_url(station_code: str, *, start_date: str | None = None, end_date: str | None = None) -> str:
    query = {"ids": station_code, "format": "json", "taf": "false"}
    if start_date and end_date:
        query.update({"start": f"{start_date}T00:00:00Z", "end": f"{end_date}T23:59:59Z"})
    return f"https://aviationweather.gov/api/data/metar?{urlencode(query)}"


def _hko_latest_url(source_url: str | None) -> str:
    del source_url
    return "https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=rhrread&lang=en"


def _hko_daily_extract_url(structure: MarketStructure, *, start_date: str | None = None, end_date: str | None = None) -> str:
    if start_date and end_date and start_date == end_date:
        parsed_date = _parse_iso_date(start_date)
        if parsed_date is not None:
            data_type = "CLMMINT" if structure.measurement_kind == "low" else "CLMMAXT"
            query = urlencode({"dataType": data_type, "rformat": "json", "station": "HKO", "year": parsed_date.year, "month": parsed_date.month})
            return f"https://data.weather.gov.hk/weatherAPI/opendata/opendata.php?{query}"
    return "https://www.hko.gov.hk/en/wxinfo/dailywx/extract.htm"


def _meteostat_history_url(structure: MarketStructure, resolution: ResolutionMetadata, *, start_date: str | None = None, end_date: str | None = None) -> str | None:
    if not start_date or not end_date:
        return None
    location_key = "station" if resolution.station_code else "city"
    location_value = resolution.station_code or structure.city
    query = urlencode({location_key: location_value, "start": start_date, "end": end_date})
    return f"meteostat://daily?{query}"


def _environment_canada_history_url(source_url: str, *, start_date: str | None, end_date: str | None) -> str | None:
    if not start_date or not end_date:
        return source_url
    parsed = _parse_iso_date(start_date)
    if parsed is None:
        return source_url
    split = urlsplit(source_url)
    query = dict(parse_qsl(split.query, keep_blank_values=True))
    query.update({"timeframe": "2", "StartYear": "1840", "EndYear": str(parsed.year), "Year": str(parsed.year), "Month": str(parsed.month), "Day": str(parsed.day)})
    return urlunsplit((split.scheme, split.netloc, split.path, urlencode(query), split.fragment))


def _parse_iso_date(raw_value: str) -> datetime | None:
    try:
        return datetime.strptime(raw_value, "%Y-%m-%d")
    except ValueError:
        return None
