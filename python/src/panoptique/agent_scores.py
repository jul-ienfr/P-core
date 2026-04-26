from __future__ import annotations

from datetime import datetime
from typing import Any

from prediction_core.evaluation import evaluation_record_canonical

from .contracts import CrowdFlowObservation, ShadowPrediction


def _feature_text(prediction: ShadowPrediction, keys: tuple[str, ...], default: str = "unknown") -> str:
    for key in keys:
        value = prediction.features.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return default


def _feature_probability(prediction: ShadowPrediction, keys: tuple[str, ...], default: float) -> float:
    for key in keys:
        value = prediction.features.get(key)
        if value is None:
            continue
        return float(value)
    return float(default)


def _research_flags() -> dict[str, Any]:
    return {
        "research_only": True,
        "paper_only": True,
        "capital_allocated": False,
        "trading_action": "none",
    }


def bind_shadow_prediction_to_event_outcome(
    prediction: ShadowPrediction,
    *,
    resolved_outcome: bool,
    event_probability_key: str = "event_probability_yes",
) -> dict[str, Any]:
    """Score a shadow event-outcome forecast with existing prediction_core metrics.

    This binds a Panoptique shadow prediction to a resolved market/event outcome.
    It deliberately does not evaluate crowd movement or executable edge.
    """

    probability_yes = _feature_probability(prediction, (event_probability_key, "probability_yes", "forecast_probability"), prediction.confidence)
    market_baseline = _feature_probability(prediction, ("market_baseline_probability", "market_probability_yes"), probability_yes)
    category = _feature_text(prediction, ("category", "market_category", "theme"))
    payload = evaluation_record_canonical(
        {
            "evaluation_id": f"event-{prediction.prediction_id}",
            "question_id": prediction.market_id,
            "market_id": prediction.market_id,
            "forecast_probability": probability_yes,
            "resolved_outcome": resolved_outcome,
            "market_baseline_probability": market_baseline,
            "model_family": prediction.agent_id,
            "market_family": category,
            "horizon_bucket": _feature_text(prediction, ("horizon_bucket", "horizon", "window_bucket"), str(prediction.horizon_seconds)),
            "cutoff_at": prediction.observed_at,
            "metadata": {
                "category": category,
                "source": "panoptique_shadow_prediction",
                "calibration_version": "bookmaker_v0_scaffold",
            },
        }
    )
    assert payload is not None
    metadata = dict(payload.get("metadata", {}))
    metadata.update(
        {
            "measurement_target": "event_outcome_forecasting",
            "crowd_movement_forecasting": "not_measured",
            "executable_edge_after_costs": "not_measured",
        }
    )
    return {
        **payload,
        "metadata": metadata,
        "metric_target": "event_outcome_forecasting",
        **_research_flags(),
    }


def bind_shadow_prediction_to_crowd_flow(prediction: ShadowPrediction, observation: CrowdFlowObservation) -> dict[str, Any]:
    """Score a shadow crowd-movement forecast with existing prediction_core metrics."""

    if prediction.prediction_id != observation.prediction_id or prediction.market_id != observation.market_id:
        raise ValueError("prediction and observation must reference the same prediction and market")

    category = _feature_text(prediction, ("category", "market_category", "theme"))
    payload = evaluation_record_canonical(
        {
            "evaluation_id": f"crowd-flow-{observation.observation_id}",
            "question_id": prediction.market_id,
            "market_id": prediction.market_id,
            "forecast_probability": prediction.confidence,
            "resolved_outcome": observation.direction_hit,
            "market_baseline_probability": 0.5,
            "model_family": prediction.agent_id,
            "market_family": category,
            "horizon_bucket": _feature_text(prediction, ("horizon_bucket", "horizon", "window_bucket"), str(observation.window_seconds)),
            "cutoff_at": prediction.observed_at,
            "metadata": {
                "category": category,
                "source": "panoptique_crowd_flow_observation",
                "calibration_version": "bookmaker_v0_scaffold",
            },
        }
    )
    assert payload is not None
    metadata = dict(payload.get("metadata", {}))
    metadata.update(
        {
            "measurement_target": "crowd_movement_forecasting",
            "event_outcome_forecasting": "not_measured",
            "executable_edge_after_costs": "not_measured",
            "price_delta": observation.price_delta,
            "volume_delta": observation.volume_delta,
            "liquidity_caveat": observation.liquidity_caveat,
            "execution_feasibility": observation.metrics.get("execution_feasibility", "not_measured"),
        }
    )
    return {
        **payload,
        "metadata": metadata,
        "metric_target": "crowd_movement_forecasting",
        **_research_flags(),
    }


def executable_edge_after_costs_record(
    *,
    market_id: str,
    agent_id: str,
    gross_edge_bps: float,
    estimated_cost_bps: float,
    observed_at: datetime | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a measurement-only executable-edge record after costs.

    This is a scaffold for reporting separation only. It does not authorize,
    size, or route orders.
    """

    net_edge_bps = round(float(gross_edge_bps) - float(estimated_cost_bps), 6)
    return {
        "metric_target": "executable_edge_after_costs",
        "market_id": market_id,
        "agent_id": agent_id,
        "gross_edge_bps": round(float(gross_edge_bps), 6),
        "estimated_cost_bps": round(float(estimated_cost_bps), 6),
        "net_edge_bps": net_edge_bps,
        "executable": net_edge_bps > 0.0,
        "observed_at": observed_at,
        "metadata": {
            "measurement_target": "executable_edge_after_costs",
            "event_outcome_forecasting": "not_measured",
            "crowd_movement_forecasting": "not_measured",
            **(metadata or {}),
        },
        **_research_flags(),
    }


__all__ = [
    "bind_shadow_prediction_to_crowd_flow",
    "bind_shadow_prediction_to_event_outcome",
    "executable_edge_after_costs_record",
]
