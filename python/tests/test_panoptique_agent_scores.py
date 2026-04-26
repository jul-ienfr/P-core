from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from panoptique.agent_scores import (
    bind_shadow_prediction_to_crowd_flow,
    bind_shadow_prediction_to_event_outcome,
    executable_edge_after_costs_record,
)
from panoptique.contracts import CrowdFlowObservation, ShadowPrediction
from prediction_core.evaluation import ece_bucket, evaluation_record_canonical, log_loss


BASE = datetime(2026, 4, 26, 12, 0, tzinfo=UTC)


def prediction(*, confidence: float = 0.7, event_probability_yes: float = 0.62) -> ShadowPrediction:
    return ShadowPrediction(
        prediction_id="sp-1",
        market_id="m-1",
        agent_id="agent-a",
        observed_at=BASE,
        horizon_seconds=900,
        predicted_crowd_direction="up",
        confidence=confidence,
        rationale="paper-only shadow prediction; no real order placed",
        features={
            "event_probability_yes": event_probability_yes,
            "market_baseline_probability": 0.55,
            "category": "weather",
            "horizon_bucket": "15m",
        },
    )


def observation(*, direction_hit: bool = True) -> CrowdFlowObservation:
    return CrowdFlowObservation(
        observation_id="cf-1",
        prediction_id="sp-1",
        market_id="m-1",
        observed_at=BASE + timedelta(minutes=15),
        window_seconds=900,
        price_delta=0.04,
        volume_delta=100.0,
        direction_hit=direction_hit,
        liquidity_caveat=None,
        metrics={"execution_feasibility": "liquidity_ok"},
    )


def test_event_outcome_score_uses_existing_evaluation_metrics() -> None:
    score = bind_shadow_prediction_to_event_outcome(prediction(), resolved_outcome=True)

    expected = evaluation_record_canonical(
        {
            "evaluation_id": "event-sp-1",
            "question_id": "m-1",
            "market_id": "m-1",
            "forecast_probability": 0.62,
            "resolved_outcome": True,
            "market_baseline_probability": 0.55,
            "model_family": "agent-a",
            "market_family": "weather",
            "horizon_bucket": "15m",
            "cutoff_at": BASE,
            "metadata": {"category": "weather", "source": "panoptique_shadow_prediction"},
        }
    )

    assert score["metric_target"] == "event_outcome_forecasting"
    assert score["brier_score"] == expected["brier_score"] == pytest.approx((0.62 - 1.0) ** 2)
    assert score["log_loss"] == expected["log_loss"] == pytest.approx(log_loss(0.62, True))
    assert score["ece_bucket"] == expected["ece_bucket"] == ece_bucket(0.62)
    assert score["paper_only"] is True
    assert score["research_only"] is True
    assert score["capital_allocated"] is False
    assert score["metadata"]["measurement_target"] == "event_outcome_forecasting"


def test_crowd_flow_score_separates_movement_forecasting_from_event_truth() -> None:
    score = bind_shadow_prediction_to_crowd_flow(prediction(confidence=0.8), observation(direction_hit=False))

    assert score["metric_target"] == "crowd_movement_forecasting"
    assert score["forecast_probability"] == 0.8
    assert score["resolved_outcome"] is False
    assert score["brier_score"] == pytest.approx((0.8 - 0.0) ** 2)
    assert score["metadata"]["measurement_target"] == "crowd_movement_forecasting"
    assert score["metadata"]["event_outcome_forecasting"] == "not_measured"
    assert score["metadata"]["executable_edge_after_costs"] == "not_measured"
    assert score["paper_only"] is True
    assert score["capital_allocated"] is False


def test_crowd_flow_score_requires_matching_prediction_and_market() -> None:
    mismatched = CrowdFlowObservation(**{**observation().to_record(), "prediction_id": "other", "observed_at": observation().observed_at})

    with pytest.raises(ValueError, match="same prediction and market"):
        bind_shadow_prediction_to_crowd_flow(prediction(), mismatched)


def test_executable_edge_after_costs_record_is_measurement_only() -> None:
    record = executable_edge_after_costs_record(
        market_id="m-1",
        agent_id="agent-a",
        gross_edge_bps=120.0,
        estimated_cost_bps=150.0,
        observed_at=BASE,
    )

    assert record["metric_target"] == "executable_edge_after_costs"
    assert record["net_edge_bps"] == -30.0
    assert record["executable"] is False
    assert record["paper_only"] is True
    assert record["research_only"] is True
    assert record["capital_allocated"] is False
    assert record["trading_action"] == "none"
