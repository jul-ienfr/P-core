from __future__ import annotations

from weather_pm.models import (
    ExecutionFeatures,
    ForecastBundle,
    MarketStructure,
    ModelOutput,
    NeighborContext,
    ResolutionMetadata,
    ScoreResult,
)


EDGE_WEIGHT = 35
DATA_WEIGHT = 20
RESOLUTION_WEIGHT = 15
EXECUTION_WEIGHT = 15
COMPETITION_WEIGHT = 15


def score_market(
    *,
    structure: MarketStructure,
    resolution: ResolutionMetadata,
    forecast_bundle: ForecastBundle,
    model_output: ModelOutput,
    neighbor_context: NeighborContext,
    execution: ExecutionFeatures,
    yes_price: float,
) -> ScoreResult:
    raw_edge = round(model_output.probability_yes - yes_price, 2)
    edge_net_execution = _edge_net_execution(raw_edge=raw_edge, execution=execution)
    edge_for_scoring = edge_net_execution if edge_net_execution is not None else raw_edge
    edge_theoretical = _clamp(edge_for_scoring / 0.20)
    data_quality = _score_data_quality(forecast_bundle)
    resolution_clarity = _score_resolution(resolution)
    execution_friction = _score_execution(execution)
    competition_inefficiency = _score_competition(structure, neighbor_context)

    total_score = round(
        edge_theoretical * EDGE_WEIGHT
        + data_quality * DATA_WEIGHT
        + resolution_clarity * RESOLUTION_WEIGHT
        + execution_friction * EXECUTION_WEIGHT
        + competition_inefficiency * COMPETITION_WEIGHT,
        1,
    )

    if resolution.manual_review_needed:
        total_score = min(total_score, 59.0)

    grade = _grade(total_score)
    return ScoreResult(
        raw_edge=raw_edge,
        edge_theoretical=round(edge_theoretical, 2),
        data_quality=round(data_quality, 2),
        resolution_clarity=round(resolution_clarity, 2),
        execution_friction=round(execution_friction, 2),
        competition_inefficiency=round(competition_inefficiency, 2),
        total_score=total_score,
        grade=grade,
        edge_net_execution=edge_net_execution,
    )


def _edge_net_execution(*, raw_edge: float, execution: ExecutionFeatures) -> float | None:
    if execution.fillable_size_usd <= 0.0:
        return None
    return round(raw_edge - (execution.all_in_cost_bps / 10000.0), 3)


def _score_data_quality(bundle: ForecastBundle) -> float:
    source_bonus = min(bundle.source_count / 3.0, 1.0) * 0.45
    dispersion = bundle.dispersion if bundle.dispersion is not None else 5.0
    dispersion_score = max(0.0, 1.0 - min(dispersion, 5.0) / 5.0) * 0.35
    history_bonus = 0.20 if bundle.historical_station_available else 0.0
    return _clamp(source_bonus + dispersion_score + history_bonus)


def _score_resolution(resolution: ResolutionMetadata) -> float:
    score = 0.0
    if resolution.provider != "unknown":
        score += 0.25
    if resolution.station_code:
        score += 0.20
    if resolution.wording_clear:
        score += 0.20
    if resolution.rules_clear:
        score += 0.20
    if resolution.revision_risk == "low":
        score += 0.15
    elif resolution.revision_risk == "medium":
        score += 0.07
    if resolution.manual_review_needed:
        score -= 0.35
    return _clamp(score)


def _score_execution(execution: ExecutionFeatures) -> float:
    score = 0.0
    score += max(0.0, 1.0 - min(execution.spread, 0.10) / 0.10) * 0.40
    if execution.hours_to_resolution is not None:
        ideal_delta = abs(execution.hours_to_resolution - 18.0)
        score += max(0.0, 1.0 - min(ideal_delta, 18.0) / 18.0) * 0.20
    score += min(execution.volume_usd / 10000.0, 1.0) * 0.20
    score += min(execution.fillable_size_usd / 250.0, 1.0) * 0.10
    if execution.slippage_risk == "low":
        score += 0.10
    elif execution.slippage_risk == "medium":
        score += 0.05
    return _clamp(score)


def _score_competition(structure: MarketStructure, context: NeighborContext) -> float:
    score = 0.0
    score += min(context.neighbor_market_count / 4.0, 1.0) * 0.20
    score += _clamp(context.neighbor_inconsistency) * 0.45
    score += _clamp(context.threshold_bin_inconsistency) * 0.25
    if structure.is_threshold:
        score += 0.10
    return _clamp(score)


def _grade(total_score: float) -> str:
    if total_score >= 80:
        return "A"
    if total_score >= 65:
        return "B"
    if total_score >= 50:
        return "C"
    return "D"


def _clamp(value: float) -> float:
    return max(0.0, min(value, 1.0))
