from __future__ import annotations

from typing import Any

from weather_pm.models import ExecutionFeatures


def build_execution_features(raw_market: dict[str, Any]) -> ExecutionFeatures:
    best_bid = _as_float(raw_market.get("best_bid"))
    best_ask = _as_float(raw_market.get("best_ask"))
    spread = round(max(best_ask - best_bid, 0.0), 2)
    volume_usd = _as_float(raw_market.get("volume", raw_market.get("volume_usd")))
    hours_to_resolution = _optional_float(raw_market.get("hours_to_resolution"))
    fillable_size_usd = round(volume_usd * 0.01, 2)

    execution_speed_required = "high" if hours_to_resolution is not None and hours_to_resolution <= 6 else "low"
    if spread >= 0.06 or volume_usd < 1500:
        slippage_risk = "high"
    elif spread >= 0.04 or volume_usd < 5000:
        slippage_risk = "medium"
    else:
        slippage_risk = "low"

    return ExecutionFeatures(
        spread=spread,
        hours_to_resolution=hours_to_resolution,
        volume_usd=volume_usd,
        fillable_size_usd=fillable_size_usd,
        execution_speed_required=execution_speed_required,
        slippage_risk=slippage_risk,
    )


def _as_float(value: Any) -> float:
    if value is None:
        return 0.0
    return float(value)


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)
