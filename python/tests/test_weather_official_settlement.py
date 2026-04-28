from __future__ import annotations

from weather_pm.market_parser import parse_market_question
from weather_pm.models import MarketStructure, StationHistoryBundle, StationHistoryPoint
from weather_pm.official_settlement import (
    OfficialWeatherObservation,
    classify_official_outcome,
    parse_hko_monthly_extract,
    parse_noaa_daily_summary,
    parse_station_history_bundle,
    parse_wunderground_observations,
    resolve_official_weather_settlement,
    settlement_validation_status,
)


def test_parse_noaa_daily_summary_extracts_official_high_and_classifies_threshold() -> None:
    structure = parse_market_question("Will the highest temperature in Denver be 64F or higher on April 25?")
    payload = [
        {"DATE": "2026-04-24", "STATION": "KDEN", "TMAX": "61", "TMIN": "36"},
        {"DATE": "2026-04-25", "STATION": "KDEN", "TMAX": "65", "TMIN": "34"},
    ]

    observation = parse_noaa_daily_summary(payload, structure, target_date="2026-04-25", station_code="KDEN")
    result = classify_official_outcome(observation, structure)

    assert observation == OfficialWeatherObservation(
        provider="noaa",
        station_code="KDEN",
        observed_date="2026-04-25",
        measurement_kind="high",
        value=65.0,
        unit="f",
        source="noaa_daily_summary",
    )
    assert result.resolved is True
    assert result.outcome_yes is True
    assert result.observed_value == 65.0
    assert result.reason == "official_observation_classified"


def test_parse_noaa_daily_summary_extracts_low_with_unit_conversion() -> None:
    structure = parse_market_question("Will the lowest temperature in Hong Kong be 20°C or below on April 25?")
    payload = [{"DATE": "2026-04-25", "STATION": "VHHH", "TMAX": "82", "TMIN": "67"}]

    observation = parse_noaa_daily_summary(
        payload,
        structure,
        target_date="2026-04-25",
        station_code="VHHH",
        payload_unit="f",
    )
    result = classify_official_outcome(observation, structure)

    assert observation.value == 19.44
    assert observation.unit == "c"
    assert observation.measurement_kind == "low"
    assert result.outcome_yes is True


def test_parse_wunderground_observations_selects_daily_high_from_observation_series() -> None:
    structure = parse_market_question("Will the highest temperature in Miami be between 82F and 84F on April 25?")
    payload = {
        "observations": [
            {"obsTimeLocal": "2026-04-25 01:00:00", "stationID": "KMIA", "imperial": {"temp": 79}},
            {"obsTimeLocal": "2026-04-25 15:00:00", "stationID": "KMIA", "imperial": {"temp": 83.6}},
            {"obsTimeLocal": "2026-04-25 23:00:00", "stationID": "KMIA", "imperial": {"temp": 81}},
            {"obsTimeLocal": "2026-04-26 00:05:00", "stationID": "KMIA", "imperial": {"temp": 86}},
        ]
    }

    observation = parse_wunderground_observations(payload, structure, target_date="2026-04-25", station_code="KMIA")
    result = classify_official_outcome(observation, structure)

    assert observation.provider == "wunderground"
    assert observation.station_code == "KMIA"
    assert observation.observed_date == "2026-04-25"
    assert observation.value == 83.6
    assert result.outcome_yes is True


def test_parse_hko_monthly_extract_extracts_daily_low_for_requested_day() -> None:
    structure = parse_market_question("Will the lowest temperature in Hong Kong be 20°C or below on April 25?")
    payload = {
        "data": [
            {"day": "24", "min": "21.7"},
            {"day": "25", "min": "19.8"},
            {"day": "26", "min": "22.1"},
        ]
    }

    observation = parse_hko_monthly_extract(payload, structure, target_date="2026-04-25")
    result = classify_official_outcome(observation, structure)

    assert observation.provider == "hong_kong_observatory"
    assert observation.station_code == "HKO"
    assert observation.value == 19.8
    assert observation.unit == "c"
    assert result.outcome_yes is True


