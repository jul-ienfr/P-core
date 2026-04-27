from __future__ import annotations

from weather_pm.portfolio_risk import (
    PortfolioRiskConfig,
    apply_portfolio_risk_to_candidates,
    classify_stress_robustness,
    enforce_portfolio_caps,
    size_candidate_for_portfolio,
)


def _candidate(**overrides):
    payload = {
        "market_id": "chicago-high-72f-or-higher-20260430",
        "city": "Chicago",
        "date": "2026-04-30",
        "source_station_code": "KMDW",
        "source_provider": "noaa",
        "primary_archetype": "threshold_harvester",
        "candidate_side": "YES",
        "correlated_surface_id": "Chicago|2026-04-30|high|f|KMDW",
        "decision_status": "trade",
        "source_direct": True,
        "source_status": "source_confirmed",
        "probability_edge": 0.14,
        "prediction_probability": 0.66,
        "market_price": 0.52,
        "forecast_value": 74.0,
        "threshold": 72.0,
        "sigma": 1.0,
        "error_width": 1.0,
        "edge_source": "official_station_confirmed_threshold",
        "execution_blocker": None,
    }
    payload.update(overrides)
    return payload


def test_portfolio_risk_enforces_total_city_station_archetype_side_and_correlated_caps():
    config = PortfolioRiskConfig(
        total_paper_cap_usdc=20,
        total_live_cap_usdc=0,
        city_date_cap_usdc=12,
        station_source_cap_usdc=10,
        archetype_cap_usdc=9,
        side_cap_usdc=8,
        correlated_surface_cap_usdc=7,
    )
    existing = [
        {
            "mode": "paper",
            "city": "Chicago",
            "date": "2026-04-30",
            "source_station_code": "KMDW",
            "source_provider": "noaa",
            "primary_archetype": "threshold_harvester",
            "candidate_side": "YES",
            "correlated_surface_id": "Chicago|2026-04-30|high|f|KMDW",
            "notional_usdc": 5.0,
        }
    ]

    result = enforce_portfolio_caps(_candidate(), requested_size_usdc=10, existing_exposures=existing, config=config)

    assert result["requested_size_usdc"] == 10.0
    assert result["approved_size_usdc"] == 2.0
    assert result["cap_status"] == "capped"
    assert result["binding_caps"] == ["correlated_surface"]
    assert result["remaining_capacity_usdc"]["correlated_surface"] == 2.0
    assert result["remaining_capacity_usdc"]["side"] == 3.0
    assert result["remaining_capacity_usdc"]["total_paper"] == 15.0


def test_portfolio_risk_blocks_correlated_market_when_surface_capacity_is_used():
    config = PortfolioRiskConfig(correlated_surface_cap_usdc=5, min_paper_size_usdc=1)
    existing = [
        {
            "mode": "paper",
            "city": "Chicago",
            "date": "2026-04-30",
            "source_station_code": "KMDW",
            "source_provider": "noaa",
            "correlated_surface_id": "Chicago|2026-04-30|high|f|KMDW",
            "candidate_side": "NO",
            "notional_usdc": 5.0,
        }
    ]

    result = enforce_portfolio_caps(_candidate(candidate_side="YES"), requested_size_usdc=4, existing_exposures=existing, config=config)

    assert result["approved_size_usdc"] == 0.0
    assert result["cap_status"] == "blocked"
    assert "correlated_surface" in result["binding_caps"]


def test_fragile_crude_proxy_long_tail_candidate_is_micro_paper_only():
    result = size_candidate_for_portfolio(
        _candidate(
            market_id="miami-exact-100f-long-tail",
            primary_archetype="exact_bin_anomaly_hunter",
            edge_source="crude_proxy_long_tail",
            source_direct=False,
            source_status="source_missing",
            probability_edge=0.22,
            prediction_probability=0.08,
            market_price=0.03,
            forecast_value=94.0,
            threshold=100.0,
            sigma=4.0,
            error_width=5.0,
        ),
        existing_exposures=[],
        config=PortfolioRiskConfig(micro_paper_size_usdc=1.0, robust_paper_size_usdc=12.0),
    )

    assert result["mode"] == "paper"
    assert result["robustness_label"] == "fragile"
    assert result["requested_size_usdc"] == 1.0
    assert result["approved_size_usdc"] == 1.0
    assert result["recommendation"] == "paper_micro_only"
    assert result["live_order_allowed"] is False


def test_robust_source_confirmed_threshold_gets_larger_but_capped_paper_size():
    result = size_candidate_for_portfolio(
        _candidate(probability_edge=0.18, forecast_value=76.0, threshold=72.0, sigma=0.8, error_width=0.8),
        existing_exposures=[],
        config=PortfolioRiskConfig(robust_paper_size_usdc=15.0, correlated_surface_cap_usdc=9.0),
    )

    assert result["robustness_label"] == "robust"
    assert result["requested_size_usdc"] == 15.0
    assert result["approved_size_usdc"] == 9.0
    assert result["cap_status"] == "capped"
    assert result["recommendation"] == "paper_larger_capped"


def test_stress_test_classification_returns_robust_medium_fragile_and_avoid():
    assert classify_stress_robustness(_candidate(forecast_value=76.0, threshold=72.0, probability_edge=0.18))["label"] == "robust"
    assert classify_stress_robustness(_candidate(forecast_value=73.2, threshold=72.0, probability_edge=0.10))["label"] == "medium"
    assert classify_stress_robustness(_candidate(forecast_value=72.3, threshold=72.0, probability_edge=0.04))["label"] == "fragile"
    assert classify_stress_robustness(_candidate(forecast_value=71.5, threshold=72.0, probability_edge=-0.02))["label"] == "avoid"


def test_strategy_candidate_recommendations_include_portfolio_risk_sizing():
    sized = apply_portfolio_risk_to_candidates(
        [
            _candidate(market_id="robust", probability_edge=0.18, forecast_value=76.0),
            _candidate(market_id="fragile", edge_source="crude_proxy_long_tail", source_direct=False, forecast_value=72.2, probability_edge=0.03),
        ],
        existing_exposures=[],
        config=PortfolioRiskConfig(robust_paper_size_usdc=10.0, micro_paper_size_usdc=1.0),
    )

    by_id = {row["market_id"]: row for row in sized}
    assert by_id["robust"]["portfolio_risk"]["recommendation"] == "paper_larger_capped"
    assert by_id["robust"]["paper_notional_usdc"] == 10.0
    assert by_id["fragile"]["portfolio_risk"]["recommendation"] == "paper_micro_only"
    assert by_id["fragile"]["paper_notional_usdc"] == 1.0
