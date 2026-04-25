from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any
from urllib.parse import quote, urlencode

from weather_pm.models import MarketStructure, ResolutionMetadata


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
    """Describe the lowest-latency source path implied by a market's resolution rules.

    This is intentionally a routing/diagnostic layer: it does not fetch data.  Callers can
    use it to know exactly which station/source to poll, and avoid city geocoding or
    aggregator fallbacks whenever the resolution metadata exposes a direct source.
    """
    if resolution.provider == "noaa" and resolution.station_code:
        latest_url = _noaa_latest_url(resolution.station_code)
        history_url = _noaa_history_url(structure, resolution.station_code, start_date=start_date, end_date=end_date)
        daily_summary = _uses_noaa_daily_summary(structure, start_date=start_date, end_date=end_date)
        return ResolutionSourceRoute(
            provider=resolution.provider,
            station_code=resolution.station_code,
            station_name=resolution.station_name,
            source_url=resolution.source_url,
            latest_url=latest_url,
            history_url=history_url,
            direct=True,
            supported=True,
            latency_tier="direct_history" if daily_summary else "direct_latest",
            latency_priority="direct_source_low_latency",
            polling_focus="noaa_official_daily_summary" if daily_summary else "station_observations_latest",
            manual_review_needed=resolution.manual_review_needed,
            reason=(
                "NOAA station code found in resolution rules; poll NOAA/NCEI daily summaries for official daily high/low."
                if daily_summary
                else "NOAA station code found in resolution rules; poll weather.gov station observations directly."
            ),
        )

    if resolution.provider == "wunderground" and resolution.source_url and resolution.station_code:
        history_url = _wunderground_history_url(resolution.source_url, start_date=start_date, end_date=end_date)
        return ResolutionSourceRoute(
            provider=resolution.provider,
            station_code=resolution.station_code,
            station_name=resolution.station_name,
            source_url=resolution.source_url,
            latest_url=resolution.source_url,
            history_url=history_url,
            direct=True,
            supported=True,
            latency_tier="direct_latest",
            latency_priority="direct_source_low_latency",
            polling_focus="station_history_page",
            manual_review_needed=resolution.manual_review_needed,
            reason="Wunderground station page found in resolution rules; poll the station page directly without city geocoding.",
        )

    if resolution.provider == "accuweather" and resolution.source_url:
        return ResolutionSourceRoute(
            provider=resolution.provider,
            station_code=resolution.station_code,
            station_name=resolution.station_name,
            source_url=resolution.source_url,
            latest_url=resolution.source_url,
            history_url=_accuweather_history_url(resolution.source_url),
            direct=True,
            supported=True,
            latency_tier="direct_latest",
            latency_priority="direct_source_low_latency",
            polling_focus="accuweather_location_page_or_injected_json",
            manual_review_needed=resolution.manual_review_needed,
            reason="AccuWeather source URL found in resolution rules; route directly to the auditable page and parse injected JSON payloads. Live AccuWeather API use requires an API key supplied outside tests.",
        )

    if resolution.provider == "aviation_weather" and resolution.station_code:
        return ResolutionSourceRoute(
            provider=resolution.provider,
            station_code=resolution.station_code,
            station_name=resolution.station_name,
            source_url=resolution.source_url,
            latest_url=_aviation_weather_url(resolution.station_code),
            history_url=_aviation_weather_url(resolution.station_code, start_date=start_date, end_date=end_date),
            direct=True,
            supported=True,
            latency_tier="direct_latest",
            latency_priority="direct_source_low_latency",
            polling_focus="aviation_weather_metar_observations",
            manual_review_needed=resolution.manual_review_needed,
            reason="AviationWeather METAR station code found in resolution rules; poll station observations directly.",
        )

    if resolution.provider == "hong_kong_observatory":
        latest_url = _hko_latest_url(resolution.source_url)
        history_url = _hko_daily_extract_url(structure, start_date=start_date, end_date=end_date)
        return ResolutionSourceRoute(
            provider=resolution.provider,
            station_code=resolution.station_code or "HKO",
            station_name=resolution.station_name or "Hong Kong Observatory",
            source_url=resolution.source_url,
            latest_url=latest_url,
            history_url=history_url,
            direct=True,
            supported=True,
            latency_tier="direct_latest",
            latency_priority="direct_source_low_latency",
            polling_focus="hko_current_weather_and_daily_extract",
            manual_review_needed=resolution.manual_review_needed,
            reason="Hong Kong Observatory source found in resolution rules; poll HKO current weather and official monthly daily extract directly.",
        )

    if resolution.provider == "meteostat" and (resolution.station_code or structure.city):
        history_url = _meteostat_history_url(structure, resolution, start_date=start_date, end_date=end_date)
        has_station = resolution.station_code is not None
        return ResolutionSourceRoute(
            provider=resolution.provider,
            station_code=resolution.station_code,
            station_name=resolution.station_name,
            source_url=resolution.source_url,
            latest_url=None,
            history_url=history_url,
            direct=False,
            supported=True,
            latency_tier="fallback_history",
            latency_priority="fallback_daily_history" if has_station else "fallback_city_daily_history",
            polling_focus="meteostat_daily_history" if has_station else "meteostat_city_daily_history",
            manual_review_needed=resolution.manual_review_needed,
            reason="Meteostat historical daily data is available as a fallback; use injected daily tmax/tmin payloads rather than direct official station polling.",
        )

    return ResolutionSourceRoute(
        provider=resolution.provider,
        station_code=resolution.station_code,
        station_name=resolution.station_name,
        source_url=resolution.source_url,
        latest_url=None,
        history_url=None,
        direct=False,
        supported=False,
        latency_tier="unsupported",
        latency_priority="manual_review_required",
        polling_focus="manual_review",
        manual_review_needed=True,
        reason=f"No direct route for provider={resolution.provider!r} station={resolution.station_code!r}; manual source review required.",
    )


