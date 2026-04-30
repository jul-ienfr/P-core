from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from weather_pm.market_parser import parse_market_question
from weather_pm.models import ResolutionMetadata, StationHistoryBundle, StationHistoryPoint
from weather_pm.station_binding import build_station_binding
from weather_pm.station_probe import StationEndpointProbe, probe_station_endpoints
from weather_pm.source_selection import select_best_station_sources


class FakeLatestClient:
    def __init__(self) -> None:
        self.called_providers: list[str] = []

    def fetch_latest_bundle(self, structure, resolution):
        self.called_providers.append(resolution.provider)
        if resolution.provider == "noaa":
            return StationHistoryBundle(
                source_provider="noaa",
                station_code="KDEN",
                source_url="https://api.weather.gov/stations/KDEN/observations/latest",
                latency_tier="direct_latest",
                points=[StationHistoryPoint(timestamp="2026-04-25T18:55:00+00:00", value=71.0, unit="f")],
                summary={"max": 71.0},
                polling_focus="station_observations_latest",
            )
        if resolution.provider == "aviation_weather":
            return StationHistoryBundle(
                source_provider="aviation_weather",
                station_code="KDEN",
                source_url="https://aviationweather.gov/api/data/metar?ids=KDEN&format=json&taf=false",
                latency_tier="direct_latest",
                points=[StationHistoryPoint(timestamp="2026-04-25T18:40:00+00:00", value=70.0, unit="f")],
                summary={"max": 70.0},
                polling_focus="aviation_weather_metar_observations",
            )
        raise AssertionError(f"unexpected provider {resolution.provider}")


def _resolution(provider: str, *, station_code: str | None = "KDEN", source_url: str | None = None) -> ResolutionMetadata:
    return ResolutionMetadata(
        provider=provider,
        source_url=source_url,
        station_code=station_code,
        station_name="Denver International Airport",
        station_type="airport_metar",
        wording_clear=True,
        rules_clear=True,
        manual_review_needed=False,
        revision_risk="low",
    )


def test_station_binding_materializes_exact_station_latest_and_final_endpoints() -> None:
    structure = parse_market_question("Will the highest temperature in Denver be 70F or higher on April 25?")
    resolution = _resolution("noaa")

    binding = build_station_binding(structure, resolution, start_date="2026-04-25", end_date="2026-04-25")

    assert binding.provider == "noaa"
    assert binding.station_code == "KDEN"
    assert binding.station_type == "airport_metar"
    assert binding.exact_station_match is True
    assert binding.latest_candidates[0].url == "https://api.weather.gov/stations/KDEN/observations/latest"
    assert "dataset=daily-summaries" in binding.final_candidates[0].url
    assert "stations=KDEN" in binding.final_candidates[0].url
    assert binding.best_polling_focus == "station_observations_latest"


def test_station_endpoint_probe_measures_source_lag_not_just_http_latency() -> None:
    structure = parse_market_question("Will the highest temperature in Denver be 70F or higher on April 25?")
    resolution = _resolution("noaa")
    binding = build_station_binding(structure, resolution)
    client = FakeLatestClient()

    result = probe_station_endpoints(
        structure,
        binding,
        client=client,
        now=datetime(2026, 4, 25, 19, 0, tzinfo=timezone.utc),
    )[0]

    assert result.provider == "noaa"
    assert result.station_code == "KDEN"
    assert result.ok is True
    assert result.http_latency_ms >= 0
    assert result.observation_timestamp == "2026-04-25T18:55:00+00:00"
    assert result.source_lag_seconds == 300
    assert result.polling_focus == "station_observations_latest"


def test_best_station_source_selector_prefers_fresh_exact_official_station_over_stale_metar() -> None:
    structure = parse_market_question("Will the highest temperature in Denver be 70F or higher on April 25?")
    noaa_binding = build_station_binding(structure, _resolution("noaa"))
    metar_binding = build_station_binding(structure, _resolution("aviation_weather"))
    client = FakeLatestClient()

    report = select_best_station_sources(
        structure,
        [noaa_binding, metar_binding],
        client=client,
        now=datetime(2026, 4, 25, 19, 0, tzinfo=timezone.utc),
    )

    assert report.best_latest.provider == "noaa"
    assert report.best_latest.station_code == "KDEN"
    assert report.best_latest.source_lag_seconds == 300
    assert report.best_latest.direct is True
    assert report.best_final.provider == "noaa"
    assert report.best_final.url.startswith("https://www.ncei.noaa.gov/access/services/data/v1?")
    assert report.fallback_latest[0].provider == "aviation_weather"
    assert report.discovery_metrics == {
        "bindings_total": 2,
        "latest_probes_total": 2,
        "latest_ok_total": 2,
        "final_candidates_total": 2,
        "fallback_final_total": 1,
        "manual_review_total": 0,
        "source_health": "healthy",
        "paper_only": True,
        "live_order_allowed": False,
    }
    assert report.operator_action == "poll_best_latest_station_until_threshold_then_confirm_with_official_final"


def test_best_station_source_selector_falls_back_to_dallas_meteostat_when_official_station_missing() -> None:
    structure = parse_market_question("Will the highest temperature in Dallas be 90F or higher on April 25?")
    resolution = _resolution("meteostat", station_code=None)
    resolution.station_name = None
    binding = build_station_binding(structure, resolution, start_date="2026-04-25", end_date="2026-04-25")

    report = select_best_station_sources(
        structure,
        [binding],
        client=FakeLatestClient(),
        now=datetime(2026, 4, 25, 19, 0, tzinfo=timezone.utc),
    )

    assert report.best_latest is None
    assert report.best_final is None
    assert report.fallback_final[0].provider == "meteostat"
    assert report.fallback_final[0].url == "meteostat://daily?city=Dallas&start=2026-04-25&end=2026-04-25"
    assert report.discovery_metrics["fallback_final_total"] == 1
    assert report.discovery_metrics["source_health"] == "fallback_only"
    assert report.discovery_metrics["paper_only"] is True
    assert report.discovery_metrics["live_order_allowed"] is False
    assert report.operator_action == "use_fallback_history_for_research_only_until_direct_official_source_found"


def test_probe_class_is_available_for_future_live_http_instrumentation() -> None:
    probe = StationEndpointProbe(now=datetime(2026, 4, 25, 19, 0, tzinfo=timezone.utc), client=FakeLatestClient())
    structure = parse_market_question("Will the highest temperature in Denver be 70F or higher on April 25?")
    binding = build_station_binding(structure, _resolution("noaa"))

    result = probe.probe_latest(structure, binding)

    assert result.source_lag_seconds == 300
