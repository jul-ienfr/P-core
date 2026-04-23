from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from prediction_core.evaluation import (
    clamp_probability,
    ece_bucket,
    evaluation_record_canonical,
    log_loss,
    safe_mean,
    weighted_mean,
)


def test_clamp_probability_bounds_values_to_zero_one() -> None:
    assert clamp_probability(-0.2) == 0.0
    assert clamp_probability(0.42) == 0.42
    assert clamp_probability(1.3) == 1.0


def test_log_loss_uses_clamped_probability_and_outcome_side() -> None:
    assert log_loss(0.0, True) == pytest.approx(-math.log(1e-9))
    assert log_loss(1.0, False) == pytest.approx(-math.log(1e-9))
    assert log_loss(0.75, True) == pytest.approx(-math.log(0.75))


def test_ece_bucket_formats_probability_bins() -> None:
    assert ece_bucket(0.0) == "0.0-0.1"
    assert ece_bucket(0.42) == "0.4-0.5"
    assert ece_bucket(1.0) == "0.9-1.0"
    assert ece_bucket(0.42, bins=4) == "0.25-0.50"
    assert ece_bucket(0.42, bins=20) == "0.40-0.45"
    assert ece_bucket(0.42, bins=3) == "0.333333-0.666667"


def test_probability_helpers_reject_non_finite_inputs() -> None:
    non_finite_values = [float("nan"), float("inf"), float("-inf")]

    for value in non_finite_values:
        with pytest.raises(ValueError, match="probability must be finite"):
            clamp_probability(value)
        with pytest.raises(ValueError, match="probability must be finite"):
            log_loss(value, True)
        with pytest.raises(ValueError, match="probability must be finite"):
            ece_bucket(value)


def test_safe_mean_returns_default_for_empty_sequences() -> None:
    assert safe_mean([], default=0.25) == 0.25
    assert safe_mean([0.2, 0.4, 0.6]) == 0.4


def test_weighted_mean_handles_empty_and_weighted_inputs() -> None:
    assert weighted_mean([], default=0.1) == 0.1
    assert weighted_mean([(0.2, 1), (0.8, 3)]) == 0.65
    assert weighted_mean([(0.4, 0), (0.9, -1)], default=0.33) == 0.33


def test_evaluation_record_canonical_builds_minimal_snapshot() -> None:
    cutoff_at = "2026-04-23T12:00:00+00:00"

    payload = evaluation_record_canonical(
        {
            "evaluation_id": "feval_123",
            "question_id": "question-1",
            "market_id": "market-1",
            "forecast_probability": 0.62,
            "resolved_outcome": True,
            "market_baseline_probability": 0.55,
            "model_family": "ensemble",
            "market_family": "weather",
            "horizon_bucket": "short",
            "cutoff_at": cutoff_at,
            "metadata": {
                "category": "rain",
                "source": "unit-test",
                "ignored": "not-exported",
            },
            "content_hash": "drop-me",
        }
    )

    assert payload == {
        "evaluation_id": "feval_123",
        "question_id": "question-1",
        "market_id": "market-1",
        "forecast_probability": 0.62,
        "resolved_outcome": True,
        "market_baseline_probability": 0.55,
        "brier_score": 0.1444,
        "log_loss": pytest.approx(-math.log(0.62)),
        "ece_bucket": "0.6-0.7",
        "abstain_flag": False,
        "model_family": "ensemble",
        "market_family": "weather",
        "horizon_bucket": "short",
        "market_baseline_delta": 0.07,
        "market_baseline_delta_bps": 700.0,
        "cutoff_at": cutoff_at,
        "metadata": {
            "category": "rain",
            "source": "unit-test",
        },
    }


def test_evaluation_record_canonical_accepts_object_input_and_prefers_explicit_scores() -> None:
    record = type(
        "Record",
        (),
        {
            "evaluation_id": "feval_456",
            "question_id": "question-2",
            "market_id": "market-2",
            "forecast_probability": 1.2,
            "resolved_outcome": False,
            "brier_score": 0.81,
            "log_loss": 1.5,
            "ece_bucket": "0.9-1.0",
            "abstain_flag": True,
            "model_family": "market-only",
            "market_family": "macro",
            "horizon_bucket": "30d",
            "market_baseline_probability": -0.5,
            "market_baseline_delta": 1.0,
            "market_baseline_delta_bps": 10000.0,
            "cutoff_at": None,
            "metadata": {"theme": "rates", "extra": "drop-me"},
            "updated_at": "drop-me",
        },
    )()

    payload = evaluation_record_canonical(record)

    assert payload == {
        "evaluation_id": "feval_456",
        "question_id": "question-2",
        "market_id": "market-2",
        "forecast_probability": 1.0,
        "resolved_outcome": False,
        "market_baseline_probability": 0.0,
        "brier_score": 0.81,
        "log_loss": 1.5,
        "ece_bucket": "0.9-1.0",
        "abstain_flag": True,
        "model_family": "market-only",
        "market_family": "macro",
        "horizon_bucket": "30d",
        "market_baseline_delta": 1.0,
        "market_baseline_delta_bps": 10000.0,
        "metadata": {
            "theme": "rates",
        },
    }
