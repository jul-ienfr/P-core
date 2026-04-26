from __future__ import annotations

from datetime import UTC, datetime, timedelta

from panoptique.contracts import MarketSnapshot, ShadowPrediction
from panoptique.crowd_flow import (
    compute_crowd_flow_observation,
    direction_hit,
    liquidity_caveat,
    magnitude_bucket,
    price_delta_after_prediction,
    volume_delta_after_prediction,
)


BASE = datetime(2026, 4, 26, 12, 0, tzinfo=UTC)


def snapshot(*, at: datetime, price: float | None, volume: float | None, liquidity: float | None = 500.0) -> MarketSnapshot:
    return MarketSnapshot(
        snapshot_id=f"snap-{at.timestamp()}",
        market_id="m1",
        slug="weather-rain",
        question="Will it rain?",
        source="fixture",
        observed_at=at,
        yes_price=price,
        volume=volume,
        liquidity=liquidity,
    )


def prediction(direction: str = "up", confidence: float = 0.72) -> ShadowPrediction:
    return ShadowPrediction(
        prediction_id="pred-1",
        market_id="m1",
        agent_id="round_number_price_bot",
        observed_at=BASE,
        horizon_seconds=900,
        predicted_crowd_direction=direction,
        confidence=confidence,
        rationale="paper-only crowd-flow forecast; no real order placed",
        features={"prediction_target": "crowd_behavior_not_event_truth", "category": "weather"},
    )


def test_delta_direction_bucket_and_liquidity_are_pure() -> None:
    before = snapshot(at=BASE, price=0.50, volume=100.0, liquidity=25.0)
    after = snapshot(at=BASE + timedelta(minutes=15), price=0.56, volume=170.0, liquidity=25.0)

    assert price_delta_after_prediction(before, after) == 0.06
    assert volume_delta_after_prediction(before, after) == 70.0
    assert direction_hit("up", 0.06) is True
    assert direction_hit("down", 0.06) is False
    assert direction_hit("flat", 0.002) is True
    assert magnitude_bucket(0.0) == "flat"
    assert magnitude_bucket(0.006) == "small"
    assert magnitude_bucket(0.025) == "medium"
    assert magnitude_bucket(0.08) == "large"
    assert liquidity_caveat(before, after, min_liquidity=100.0) == "insufficient_liquidity"


def test_compute_observation_separates_crowd_accuracy_from_execution_feasibility() -> None:
    before = snapshot(at=BASE, price=0.50, volume=100.0, liquidity=40.0)
    after = snapshot(at=BASE + timedelta(minutes=5), price=0.53, volume=125.0, liquidity=35.0)

    observation = compute_crowd_flow_observation(prediction(), before, after, window_seconds=300, min_liquidity=100.0)

    assert observation.prediction_id == "pred-1"
    assert observation.price_delta == 0.03
    assert observation.volume_delta == 25.0
    assert observation.direction_hit is True
    assert observation.liquidity_caveat == "insufficient_liquidity"
    assert observation.metrics["measurement_target"] == "crowd_flow_prediction_accuracy"
    assert observation.metrics["event_accuracy"] == "not_measured"
    assert observation.metrics["execution_feasibility"] == "insufficient_liquidity"
    assert observation.metrics["paper_only"] is True
    assert observation.metrics["trading_action"] == "none"


def test_missing_price_or_wrong_market_prevents_silent_measurement() -> None:
    before = snapshot(at=BASE, price=None, volume=100.0)
    after = snapshot(at=BASE + timedelta(minutes=5), price=0.52, volume=125.0)

    try:
        price_delta_after_prediction(before, after)
    except ValueError as exc:
        assert "price" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("missing price should fail")

    other = MarketSnapshot(**{**after.to_record(), "market_id": "other"})
    try:
        compute_crowd_flow_observation(prediction(), snapshot(at=BASE, price=0.5, volume=1.0), other, window_seconds=300)
    except ValueError as exc:
        assert "same market" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("market mismatch should fail")