def test_parse_station_history_bundle_selects_high_low_and_classifies_exact_bin() -> None:
    structure = parse_market_question("Will the highest temperature in Denver be exactly 65F on April 25?")
    bundle = StationHistoryBundle(
        source_provider="iem_asos",
        station_code="KDEN",
        source_url="https://example.invalid/history",
        latency_tier="direct_history",
        points=[
            StationHistoryPoint(timestamp="2026-04-25T00:00:00Z", value=58.0, unit="f"),
            StationHistoryPoint(timestamp="2026-04-25T21:00:00Z", value=65.4, unit="f"),
            StationHistoryPoint(timestamp="2026-04-25T23:00:00Z", value=63.0, unit="f"),
        ],
        summary={"min": 58.0, "max": 65.4},
    )

    observation = parse_station_history_bundle(bundle, structure, target_date="2026-04-25")
    result = classify_official_outcome(observation, structure)

    assert observation.value == 65.4
    assert result.outcome_yes is True
    assert result.outcome_label == "YES"


def test_resolver_accepts_already_fetched_payloads_without_network_client() -> None:
    structure = parse_market_question("Will the highest temperature in Denver be 64F or higher on April 25?")
    payload = [{"DATE": "2026-04-25", "STATION": "KDEN", "TMAX": "63.9"}]

    result = resolve_official_weather_settlement(
        provider="noaa",
        structure=structure,
        payload=payload,
        target_date="2026-04-25",
        station_code="KDEN",
    )

    assert result.provider == "noaa"
    assert result.resolved is True
    assert result.outcome_yes is False
    assert result.observed_value == 63.9


def test_resolver_uses_injectable_client_only_when_payload_missing() -> None:
    structure = parse_market_question("Will the highest temperature in Denver be 64F or higher on April 25?")

    class StubClient:
        def fetch_official_payload(self, *, provider: str, structure: MarketStructure, target_date: str, station_code: str | None):
            assert provider == "noaa"
            assert structure.city == "Denver"
            assert target_date == "2026-04-25"
            assert station_code == "KDEN"
            return [{"DATE": "2026-04-25", "STATION": "KDEN", "TMAX": "66"}]

    result = resolve_official_weather_settlement(
        provider="noaa",
        structure=structure,
        payload=None,
        target_date="2026-04-25",
        station_code="KDEN",
        client=StubClient(),
    )

    assert result.resolved is True
    assert result.outcome_yes is True
    assert result.observed_value == 66.0


def test_unsupported_provider_and_missing_data_return_unresolved_results() -> None:
    structure = parse_market_question("Will the highest temperature in Denver be 64F or higher on April 25?")

    unsupported = resolve_official_weather_settlement(
        provider="unknown_weather_source",
        structure=structure,
        payload={"rows": []},
        target_date="2026-04-25",
    )
    missing = resolve_official_weather_settlement(
        provider="noaa",
        structure=structure,
        payload=[{"DATE": "2026-04-25", "TMIN": "35"}],
        target_date="2026-04-25",
        station_code="KDEN",
    )

    assert unsupported.resolved is False
    assert unsupported.outcome_yes is None
    assert "unsupported provider" in unsupported.reason
    assert missing.resolved is False
    assert missing.outcome_yes is None
    assert "missing official observation" in missing.reason


def test_settlement_validation_status_reports_official_slice_progression() -> None:
    structure = parse_market_question("Will the highest temperature in Denver be 64F or higher on April 25?")
    observation = parse_noaa_daily_summary(
        [{"DATE": "2026-04-25", "STATION": "KDEN", "TMAX": "65"}],
        structure,
        target_date="2026-04-25",
        station_code="KDEN",
    )

    unresolved = settlement_validation_status()
    observed_structure = MarketStructure(
        city="Denver",
        measurement_kind="high",
        unit="f",
        is_threshold=False,
        is_exact_bin=False,
        target_value=None,
        range_low=None,
        range_high=None,
    )
    observed = settlement_validation_status(official_result=classify_official_outcome(observation, observed_structure))
    classified = settlement_validation_status(official_result=classify_official_outcome(observation, structure))

    assert unresolved["settlement_validation_status"] == "unresolved"
    assert observed["settlement_validation_status"] == "official_observation_found"
    assert classified["settlement_validation_status"] == "outcome_classified"
    assert classified["official_outcome"] == "Yes"
