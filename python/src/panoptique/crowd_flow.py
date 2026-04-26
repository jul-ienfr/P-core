from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from .contracts import CrowdFlowObservation, MarketSnapshot, ShadowPrediction


def _price(snapshot: MarketSnapshot) -> float:
    if snapshot.yes_price is not None:
        return float(snapshot.yes_price)
    if snapshot.best_bid is not None and snapshot.best_ask is not None:
        return (float(snapshot.best_bid) + float(snapshot.best_ask)) / 2.0
    raise ValueError("snapshot price is required for crowd-flow measurement")


def _volume(snapshot: MarketSnapshot) -> float:
    if snapshot.volume is None:
        raise ValueError("snapshot volume is required for crowd-flow measurement")
    return float(snapshot.volume)


def _round(value: float, places: int = 6) -> float:
    return round(float(value), places)


def price_delta_after_prediction(before: MarketSnapshot, after: MarketSnapshot) -> float:
    """Return after-window YES price/mid delta for the same market."""
    if before.market_id != after.market_id:
        raise ValueError("before and after snapshots must be for the same market")
    return _round(_price(after) - _price(before))


def volume_delta_after_prediction(before: MarketSnapshot, after: MarketSnapshot) -> float:
    """Return after-window cumulative volume delta for the same market."""
    if before.market_id != after.market_id:
        raise ValueError("before and after snapshots must be for the same market")
    return _round(_volume(after) - _volume(before))


def direction_hit(predicted_direction: str, price_delta: float, *, flat_epsilon: float = 0.005) -> bool:
    direction = predicted_direction.lower()
    if direction in {"insufficient_data", "unknown", "none"}:
        return False
    if direction == "up":
        return price_delta > flat_epsilon
    if direction == "down":
        return price_delta < -flat_epsilon
    if direction == "flat":
        return abs(price_delta) <= flat_epsilon
    raise ValueError(f"unsupported predicted crowd direction: {predicted_direction}")


def magnitude_bucket(price_delta: float) -> str:
    absolute = abs(float(price_delta))
    if absolute < 0.005:
        return "flat"
    if absolute < 0.02:
        return "small"
    if absolute < 0.05:
        return "medium"
    return "large"


def liquidity_caveat(before: MarketSnapshot, after: MarketSnapshot, *, min_liquidity: float = 100.0) -> str | None:
    values = [value for value in (before.liquidity, after.liquidity) if value is not None]
    if not values:
        return "unknown_liquidity"
    if min(float(value) for value in values) < min_liquidity:
        return "insufficient_liquidity"
    return None


def _timestamp_id(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def compute_crowd_flow_observation(
    prediction: ShadowPrediction,
    before: MarketSnapshot,
    after: MarketSnapshot,
    *,
    window_seconds: int,
    min_liquidity: float = 100.0,
) -> CrowdFlowObservation:
    if prediction.market_id != before.market_id or before.market_id != after.market_id:
        raise ValueError("prediction, before snapshot, and after snapshot must be for the same market")
    delta = price_delta_after_prediction(before, after)
    vol_delta = volume_delta_after_prediction(before, after)
    caveat = liquidity_caveat(before, after, min_liquidity=min_liquidity)
    hit = direction_hit(prediction.predicted_crowd_direction, delta)
    execution_feasibility = "liquidity_ok" if caveat is None else caveat
    metrics: dict[str, Any] = {
        "agent_id": prediction.agent_id,
        "confidence": prediction.confidence,
        "predicted_crowd_direction": prediction.predicted_crowd_direction,
        "magnitude_bucket": magnitude_bucket(delta),
        "before_snapshot_id": before.snapshot_id,
        "after_snapshot_id": after.snapshot_id,
        "before_price": _round(_price(before)),
        "after_price": _round(_price(after)),
        "before_volume": _round(_volume(before)),
        "after_volume": _round(_volume(after)),
        "measurement_target": "crowd_flow_prediction_accuracy",
        "event_accuracy": "not_measured",
        "execution_feasibility": execution_feasibility,
        "paper_only": True,
        "trading_action": "none",
        "category": prediction.features.get("category") or prediction.features.get("market_category") or "unknown",
    }
    return CrowdFlowObservation(
        observation_id=f"crowd-flow-{prediction.prediction_id}-{window_seconds}-{_timestamp_id(after.observed_at)}",
        prediction_id=prediction.prediction_id,
        market_id=prediction.market_id,
        observed_at=after.observed_at,
        window_seconds=window_seconds,
        price_delta=delta,
        volume_delta=vol_delta,
        direction_hit=hit,
        liquidity_caveat=caveat,
        metrics=metrics,
    )
