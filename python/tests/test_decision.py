from __future__ import annotations

from weather_pm.decision import build_decision
from weather_pm.models import DecisionResult, ScoreResult


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
