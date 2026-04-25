from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from time import perf_counter
from typing import Any

from email.utils import parsedate_to_datetime

from weather_pm.history_client import StationHistoryClient
from weather_pm.models import MarketStructure
from weather_pm.station_binding import StationBinding


@dataclass(slots=True)
class StationEndpointProbeResult:
    provider: str
    station_code: str | None
    url: str
    ok: bool
    direct: bool
    latency_tier: str
    latency_priority: str
    polling_focus: str
    http_latency_ms: int
    observation_timestamp: str | None
    observation_value: float | None
    unit: str | None
    source_lag_seconds: int | None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class StationEndpointProbe:
    def __init__(self, *, now: datetime | None = None, client: Any | None = None) -> None:
        self.now = _as_utc(now or datetime.now(timezone.utc))
        self.client = client or StationHistoryClient(now_utc=self.now)

    def probe_latest(self, structure: MarketStructure, binding: StationBinding) -> StationEndpointProbeResult:
        started = perf_counter()
        try:
            bundle = self.client.fetch_latest_bundle(structure, binding.route_to_resolution()) if hasattr(binding, "route_to_resolution") else self.client.fetch_latest_bundle(structure, _resolution_from_binding(binding))
            elapsed_ms = int((perf_counter() - started) * 1000)
            point = bundle.latest()
            source_lag = getattr(bundle, "source_lag_seconds", None)
            if source_lag is None and point is not None:
                source_lag = _source_lag_seconds(point.timestamp, now=self.now)
            return StationEndpointProbeResult(
                provider=bundle.source_provider,
                station_code=bundle.station_code,
                url=bundle.source_url or (binding.latest_candidates[0].url if binding.latest_candidates else ""),
                ok=point is not None,
                direct=binding.route.direct,
                latency_tier=bundle.latency_tier,
                latency_priority=binding.route.latency_priority,
                polling_focus=bundle.polling_focus or binding.best_polling_focus,
                http_latency_ms=max(0, elapsed_ms),
                observation_timestamp=point.timestamp if point else None,
                observation_value=point.value if point else None,
                unit=point.unit if point else None,
                source_lag_seconds=source_lag,
            )
        except Exception as exc:  # pragma: no cover - exercised by future live probes
            elapsed_ms = int((perf_counter() - started) * 1000)
            return StationEndpointProbeResult(
                provider=binding.provider,
                station_code=binding.station_code,
                url=binding.latest_candidates[0].url if binding.latest_candidates else binding.source_url or "",
                ok=False,
                direct=binding.route.direct,
                latency_tier=binding.route.latency_tier,
                latency_priority=binding.route.latency_priority,
                polling_focus=binding.best_polling_focus,
                http_latency_ms=max(0, elapsed_ms),
                observation_timestamp=None,
                observation_value=None,
                unit=None,
                source_lag_seconds=None,
                error=str(exc),
            )


def probe_station_endpoints(
    structure: MarketStructure,
    binding: StationBinding,
    *,
    client: Any | None = None,
    now: datetime | None = None,
) -> list[StationEndpointProbeResult]:
    if not binding.latest_candidates:
        return []
    return [StationEndpointProbe(now=now, client=client).probe_latest(structure, binding)]


def _source_lag_seconds(timestamp: str, *, now: datetime) -> int | None:
    observed_at = _parse_observation_timestamp(timestamp)
    if observed_at is None:
        return None
    return max(0, int((_as_utc(now) - observed_at).total_seconds()))


def _parse_observation_timestamp(raw_timestamp: str) -> datetime | None:
    text = str(raw_timestamp).strip()
    if not text:
        return None
    candidates = [text]
    if text.endswith("Z"):
        candidates.append(f"{text[:-1]}+00:00")
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        candidates.append(f"{text}T00:00:00+00:00")
    for candidate in candidates:
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _resolution_from_binding(binding: StationBinding):
    from weather_pm.models import ResolutionMetadata

    return ResolutionMetadata(
        provider=binding.provider,
        source_url=binding.source_url,
        station_code=binding.station_code,
        station_name=binding.station_name,
        station_type=binding.station_type,
        wording_clear=not binding.manual_review_needed,
        rules_clear=not binding.manual_review_needed,
        manual_review_needed=binding.manual_review_needed,
        revision_risk="unknown",
    )
