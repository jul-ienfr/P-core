from __future__ import annotations

from weather_pm.models import (
    DecisionResult,
    ExecutionFeatures,
    ForecastBundle,
    MarketStructure,
    ModelOutput,
    NeighborContext,
    ResolutionMetadata,
)
from weather_pm.scoring import score_market


def test_score_market_returns_trade_grade_for_clean_threshold_setup() -> None:
    structure = MarketStructure(
        city="Denver",
        measurement_kind="high",
        unit="f",
        is_threshold=True,
        is_exact_bin=False,
        target_value=64.0,
        range_low=None,
        range_high=None,
        date_local=None,
    )
    resolution = ResolutionMetadata(
        provider="wunderground",
        source_url="https://example.com",
        station_code="KDEN",
        station_name="Denver Intl",
        station_type="airport",
        wording_clear=True,
        rules_clear=True,
        manual_review_needed=False,
        revision_risk="low",
    )
    forecast = ForecastBundle(
        source_count=3,
        consensus_value=64.2,
        dispersion=1.2,
        historical_station_available=True,
    )
    model = ModelOutput(probability_yes=0.64, confidence=0.75, method="heuristic")
    neighbors = NeighborContext(
        neighbor_market_count=4,
        neighbor_inconsistency=0.58,
        threshold_bin_inconsistency=0.40,
    )
    execution = ExecutionFeatures(
        spread=0.03,
        hours_to_resolution=18.0,
        volume_usd=14000.0,
        fillable_size_usd=250.0,
        execution_speed_required="low",
        slippage_risk="low",
    )

    result = score_market(
        structure=structure,
        resolution=resolution,
        forecast_bundle=forecast,
        model_output=model,
        neighbor_context=neighbors,
        execution=execution,
        yes_price=0.43,
    )

    assert result.raw_edge == 0.21
    assert result.grade == "A"
    assert result.total_score >= 80.0


def test_score_market_reduces_edge_component_when_execution_costs_eat_edge() -> None:
    structure = MarketStructure(
        city="Denver",
        measurement_kind="high",
        unit="f",
        is_threshold=True,
        is_exact_bin=False,
        target_value=64.0,
        range_low=None,
        range_high=None,
        date_local=None,
    )
    resolution = ResolutionMetadata(
        provider="wunderground",
        source_url="https://example.com",
        station_code="KDEN",
        station_name="Denver Intl",
        station_type="airport",
        wording_clear=True,
        rules_clear=True,
        manual_review_needed=False,
        revision_risk="low",
    )
    forecast = ForecastBundle(
        source_count=3,
        consensus_value=64.2,
        dispersion=1.2,
        historical_station_available=True,
    )
    model = ModelOutput(probability_yes=0.64, confidence=0.75, method="heuristic")
    neighbors = NeighborContext(
        neighbor_market_count=4,
        neighbor_inconsistency=0.58,
        threshold_bin_inconsistency=0.40,
    )
    execution = ExecutionFeatures(
        spread=0.03,
        hours_to_resolution=18.0,
        volume_usd=14000.0,
        fillable_size_usd=250.0,
        execution_speed_required="low",
        slippage_risk="medium",
        all_in_cost_bps=1950.0,
        all_in_cost_usd=48.75,
    )

    result = score_market(
        structure=structure,
        resolution=resolution,
        forecast_bundle=forecast,
        model_output=model,
        neighbor_context=neighbors,
        execution=execution,
        yes_price=0.43,
    )

    assert result.raw_edge == 0.21
    assert result.edge_net_execution == 0.015
    assert result.edge_theoretical < 0.10
    assert result.grade != "A"


def test_score_market_caps_manual_review_markets_below_trade_zone() -> None:
    structure = MarketStructure(
        city="Tokyo",
        measurement_kind="high",
        unit="c",
        is_threshold=True,
        is_exact_bin=False,
        target_value=16.0,
        range_low=None,
        range_high=None,
        date_local=None,
    )
    resolution = ResolutionMetadata(
        provider="unknown",
        source_url=None,
        station_code=None,
        station_name=None,
        station_type="unknown",
        wording_clear=False,
        rules_clear=False,
        manual_review_needed=True,
        revision_risk="high",
    )
    forecast = ForecastBundle(
        source_count=3,
        consensus_value=17.0,
        dispersion=1.0,
        historical_station_available=True,
    )
    model = ModelOutput(probability_yes=0.72, confidence=0.70, method="heuristic")
    neighbors = NeighborContext(
        neighbor_market_count=3,
        neighbor_inconsistency=0.52,
        threshold_bin_inconsistency=0.55,
    )
    execution = ExecutionFeatures(
        spread=0.02,
        hours_to_resolution=20.0,
        volume_usd=9000.0,
        fillable_size_usd=150.0,
        execution_speed_required="low",
        slippage_risk="low",
    )

    result = score_market(
        structure=structure,
        resolution=resolution,
        forecast_bundle=forecast,
        model_output=model,
        neighbor_context=neighbors,
        execution=execution,
        yes_price=0.40,
    )

    assert result.total_score <= 59.0
    assert result.grade in {"C", "D"}
