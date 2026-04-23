from __future__ import annotations

from datetime import datetime, timezone
import sys
from pathlib import Path
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from prediction_core.calibration import (
    calibration_bucket,
    calibration_mean,
    clamp_confidence,
    score_category,
    score_horizon_bucket,
    score_market_family,
    score_metadata,
    score_record_payload,
)


def test_clamp_confidence_bounds_values_inside_closed_interval() -> None:
    assert clamp_confidence(-0.2) == 1e-9
    assert clamp_confidence(0.42) == 0.42
    assert clamp_confidence(1.2) == 1.0 - 1e-9


def test_calibration_mean_returns_default_for_empty_sequences() -> None:
    assert calibration_mean([], default=0.25) == 0.25
    assert calibration_mean([0.2, 0.4, 0.6]) == 0.4


def test_calibration_bucket_formats_probability_ranges() -> None:
    assert calibration_bucket(0.0) == "0.0-0.1"
    assert calibration_bucket(0.42) == "0.4-0.5"
    assert calibration_bucket(1.0) == "0.9-1.0"


def test_score_metadata_merges_manifest_forecast_and_score_metadata() -> None:
    score = SimpleNamespace(
        manifest=SimpleNamespace(metadata={"category": "weather"}, inputs={"theme": "storm"}),
        forecast=SimpleNamespace(metadata={"engine": "mixtral"}),
        metadata={"window": "7d"},
    )
    assert score_metadata(score) == {
        "category": "weather",
        "theme": "storm",
        "engine": "mixtral",
        "window": "7d",
    }


def test_score_market_family_category_and_horizon_bucket_resolve_from_metadata() -> None:
    score = SimpleNamespace(
        manifest=SimpleNamespace(metadata={"market_family": "meteo"}, inputs={"horizon_bucket": "short"}),
        forecast=SimpleNamespace(metadata={}),
        metadata={"category": "rain"},
        venue="polymarket",
    )
    assert score_market_family(score) == "meteo"
    assert score_category(score) == "rain"
    assert score_horizon_bucket(score) == "short"


def test_score_market_family_falls_back_to_venue_and_horizon_to_unknown() -> None:
    score = SimpleNamespace(
        manifest=None,
        forecast=None,
        metadata={},
        venue="polymarket",
    )
    assert score_market_family(score) == "polymarket"
    assert score_horizon_bucket(score) == "unknown"


def test_score_record_payload_builds_minimal_canonical_snapshot() -> None:
    forecast_ts = datetime(2026, 4, 23, 12, 0, tzinfo=timezone.utc)
    score = SimpleNamespace(
        run_id="run-1",
        market_id="market-1",
        probability_yes=0.62,
        outcome_yes=True,
        brier_score=0.1444,
        log_loss=0.4780358009,
        forecast=SimpleNamespace(
            metadata={"model_family": "ensemble"},
            market_implied_probability=0.55,
            forecast_ts=forecast_ts,
            recommendation_action="bet",
            model_used="mixtral",
        ),
        manifest=SimpleNamespace(metadata={"market_family": "weather"}, inputs={"horizon_bucket": "short"}, updated_at=forecast_ts),
        metadata={"category": "rain"},
        venue="polymarket",
    )
    payload = score_record_payload(score)
    assert payload["evaluation_id"] == "run-1"
    assert payload["market_id"] == "market-1"
    assert payload["forecast_probability"] == 0.62
    assert payload["market_baseline_probability"] == 0.55
    assert payload["resolved_outcome"] is True
    assert payload["ece_bucket"] == "0.6-0.7"
    assert payload["market_family"] == "weather"
    assert payload["horizon_bucket"] == "short"
    assert payload["market_baseline_delta"] == 0.07
    assert payload["market_baseline_delta_bps"] == 700.0
    assert payload["cutoff_at"] == forecast_ts
    assert payload["metadata"]["category"] == "rain"
