from __future__ import annotations

from weather_pm.decision import build_decision
from weather_pm.models import DecisionResult, ExecutionFeatures, ScoreResult


def test_build_decision_returns_trade_for_strong_market() -> None:
    score = ScoreResult(
        raw_edge=0.18,
        edge_theoretical=0.84,
        data_quality=0.88,
        resolution_clarity=0.92,
        execution_friction=0.70,
        competition_inefficiency=0.62,
        total_score=83.4,
        grade="A",
    )

    decision = build_decision(score=score, is_exact_bin=False, spread=0.03, forecast_dispersion=1.2)

    assert decision.status == "trade"
    assert decision.max_position_pct_bankroll == 0.02
    assert any("edge" in reason for reason in decision.reasons)


def test_build_decision_returns_skip_for_weak_edge() -> None:
    score = ScoreResult(
        raw_edge=0.03,
        edge_theoretical=0.45,
        data_quality=0.80,
        resolution_clarity=0.90,
        execution_friction=0.70,
        competition_inefficiency=0.55,
        total_score=72.0,
        grade="B",
    )

    decision = build_decision(score=score, is_exact_bin=False, spread=0.03, forecast_dispersion=1.0)

    assert decision.status == "skip"
    assert decision.max_position_pct_bankroll == 0.0


def test_build_decision_returns_trade_small_for_threshold_setup_with_small_but_actionable_edge() -> None:
    score = ScoreResult(
        raw_edge=0.04,
        edge_theoretical=0.20,
        data_quality=0.92,
        resolution_clarity=1.0,
        execution_friction=0.88,
        competition_inefficiency=0.46,
        total_score=60.5,
        grade="C",
    )
    execution = ExecutionFeatures(
        spread=0.03,
        hours_to_resolution=18.0,
        volume_usd=14000.0,
        fillable_size_usd=250.0,
        execution_speed_required="low",
        slippage_risk="low",
        transaction_fee_bps=0.0,
        deposit_fee_usd=0.0,
        withdrawal_fee_usd=0.0,
        order_book_depth_usd=0.0,
        expected_slippage_bps=60.0,
        all_in_cost_bps=210.0,
        all_in_cost_usd=5.25,
    )

    decision = build_decision(
        score=score,
        is_exact_bin=False,
        spread=0.03,
        forecast_dispersion=1.2,
        execution=execution,
    )

    assert decision.status == "trade_small"
    assert decision.max_position_pct_bankroll == 0.01



def test_build_decision_skips_when_all_in_costs_consume_the_edge() -> None:
    score = ScoreResult(
        raw_edge=0.06,
        edge_theoretical=0.30,
        data_quality=0.82,
        resolution_clarity=0.91,
        execution_friction=0.25,
        competition_inefficiency=0.55,
        total_score=68.0,
        grade="B",
    )
    execution = ExecutionFeatures(
        spread=0.02,
        hours_to_resolution=12.0,
        volume_usd=5000.0,
        fillable_size_usd=80.0,
        execution_speed_required="low",
        slippage_risk="medium",
        transaction_fee_bps=90.0,
        deposit_fee_usd=1.5,
        withdrawal_fee_usd=2.0,
        order_book_depth_usd=82.8,
        expected_slippage_bps=0.0,
        all_in_cost_bps=577.5,
        all_in_cost_usd=4.62,
    )

    decision = build_decision(
        score=score,
        is_exact_bin=False,
        spread=0.02,
        forecast_dispersion=1.0,
        execution=execution,
    )

    assert decision.status == "skip"
    assert decision.max_position_pct_bankroll == 0.0
    assert any("all-in costs" in reason for reason in decision.reasons)
