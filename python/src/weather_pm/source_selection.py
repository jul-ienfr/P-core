from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from weather_pm.models import MarketStructure
from weather_pm.station_binding import StationBinding, StationEndpointCandidate
from weather_pm.station_probe import StationEndpointProbeResult, probe_station_endpoints


@dataclass(slots=True)
class BestStationSourceReport:
    best_latest: StationEndpointProbeResult | None
    best_final: StationEndpointCandidate | None
    fallback_latest: list[StationEndpointProbeResult]
    fallback_final: list[StationEndpointCandidate]
    operator_action: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "best_latest": self.best_latest.to_dict() if self.best_latest else None,
            "best_final": self.best_final.to_dict() if self.best_final else None,
            "fallback_latest": [item.to_dict() for item in self.fallback_latest],
            "fallback_final": [item.to_dict() for item in self.fallback_final],
            "operator_action": self.operator_action,
        }


def select_best_station_sources(
    structure: MarketStructure,
    bindings: list[StationBinding],
    *,
    client: Any | None = None,
    now: datetime | None = None,
) -> BestStationSourceReport:
    """Pick the freshest exact station latest source and best official final confirmation path."""
    latest_results: list[StationEndpointProbeResult] = []
    final_candidates: list[StationEndpointCandidate] = []
    fallback_final: list[StationEndpointCandidate] = []

    for binding in bindings:
        latest_results.extend(probe_station_endpoints(structure, binding, client=client, now=now))
        final_candidates.extend(binding.final_candidates)
        fallback_final.extend(binding.fallback_candidates)

    ranked_latest = sorted(latest_results, key=_latest_rank_key)
    best_latest = ranked_latest[0] if ranked_latest else None
    fallback_latest = ranked_latest[1:] if len(ranked_latest) > 1 else []

    ranked_final = sorted(final_candidates, key=_final_rank_key)
    best_final = ranked_final[0] if ranked_final else None
    fallback_final = ranked_final[1:] + fallback_final if len(ranked_final) > 1 else fallback_final

    if best_latest and best_final:
        operator_action = "poll_best_latest_station_until_threshold_then_confirm_with_official_final"
    elif best_latest:
        operator_action = "poll_best_latest_station_manual_final_review"
    else:
        operator_action = "manual_station_source_review_required"

    return BestStationSourceReport(
        best_latest=best_latest,
        best_final=best_final,
        fallback_latest=fallback_latest,
        fallback_final=fallback_final,
        operator_action=operator_action,
    )


def _latest_rank_key(result: StationEndpointProbeResult) -> tuple[int, int, int, int]:
    ok_penalty = 0 if result.ok else 1
    direct_penalty = 0 if result.direct else 1
    lag = result.source_lag_seconds if result.source_lag_seconds is not None else 10**9
    return (ok_penalty, direct_penalty, lag, result.http_latency_ms)


def _final_rank_key(candidate: StationEndpointCandidate) -> tuple[int, int, int, int]:
    direct_penalty = 0 if candidate.direct else 1
    official_penalty = 0 if candidate.official else 1
    tier_penalty = 0 if candidate.latency_tier in {"direct_history", "direct_latest", "direct"} else 1
    finality_penalty = 0 if candidate.polling_focus in {"noaa_official_daily_summary", "hko_official_daily_extract"} else 1
    return (direct_penalty, official_penalty, tier_penalty, finality_penalty)