def _noaa_latest_url(station_code: str) -> str:
    return f"https://api.weather.gov/stations/{quote(station_code)}/observations/latest"


def _noaa_history_url(
    structure: MarketStructure,
    station_code: str,
    *,
    start_date: str | None,
    end_date: str | None,
) -> str | None:
    if not start_date or not end_date:
        return None
    if _uses_noaa_daily_summary(structure, start_date=start_date, end_date=end_date):
        query = urlencode(
            {
                "dataset": "daily-summaries",
                "stations": station_code,
                "startDate": start_date,
                "endDate": end_date,
                "format": "json",
                "units": "standard",
                "includeAttributes": "false",
            }
        )
        return f"https://www.ncei.noaa.gov/access/services/data/v1?{query}"
    query = urlencode({"start": f"{start_date}T00:00:00Z", "end": f"{end_date}T23:59:59Z"})
    return f"https://api.weather.gov/stations/{quote(station_code)}/observations?{query}"


def _uses_noaa_daily_summary(structure: MarketStructure, *, start_date: str | None, end_date: str | None) -> bool:
    return start_date is not None and start_date == end_date and structure.measurement_kind in {"high", "low"}


def _wunderground_history_url(source_url: str, *, start_date: str | None, end_date: str | None) -> str | None:
    if not start_date or not end_date:
        return None
    if start_date != end_date:
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


def _hko_daily_extract_url(
    structure: MarketStructure,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> str:
    if start_date and end_date and start_date == end_date:
        parsed_date = _parse_iso_date(start_date)
        if parsed_date is not None:
            data_type = "CLMMINT" if structure.measurement_kind == "low" else "CLMMAXT"
            query = urlencode(
                {
                    "dataType": data_type,
                    "rformat": "json",
                    "station": "HKO",
                    "year": parsed_date.year,
                    "month": parsed_date.month,
                }
            )
            return f"https://data.weather.gov.hk/weatherAPI/opendata/opendata.php?{query}"
    return "https://www.hko.gov.hk/en/wxinfo/dailywx/extract.htm"


def _meteostat_history_url(
    structure: MarketStructure,
    resolution: ResolutionMetadata,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> str | None:
    if not start_date or not end_date:
        return None
    location_key = "station" if resolution.station_code else "city"
    location_value = resolution.station_code or structure.city
    query = urlencode({location_key: location_value, "start": start_date, "end": end_date})
    return f"meteostat://daily?{query}"


def _parse_iso_date(raw_value: str) -> datetime | None:
    try:
        return datetime.strptime(raw_value, "%Y-%m-%d")
    except ValueError:
        return None
