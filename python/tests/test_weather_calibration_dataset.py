from __future__ import annotations

import math

from weather_pm.calibration_dataset import (
    GroupedRmsePolicy,
    LeadTimeBucket,
    WeatherCalibrationSample,
    group_rmse_estimates,
    load_calibration_samples,
)


def test_load_calibration_samples_from_dicts_and_csv_style_rows() -> None:
    samples = load_calibration_samples(
        [
            {
                "city": "Denver",
                "station_code": "KDEN",
                "measurement_kind": "high",
                "lead_time_hours": "6",
                "forecast_value": "66.5",
                "observed_value": "64.0",
            },
            {
                "city": " denver ",
                "station": " kden ",
                "measurement": "HIGH",
                "lead_hours": 30,
                "forecast": 70,
                "observed": 67,
            },
        ]
    )

    assert samples == [
        WeatherCalibrationSample(
            city="Denver",
            station_code="KDEN",
            measurement_kind="high",
            lead_time_hours=6.0,
            forecast_value=66.5,
            observed_value=64.0,
        ),
        WeatherCalibrationSample(
            city="denver",
            station_code="kden",
            measurement_kind="high",
            lead_time_hours=30.0,
            forecast_value=70.0,
            observed_value=67.0,
        ),
    ]


def test_load_calibration_samples_filters_by_group_and_lead_time_bucket() -> None:
    rows = [
        {"city": "Denver", "station_code": "KDEN", "measurement_kind": "high", "lead_time_hours": 6, "forecast_value": 66, "observed_value": 64},
        {"city": "Denver", "station_code": "KDEN", "measurement_kind": "low", "lead_time_hours": 6, "forecast_value": 50, "observed_value": 49},
        {"city": "Denver", "station_code": "KBJC", "measurement_kind": "high", "lead_time_hours": 6, "forecast_value": 65, "observed_value": 64},
        {"city": "Boston", "station_code": "KBOS", "measurement_kind": "high", "lead_time_hours": 6, "forecast_value": 75, "observed_value": 73},
        {"city": "Denver", "station_code": "KDEN", "measurement_kind": "high", "lead_time_hours": 30, "forecast_value": 70, "observed_value": 67},
    ]

    samples = load_calibration_samples(
        rows,
        city="denver",
        station_code="kden",
        measurement_kind="HIGH",
        lead_time_bucket=LeadTimeBucket(0, 24),
    )

    assert [(sample.city, sample.station_code, sample.measurement_kind, sample.lead_time_hours) for sample in samples] == [
        ("Denver", "KDEN", "high", 6.0)
    ]


def test_group_rmse_estimates_compute_grouped_rmse_and_global_estimate() -> None:
    samples = load_calibration_samples(
        [
            {"city": "Denver", "station_code": "KDEN", "measurement_kind": "high", "lead_time_hours": 6, "forecast_value": 66, "observed_value": 64},
            {"city": "Denver", "station_code": "KDEN", "measurement_kind": "high", "lead_time_hours": 12, "forecast_value": 68, "observed_value": 64},
            {"city": "Denver", "station_code": "KDEN", "measurement_kind": "high", "lead_time_hours": 30, "forecast_value": 70, "observed_value": 67},
            {"city": "Boston", "station_code": "KBOS", "measurement_kind": "low", "lead_time_hours": 10, "forecast_value": 40, "observed_value": 41},
        ]
    )

    estimates = group_rmse_estimates(samples, lead_time_buckets=[LeadTimeBucket(0, 24), LeadTimeBucket(24, 48)])

    short_denver = estimates[("denver", "kden", "high", LeadTimeBucket(0, 24))]
    long_denver = estimates[("denver", "kden", "high", LeadTimeBucket(24, 48))]
    global_estimate = estimates[(None, None, None, None)]

    assert short_denver.count == 2
    assert short_denver.rmse == round(math.sqrt((2.0**2 + 4.0**2) / 2), 4)
    assert long_denver.count == 1
    assert long_denver.rmse == 3.0
    assert global_estimate.count == 4
    assert global_estimate.rmse == round(math.sqrt((2.0**2 + 4.0**2 + 3.0**2 + 1.0**2) / 4), 4)


def test_grouped_rmse_policy_uses_group_rmse_then_global_then_default_sigma() -> None:
    estimates = group_rmse_estimates(
        load_calibration_samples(
            [
                {"city": "Denver", "station_code": "KDEN", "measurement_kind": "high", "lead_time_hours": 6, "forecast_value": 66, "observed_value": 64},
                {"city": "Denver", "station_code": "KDEN", "measurement_kind": "high", "lead_time_hours": 12, "forecast_value": 68, "observed_value": 64},
                {"city": "Boston", "station_code": "KBOS", "measurement_kind": "low", "lead_time_hours": 10, "forecast_value": 40, "observed_value": 41},
            ]
        ),
        lead_time_buckets=[LeadTimeBucket(0, 24), LeadTimeBucket(24, 48)],
    )
    policy = GroupedRmsePolicy(estimates=estimates, minimum_sigma=0.5, default_sigma=1.25)

    group_sigma = policy.sigma(
        dispersion=1.0,
        lead_time_hours=6,
        city="DENVER",
        station_code="kden",
        measurement_kind="High",
    )
    global_sigma = policy.sigma(
        dispersion=1.0,
        lead_time_hours=30,
        city="Denver",
        station_code="KDEN",
        measurement_kind="high",
    )
    default_sigma = GroupedRmsePolicy(estimates={}, minimum_sigma=0.5, default_sigma=1.25).sigma(
        dispersion=1.0,
        lead_time_hours=6,
        city="Denver",
        station_code="KDEN",
        measurement_kind="high",
    )

    assert group_sigma == round(math.sqrt(1.0**2 + math.sqrt(10.0) ** 2), 4)
    assert global_sigma == round(math.sqrt(1.0**2 + 2.6458**2), 4)
    assert default_sigma == round(math.sqrt(1.0**2 + 1.25**2), 4)


def test_grouped_rmse_policy_matches_lead_time_rmse_policy_call_shape_without_context() -> None:
    policy = GroupedRmsePolicy(estimates={}, minimum_sigma=0.6, default_sigma=0.0)

    assert policy.sigma(dispersion=0.2, lead_time_hours=48) == 0.6
