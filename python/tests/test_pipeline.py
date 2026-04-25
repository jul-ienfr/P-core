from __future__ import annotations

from weather_pm.market_parser import parse_market_question
from weather_pm.models import ForecastBundle
from weather_pm.pipeline import _default_forecast, _default_model, score_market_from_fixture_market_id, score_market_from_question


def test_score_market_from_fixture_market_id_returns_full_payload() -> None:
    payload = score_market_from_fixture_market_id("denver-high-64")

    assert payload["market"]["city"] == "Denver"
    assert payload["score"]["grade"] in {"A", "B", "C", "D"}
    assert payload["decision"]["status"] in {"trade", "trade_small", "watchlist", "skip"}
    assert payload["neighbors"]["neighbor_market_count"] >= 2
    assert payload["execution"]["spread"] == 0.03


def test_default_model_distinguishes_below_threshold_direction_semantics() -> None:
    structure = parse_market_question("Will the lowest temperature in Miami be 63°F or below on April 23?")
    forecast = _default_forecast(structure)

    model = _default_model(structure, forecast)

    assert forecast.consensus_value == 62.8
    assert model.probability_yes > 0.54


def test_score_market_from_question_can_use_live_direct_station_observation_for_model_source() -> None:
    class _FakeDirectStationClient:
        def build_forecast_bundle(self, structure, resolution):
            assert resolution.provider == "noaa"
            assert resolution.station_code == "KDEN"
            return ForecastBundle(
                source_count=1,
                consensus_value=68.0,
                dispersion=1.0,
                historical_station_available=True,
                source_provider="noaa",
                source_station_code="KDEN",
                source_url="https://api.weather.gov/stations/KDEN/observations/latest",
                source_latency_tier="direct_latest",
            )

    payload = score_market_from_question(
        "Will the highest temperature in Denver be 64F or higher?",
        0.43,
        resolution_source="Resolution source: NOAA daily climate report for station KDEN",
        description="Official observed high temperature at Denver International Airport station KDEN.",
        rules="Source: https://www.weather.gov/wrh/climate?wfo=bou station KDEN.",
        live=True,
        direct_client=_FakeDirectStationClient(),
    )

    assert payload["forecast"]["consensus_value"] == 68.0
    assert payload["model"]["source_provider"] == "noaa"
    assert payload["model"]["source_station_code"] == "KDEN"
    assert payload["model"]["source_url"] == "https://api.weather.gov/stations/KDEN/observations/latest"
    assert payload["model"]["source_latency_tier"] == "direct_latest"
    assert payload["source_route"]["latency_priority"] == "direct_source_low_latency"
    assert payload["source_route"]["latest_url"] == "https://api.weather.gov/stations/KDEN/observations/latest"


def test_score_market_from_question_does_not_invent_resolution_source_when_absent() -> None:
    payload = score_market_from_question(
        "Will the highest temperature in Denver be 64F or higher?",
        0.43,
    )

    assert payload["resolution"]["provider"] == "unknown"
    assert payload["resolution"]["station_code"] is None
    assert payload["resolution"]["source_url"] is None
    assert payload["resolution"]["manual_review_needed"] is True
    assert payload["source_route"]["direct"] is False
    assert payload["source_route"]["latency_tier"] == "unsupported"
    assert payload["source_route"]["latency_priority"] == "manual_review_required"
