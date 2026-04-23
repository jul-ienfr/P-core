from __future__ import annotations

from weather_pm.execution_features import build_execution_features


def test_build_execution_features_uses_market_microstructure_fields() -> None:
    result = build_execution_features(
        {
            "best_bid": 0.42,
            "best_ask": 0.45,
            "volume": 14000,
            "hours_to_resolution": 18,
        }
    )

    assert result.spread == 0.03
    assert result.hours_to_resolution == 18.0
    assert result.volume_usd == 14000.0
    assert result.fillable_size_usd == 140.0
    assert result.slippage_risk == "low"


def test_build_execution_features_penalizes_wide_spread_and_low_volume() -> None:
    result = build_execution_features(
        {
            "best_bid": 0.31,
            "best_ask": 0.39,
            "volume": 800,
            "hours_to_resolution": 3,
        }
    )

    assert result.spread == 0.08
    assert result.fillable_size_usd == 8.0
    assert result.execution_speed_required == "high"
    assert result.slippage_risk == "high"
