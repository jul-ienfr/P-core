from __future__ import annotations

from prediction_core.decision.entry_policy import EntryPolicy, evaluate_entry


def test_evaluate_entry_allows_trade_when_price_edge_confidence_and_execution_are_inside_policy() -> None:
    decision = evaluate_entry(
        policy=EntryPolicy(
            name="weather_station",
            q_min=0.08,
            q_max=0.92,
            min_edge=0.07,
            min_confidence=0.75,
            max_spread=0.08,
            min_depth_usd=50.0,
            max_position_usd=10.0,
        ),
        market_price=0.55,
        model_probability=0.67,
        confidence=0.81,
        spread=0.03,
        depth_usd=240.0,
        execution_cost_bps=120.0,
    )

    assert decision.enter is True
    assert decision.action == "paper_trade_small"
    assert decision.blocked_by == []
    assert decision.edge_gross == 0.12
    assert decision.edge_net_all_in == 0.108
    assert decision.size_hint_usd == 10.0
    assert decision.to_dict()["policy"] == "weather_station"


def test_evaluate_entry_blocks_with_specific_reasons_before_sizing() -> None:
    decision = evaluate_entry(
        policy=EntryPolicy(
            name="crypto_5m_conservative",
            q_min=0.60,
            q_max=0.95,
            min_edge=0.05,
            min_confidence=0.85,
            max_spread=0.02,
            min_depth_usd=1000.0,
        ),
        market_price=0.40,
        model_probability=0.43,
        confidence=0.70,
        spread=0.06,
        depth_usd=100.0,
        execution_cost_bps=100.0,
    )

    assert decision.enter is False
    assert decision.action == "skip"
    assert decision.size_hint_usd == 0.0
    assert decision.blocked_by == [
        "price_outside_window",
        "edge_below_threshold",
        "confidence_below_threshold",
        "spread_too_wide",
        "depth_insufficient",
        "execution_cost_exceeds_edge",
    ]
    assert decision.edge_gross == 0.03
    assert decision.edge_net_all_in == 0.02


def test_evaluate_entry_supports_no_side_for_buying_no_outcomes() -> None:
    decision = evaluate_entry(
        policy=EntryPolicy(
            name="tail_risk_micro",
            q_min=0.01,
            q_max=0.20,
            min_edge=0.09,
            min_confidence=0.90,
            max_spread=0.05,
            min_depth_usd=20.0,
            max_position_usd=5.0,
        ),
        market_price=0.12,
        model_probability=0.02,
        confidence=0.95,
        spread=0.02,
        depth_usd=100.0,
        execution_cost_bps=50.0,
        side="no",
    )

    assert decision.enter is True
    assert decision.side == "no"
    assert decision.edge_gross == 0.10
    assert decision.edge_net_all_in == 0.095
    assert decision.size_hint_usd == 5.0
