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
    assert result.transaction_fee_bps == 0.0
    assert result.deposit_fee_usd == 0.0
    assert result.withdrawal_fee_usd == 0.0
    assert result.order_book_depth_usd == 0.0
    assert result.expected_slippage_bps == 60.0
    assert result.all_in_cost_bps == 210.0
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
    assert result.expected_slippage_bps == 160.0
    assert result.all_in_cost_bps == 560.0
    assert result.slippage_risk == "high"


def test_build_execution_features_uses_order_book_and_external_fees_when_available() -> None:
    result = build_execution_features(
        {
            "best_bid": 0.5,
            "best_ask": 0.52,
            "volume": 6000,
            "hours_to_resolution": 10,
            "target_order_size_usd": 80,
            "taker_fee_bps": 90,
            "deposit_fee_usd": 1.5,
            "withdrawal_fee_usd": 2.0,
            "bids": [
                {"price": 0.5, "size": 100},
                {"price": 0.49, "size": 80},
            ],
            "asks": [
                {"price": 0.52, "size": 120},
                {"price": 0.54, "size": 40},
            ],
        }
    )

    assert result.order_book_depth_usd == 84.0
    assert result.fillable_size_usd == 80.0
    assert result.transaction_fee_bps == 90.0
    assert result.deposit_fee_usd == 1.5
    assert result.withdrawal_fee_usd == 2.0
    assert result.expected_slippage_bps == 0.0
    assert result.all_in_cost_usd == 4.62
    assert result.all_in_cost_bps == 577.5
    assert result.slippage_risk == "medium"
