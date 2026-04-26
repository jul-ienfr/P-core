from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import UTC, datetime
from typing import Any
import json

from prediction_core.evaluation import clamp_probability


@dataclass(frozen=True, kw_only=True)
class BookmakerInput:
    """One research-only agent/shadow probability for bookmaker_v0."""

    agent_id: str
    probability_yes: float
    weight: float = 1.0
    brier_score: float | None = None
    calibration_bucket: str | None = None
    metric_target: str = "event_outcome_forecasting"
    metadata: dict[str, Any] = field(default_factory=dict)

    def normalized_probability(self) -> float:
        return clamp_probability(self.probability_yes)


@dataclass(frozen=True, kw_only=True)
class BookmakerOutput:
    market_id: str
    probability_yes: float
    method: str
    generated_at: datetime
    contributing_agents: list[str]
    research_only: bool = True
    paper_only: bool = True
    capital_allocated: bool = False
    trading_action: str = "none"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return json.loads(json.dumps(asdict(self), default=_json_default, sort_keys=True))

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value):
        return asdict(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def bookmaker_v0(
    inputs: list[BookmakerInput],
    *,
    market_id: str,
    generated_at: datetime | None = None,
) -> BookmakerOutput:
    """Return a paper/research-only weighted average of agent probabilities.

    v0 intentionally avoids capital allocation, order language, and correlation
    math. Anti-correlation support is represented only as placeholder metadata.
    """

    usable = [item for item in inputs if float(item.weight) > 0.0]
    if not usable:
        raise ValueError("bookmaker_v0 requires at least one positive weight")

    total_weight = sum(float(item.weight) for item in usable)
    weighted_probability = sum(item.normalized_probability() * float(item.weight) for item in usable) / total_weight
    probability_yes = round(float(weighted_probability), 12)
    metric_targets = [
        "event_outcome_forecasting",
        "crowd_movement_forecasting",
        "executable_edge_after_costs",
    ]
    metadata = {
        "input_count": len(inputs),
        "used_input_count": len(usable),
        "input_metrics": [
            {
                "agent_id": item.agent_id,
                "weight": float(item.weight),
                "probability_yes": item.normalized_probability(),
                "brier_score": item.brier_score,
                "calibration_bucket": item.calibration_bucket,
                "metric_target": item.metric_target,
            }
            for item in usable
        ],
        "metric_targets": metric_targets,
        "measurement_separation": {
            "event_outcome_forecasting": "input_metric_supported",
            "crowd_movement_forecasting": "input_metric_supported",
            "executable_edge_after_costs": "reported_separately_after_costs_only",
        },
        "anti_correlation": {
            "status": "placeholder_not_applied",
            "note": "Future versions may discount correlated agents; v0 only reports a weighted average.",
        },
        "safety": {
            "research_only": True,
            "paper_only": True,
            "capital_allocated": False,
            "trading_action": "none",
        },
    }
    return BookmakerOutput(
        market_id=market_id,
        probability_yes=probability_yes,
        method="weighted_average_v0",
        generated_at=generated_at or datetime.now(UTC),
        contributing_agents=[item.agent_id for item in usable],
        metadata=metadata,
    )


__all__ = ["BookmakerInput", "BookmakerOutput", "bookmaker_v0"]
