from __future__ import annotations

from weather_pm.dynamic_position_sizing import (
    ExposureState,
    SizingInput,
    SizingPolicy,
    build_exposure_index,
    calculate_dynamic_position_size,
)


def test_grid_style_positive_edge_opens_small_position() -> None:
    decision = calculate_dynamic_position_size(
        SizingInput(
            market_id="m1",
            surface_key="Paris|2026-04-27|high_temp",
            model_probability=0.67,
            market_price=0.55,
            net_edge=0.108,
            confidence=0.82,
            spread=0.03,
            depth_usd=900.0,
            hours_to_resolution=18.0,
            wallet_style="breadth/grid small-ticket surface trader",
            current_market_exposure_usdc=0.0,
            current_surface_exposure_usdc=0.0,
            current_total_weather_exposure_usdc=40.0,
        ),
        policy=SizingPolicy.paper_weather_grid_default(),
    )

    assert decision.action == "OPEN"
    assert 5.0 <= decision.recommended_size_usdc <= 15.0
    assert decision.max_market_remaining_usdc > 0
    assert decision.wallet_style_reference == "breadth/grid small-ticket surface trader"


def test_large_ticket_wallet_does_not_force_large_size() -> None:
    decision = calculate_dynamic_position_size(
        SizingInput(
            market_id="m2",
            surface_key="Dallas|2026-04-27|high_temp",
            model_probability=0.72,
            market_price=0.58,
            net_edge=0.12,
            confidence=0.85,
            spread=0.04,
            depth_usd=1200.0,
            hours_to_resolution=12.0,
            wallet_style="sparse/large-ticket conviction trader",
            current_market_exposure_usdc=0.0,
            current_surface_exposure_usdc=0.0,
            current_total_weather_exposure_usdc=20.0,
        ),
        policy=SizingPolicy.paper_weather_grid_default(),
    )

    assert decision.action == "OPEN"
    assert decision.recommended_size_usdc <= 15.0
    assert "large_ticket_style_capped" in decision.reasons


def test_surface_cap_blocks_repeated_add() -> None:
    decision = calculate_dynamic_position_size(
        SizingInput(
            market_id="m3",
            surface_key="Hong Kong|2026-04-26|high_temp",
            model_probability=0.80,
            market_price=0.62,
            net_edge=0.15,
            confidence=0.9,
            spread=0.02,
            depth_usd=1500.0,
            hours_to_resolution=4.0,
            wallet_style="breadth/grid small-ticket surface trader",
            current_market_exposure_usdc=10.0,
            current_surface_exposure_usdc=50.0,
            current_total_weather_exposure_usdc=120.0,
        ),
        policy=SizingPolicy.paper_weather_grid_default(),
    )

    assert decision.action == "HOLD_CAPPED"
    assert decision.recommended_size_usdc == 0.0
    assert "surface_cap_reached" in decision.reasons


def test_thin_book_or_wide_spread_only_allows_probe() -> None:
    decision = calculate_dynamic_position_size(
        SizingInput(
            market_id="m4",
            surface_key="Seoul|2026-04-27|high_temp",
            model_probability=0.70,
            market_price=0.55,
            net_edge=0.12,
            confidence=0.84,
            spread=0.12,
            depth_usd=35.0,
            hours_to_resolution=20.0,
            wallet_style="breadth/grid small-ticket surface trader",
            current_market_exposure_usdc=0.0,
            current_surface_exposure_usdc=0.0,
            current_total_weather_exposure_usdc=0.0,
        ),
        policy=SizingPolicy.paper_weather_grid_default(),
    )

    assert decision.action == "PROBE"
    assert 1.0 <= decision.recommended_size_usdc <= 3.0
    assert "execution_quality_poor" in decision.reasons


def test_build_exposure_index_groups_by_market_and_surface() -> None:
    positions = [
        {"market_id": "m1", "surface_key": "Paris|2026-04-27|high_temp", "filled_usdc": 10.0},
        {"market_id": "m2", "surface_key": "Paris|2026-04-27|high_temp", "paper_notional_usd": 12.5},
        {"market_id": "m3", "surface_key": "Seoul|2026-04-27|high_temp", "filled_usdc": 7.5},
    ]

    exposure = build_exposure_index(positions)

    assert exposure["by_market"] == {"m1": 10.0, "m2": 12.5, "m3": 7.5}
    assert exposure["by_surface"] == {
        "Paris|2026-04-27|high_temp": 22.5,
        "Seoul|2026-04-27|high_temp": 7.5,
    }
    assert exposure["total_weather"] == 30.0


def test_exposure_state_alias_is_available() -> None:
    assert ExposureState is SizingInput
