from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from weather_pm.models import MarketStructure, ResolutionMetadata
from weather_pm.source_routing import ResolutionSourceRoute, build_resolution_source_route


@dataclass(slots=True)
class StationEndpointCandidate:
    provider: str
    station_code: str | None
    station_name: str | None
    url: str
    endpoint_kind: str
    latency_tier: str
    latency_priority: str
    polling_focus: str
    direct: bool
    official: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class StationBinding:
    provider: str
    station_code: str | None
    station_name: str | None
    station_type: str
    source_url: str | None
    exact_station_match: bool
    manual_review_needed: bool
    latest_candidates: list[StationEndpointCandidate]
    final_candidates: list[StationEndpointCandidate]
    fallback_candidates: list[StationEndpointCandidate]
    best_polling_focus: str
    route: ResolutionSourceRoute

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["route"] = self.route.to_dict()
        return payload


def build_station_binding(
    structure: MarketStructure,
    resolution: ResolutionMetadata,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> StationBinding:
    """Materialize the exact station/source endpoints implied by resolution rules."""
    route = build_resolution_source_route(structure, resolution, start_date=start_date, end_date=end_date)
    latest_candidates: list[StationEndpointCandidate] = []
    final_candidates: list[StationEndpointCandidate] = []
    fallback_candidates: list[StationEndpointCandidate] = []

    if route.latest_url:
        latest_candidates.append(_candidate(route, url=route.latest_url, endpoint_kind="latest"))
    if route.history_url:
        final_candidates.append(_candidate(route, url=route.history_url, endpoint_kind="final"))
    elif route.provider == "noaa" and route.station_code:
        # Without dates we still know the official final path family: NCEI daily summaries.
        # A dated caller will materialize the exact query string.
        final_candidates.append(
            _candidate(
                route,
                url=f"https://www.ncei.noaa.gov/access/services/data/v1?dataset=daily-summaries&stations={route.station_code}",
                endpoint_kind="final",
            )
        )

    if not route.direct and route.history_url:
        fallback_candidates.append(_candidate(route, url=route.history_url, endpoint_kind="fallback_history"))
        final_candidates = []

    exact_station_match = bool(route.station_code and route.direct and route.supported)
    return StationBinding(
        provider=route.provider,
        station_code=route.station_code,
        station_name=route.station_name,
        station_type=resolution.station_type,
        source_url=route.source_url,
        exact_station_match=exact_station_match,
        manual_review_needed=route.manual_review_needed,
        latest_candidates=latest_candidates,
        final_candidates=final_candidates,
        fallback_candidates=fallback_candidates,
        best_polling_focus=latest_candidates[0].polling_focus if latest_candidates else route.polling_focus,
        route=route,
    )


def _candidate(route: ResolutionSourceRoute, *, url: str, endpoint_kind: str) -> StationEndpointCandidate:
    return StationEndpointCandidate(
        provider=route.provider,
        station_code=route.station_code,
        station_name=route.station_name,
        url=url,
        endpoint_kind=endpoint_kind,
        latency_tier=route.latency_tier,
        latency_priority=route.latency_priority,
        polling_focus=_candidate_polling_focus(route, endpoint_kind=endpoint_kind),
        direct=route.direct,
        official=_is_official_route(route),
    )


def _candidate_polling_focus(route: ResolutionSourceRoute, *, endpoint_kind: str) -> str:
    if route.provider == "noaa" and endpoint_kind == "latest":
        return "station_observations_latest"
    if route.provider == "noaa" and endpoint_kind == "final":
        return "noaa_official_daily_summary"
    return route.polling_focus


def _is_official_route(route: ResolutionSourceRoute) -> bool:
    if route.latency_priority in {"direct_source_low_latency", "direct_source_official_open_data"}:
        return True
    return route.provider in {"noaa", "aviation_weather", "hong_kong_observatory", "environment_canada"}
