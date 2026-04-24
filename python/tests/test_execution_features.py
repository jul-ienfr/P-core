from __future__ import annotations

from weather_pm.execution_features import build_execution_features


def test_build_execution_features_caps_depth_to_levels_within_max_impact() -> None:
    execution = build_execution_features(
        {
            "best_bid": 0.44,
            "best_ask": 0.45,
            "yes_price": 0.445,
            "volume": 50_000.0,
            "hours_to_resolution": 12.0,
            "max_impact_bps": 150.0,
            "ask_depth_usd": 137.5,
            "bid_depth_usd": 121.4,
            "asks": [
                {"price": 0.45, "size": 100.0},
                {"price": 0.456, "size": 50.0},
                {"price": 0.46, "size": 200.0},
            ],
            "bids": [
                {"price": 0.44, "size": 10.0},
                {"price": 0.434, "size": 100.0},
                {"price": 0.43, "size": 200.0},
            ],
        }
    )

    assert execution.order_book_depth_usd == 47.8
    assert execution.fillable_size_usd == 47.8
    assert execution.best_effort_reason is None


def test_build_execution_features_uses_aggregated_depth_fallback_when_book_levels_missing() -> None:
    execution = build_execution_features(
        {
            "best_bid": 0.44,
            "best_ask": 0.45,
            "yes_price": 0.445,
            "volume": 50_000.0,
            "hours_to_resolution": 12.0,
            "ask_depth_usd": 137.5,
            "bid_depth_usd": 121.4,
            "asks": [],
            "bids": [],
        }
    )

    assert execution.order_book_depth_usd == 121.4
    assert execution.fillable_size_usd == 121.4
    assert execution.best_effort_reason is None


def test_build_execution_features_skips_when_impact_capped_depth_is_too_thin() -> None:
    execution = build_execution_features(
        {
            "best_bid": 0.44,
            "best_ask": 0.45,
            "yes_price": 0.445,
            "volume": 500_000.0,
            "hours_to_resolution": 12.0,
            "max_impact_bps": 150.0,
            "ask_depth_usd": 120.0,
            "bid_depth_usd": 120.0,
            "asks": [
                {"price": 0.45, "size": 20.0},
                {"price": 0.458, "size": 100.0},
            ],
            "bids": [
                {"price": 0.44, "size": 20.0},
                {"price": 0.432, "size": 100.0},
            ],
        }
    )

    assert execution.order_book_depth_usd == 8.8
    assert execution.fillable_size_usd == 0.0
    assert execution.best_effort_reason == "missing_tradeable_quote"


def test_build_execution_features_respects_explicit_tighter_impact_cap() -> None:
    execution = build_execution_features(
        {
            "best_bid": 0.44,
            "best_ask": 0.45,
            "yes_price": 0.445,
            "volume": 50_000.0,
            "hours_to_resolution": 12.0,
            "max_impact_bps": 50.0,
            "asks": [
                {"price": 0.45, "size": 100.0},
                {"price": 0.452, "size": 100.0},
                {"price": 0.454, "size": 100.0},
            ],
            "bids": [
                {"price": 0.44, "size": 100.0},
                {"price": 0.438, "size": 100.0},
                {"price": 0.437, "size": 100.0},
            ],
        }
    )

    assert execution.order_book_depth_usd == 87.8
    assert execution.fillable_size_usd == 87.8
    assert execution.best_effort_reason is None
    assert execution.expected_slippage_bps == 0.0
    assert execution.all_in_cost_bps == 25.06
    assert execution.all_in_cost_usd == 0.22




def test_build_execution_features_uses_single_side_when_other_side_missing() -> None:
    execution = build_execution_features(
        {
            "best_bid": 0.0,
            "best_ask": 0.45,
            "yes_price": 0.445,
            "volume": 50_000.0,
            "hours_to_resolution": 12.0,
            "asks": [
                {"price": 0.45, "size": 100.0},
                {"price": 0.455, "size": 100.0},
            ],
            "bids": [],
        }
    )

    assert execution.order_book_depth_usd == 90.5
    assert execution.fillable_size_usd == 90.5
    assert execution.best_effort_reason is None
    assert execution.expected_slippage_bps == 0.0
    assert execution.all_in_cost_bps == 24.97
    assert execution.all_in_cost_usd == 0.226


def test_build_execution_features_skips_when_single_side_impact_capped_depth_is_too_thin() -> None:
    execution = build_execution_features(
        {
            "best_bid": 0.0,
            "best_ask": 0.45,
            "yes_price": 0.445,
            "volume": 500_000.0,
            "hours_to_resolution": 12.0,
            "max_impact_bps": 50.0,
            "asks": [
                {"price": 0.45, "size": 20.0},
                {"price": 0.46, "size": 100.0},
            ],
            "bids": [],
        }
    )

    assert execution.order_book_depth_usd == 9.0
    assert execution.fillable_size_usd == 0.0
    assert execution.best_effort_reason == "missing_tradeable_quote"