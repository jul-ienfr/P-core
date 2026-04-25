from __future__ import annotations

from dataclasses import asdict, dataclass
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
    del structure  # reserved for provider-specific routing decisions that need market kind/unit/date.

    if resolution.provider == "noaa" and resolution.station_code:
        latest_url = _noaa_latest_url(resolution.station_code)
        history_url = _noaa_history_url(resolution.station_code, start_date=start_date, end_date=end_date)
        return ResolutionSourceRoute(
            provider=resolution.provider,
            station_code=resolution.station_code,
            station_name=resolution.station_name,
            source_url=resolution.source_url,
            latest_url=latest_url,
            history_url=history_url,
            direct=True,
            supported=True,
            latency_tier="direct_latest",
            polling_focus="station_observations_latest",
            manual_review_needed=resolution.manual_review_needed,
            reason="NOAA station code found in resolution rules; poll weather.gov station observations directly.",
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
            polling_focus="station_history_page",
            manual_review_needed=resolution.manual_review_needed,
            reason="Wunderground station page found in resolution rules; poll the station page directly without city geocoding.",
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
        polling_focus="manual_review",
        manual_review_needed=True,
        reason=f"No direct route for provider={resolution.provider!r} station={resolution.station_code!r}; manual source review required.",
    )


def _noaa_latest_url(station_code: str) -> str:
    return f"https://api.weather.gov/stations/{quote(station_code)}/observations/latest"


def _noaa_history_url(station_code: str, *, start_date: str | None, end_date: str | None) -> str | None:
    if not start_date or not end_date:
        return None
    query = urlencode({"start": f"{start_date}T00:00:00Z", "end": f"{end_date}T23:59:59Z"})
    return f"https://api.weather.gov/stations/{quote(station_code)}/observations?{query}"


def _wunderground_history_url(source_url: str, *, start_date: str | None, end_date: str | None) -> str | None:
    if not start_date or not end_date:
        return None
    if start_date != end_date:
        return None
    return f"{source_url.rstrip('/')}/date/{start_date}"
