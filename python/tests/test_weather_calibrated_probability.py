from __future__ import annotations

import math

from weather_pm.calibrated_probability import (
    CalibratedProbabilityInput,
    LeadTimeRmsePolicy,
    exact_bin_probability,
    gaussian_cdf,
    threshold_probability,
)
from weather_pm.calibration_dataset import GroupedRmsePolicy, LeadTimeBucket, RmseEstimate
from weather_pm.models import ForecastBundle, MarketStructure
from weather_pm.probability_model import build_model_output


def test_gaussian_cdf_threshold_probability_for_above_market() -> None:
    probability = threshold_probability(
        CalibratedProbabilityInput(
            forecast_value=66.0,
            target_value=64.0,
            threshold_direction="above",
            dispersion=2.0,
            market_yes_price=0.65,
        )
    )

    assert gaussian_cdf(0.0) == 0.5
    assert probability.probability_yes == 0.8413
    assert probability.z_score == 1.0
    assert probability.edge == 0.1913


def test_exact_bin_probability_uses_gaussian_mass_between_edges() -> None:
    probability = exact_bin_probability(
        CalibratedProbabilityInput(
            forecast_value=65.0,
            range_low=64.0,
            range_high=66.0,
            dispersion=2.0,
        )
    )

    expected = gaussian_cdf(0.5) - gaussian_cdf(-0.5)
    assert probability.probability_yes == round(expected, 4)
    assert probability.z_score == 0.0
    assert probability.edge is None


def test_lead_time_rmse_policy_widens_sigma_and_softens_threshold_probability() -> None:
    short = threshold_probability(
        CalibratedProbabilityInput(
            forecast_value=66.0,
            target_value=64.0,
            threshold_direction="above",
            dispersion=1.0,
            lead_time_hours=0.0,
        ),
        rmse_policy=LeadTimeRmsePolicy(base_rmse=0.0, rmse_per_day=0.0, minimum_sigma=0.5),
    )
    long = threshold_probability(
        CalibratedProbabilityInput(
            forecast_value=66.0,
            target_value=64.0,
            threshold_direction="above",
            dispersion=1.0,
            lead_time_hours=48.0,
        ),
        rmse_policy=LeadTimeRmsePolicy(base_rmse=0.0, rmse_per_day=1.0, minimum_sigma=0.5),
    )

    assert short.sigma == 1.0
    assert long.sigma == round(math.sqrt(5.0), 4)
    assert long.probability_yes < short.probability_yes
    assert long.probability_yes > 0.5


def test_threshold_edge_z_score_handles_below_direction() -> None:
    probability = threshold_probability(
        CalibratedProbabilityInput(
            forecast_value=62.0,
            target_value=64.0,
            threshold_direction="below",
            dispersion=2.0,
            market_yes_price=0.40,
        )
    )

    assert probability.probability_yes == 0.8413
    assert probability.z_score == 1.0
    assert probability.edge == 0.4413


def test_build_model_output_uses_calibrated_probability_when_threshold_data_is_sufficient() -> None:
    structure = MarketStructure(
        city="Denver",
        measurement_kind="high",
        unit="f",
        is_threshold=True,
        is_exact_bin=False,
        target_value=64.0,
        range_low=None,
        range_high=None,
        threshold_direction="above",
    )
    forecast = ForecastBundle(
        source_count=3,
        consensus_value=66.0,
        dispersion=2.0,
        historical_station_available=True,
    )

    model = build_model_output(structure, forecast)

    assert model.probability_yes == 0.84
    assert model.confidence == 0.65
    assert model.method == "calibrated_gaussian_threshold_v1"


def test_build_model_output_preserves_safe_fallback_when_data_is_insufficient() -> None:
    structure = MarketStructure(
        city="Denver",
        measurement_kind="high",
        unit="f",
        is_threshold=True,
        is_exact_bin=False,
        target_value=64.0,
        range_low=None,
        range_high=None,
        threshold_direction="above",
    )
    forecast = ForecastBundle(
        source_count=1,
        consensus_value=None,
        dispersion=2.0,
        historical_station_available=False,
    )

    model = build_model_output(structure, forecast)

    assert model.probability_yes == 0.50
    assert model.method == "calibrated_threshold_v1"


def test_build_model_output_uses_grouped_rmse_policy_context_to_soften_threshold_probability() -> None:
    bucket = LeadTimeBucket(start_hours=24.0, end_hours=72.0)
    rmse_policy = GroupedRmsePolicy(
        estimates={
            ("denver", "kden", "high", bucket): RmseEstimate(rmse=3.0, count=8),
            (None, None, None, None): RmseEstimate(rmse=0.0, count=20),
        },
        minimum_sigma=0.6,
    )
    structure = MarketStructure(
        city="Denver",
        measurement_kind="high",
        unit="f",
        is_threshold=True,
        is_exact_bin=False,
        target_value=64.0,
        range_low=None,
        range_high=None,
        threshold_direction="above",
    )
    forecast = ForecastBundle(
        source_count=3,
        consensus_value=66.0,
        dispersion=1.0,
        historical_station_available=True,
        source_station_code="KDEN",
        lead_time_hours=48.0,
    )

    model = build_model_output(structure, forecast, rmse_policy=rmse_policy)

    assert model.probability_yes == 0.74
    assert model.probability_yes < build_model_output(structure, forecast).probability_yes
    assert model.method == "calibrated_gaussian_threshold_v1"


def test_build_model_output_uses_grouped_rmse_policy_context_to_widen_exact_bin_probability() -> None:
    bucket = LeadTimeBucket(start_hours=24.0, end_hours=72.0)
    rmse_policy = GroupedRmsePolicy(
        estimates={
            ("denver", "kden", "high", bucket): RmseEstimate(rmse=3.0, count=8),
            (None, None, None, None): RmseEstimate(rmse=0.0, count=20),
        },
        minimum_sigma=0.6,
    )
    structure = MarketStructure(
        city="Denver",
        measurement_kind="high",
        unit="f",
        is_threshold=False,
        is_exact_bin=True,
        target_value=None,
        range_low=64.0,
        range_high=66.0,
    )
    forecast = ForecastBundle(
        source_count=3,
        consensus_value=65.0,
        dispersion=1.0,
        historical_station_available=True,
        source_station_code="KDEN",
        lead_time_hours=48.0,
    )

    model = build_model_output(structure, forecast, rmse_policy=rmse_policy)

    assert model.probability_yes == 0.25
    assert model.probability_yes < build_model_output(structure, forecast).probability_yes
    assert model.method == "calibrated_gaussian_bin_v1"
