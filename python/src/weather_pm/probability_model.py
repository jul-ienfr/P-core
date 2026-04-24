from __future__ import annotations

from weather_pm.models import ForecastBundle, MarketStructure, ModelOutput


_MIN_PROBABILITY = 0.05
_MAX_PROBABILITY = 0.95


def build_model_output(structure: MarketStructure, forecast_bundle: ForecastBundle) -> ModelOutput:
    if structure.is_threshold:
        probability_yes = _threshold_probability(structure, forecast_bundle)
        confidence = _threshold_confidence(forecast_bundle)
        method = "calibrated_threshold_v1"
    else:
        probability_yes = _exact_bin_probability(structure, forecast_bundle)
        confidence = _exact_bin_confidence(forecast_bundle)
        method = "calibrated_bin_v1"

    return ModelOutput(
        probability_yes=round(_clamp(probability_yes, _MIN_PROBABILITY, _MAX_PROBABILITY), 2),
        confidence=round(_clamp(confidence, _MIN_PROBABILITY, _MAX_PROBABILITY), 2),
        method=method,
    )



def _threshold_probability(structure: MarketStructure, forecast_bundle: ForecastBundle) -> float:
    if structure.target_value is None or forecast_bundle.consensus_value is None:
        return 0.50

    signed_diff = forecast_bundle.consensus_value - structure.target_value
    if structure.threshold_direction == "below":
        signed_diff = -signed_diff

    bounded_diff = _clamp(signed_diff, -1.0, 1.0)
    return 0.50 + (bounded_diff * 0.35)



def _exact_bin_probability(structure: MarketStructure, forecast_bundle: ForecastBundle) -> float:
    if structure.range_low is None or structure.range_high is None:
        return 0.22
    if forecast_bundle.consensus_value is None:
        return 0.22

    width = max(structure.range_high - structure.range_low, 0.0)
    sigma = max(forecast_bundle.dispersion or 1.8, 0.8)
    midpoint = (structure.range_low + structure.range_high) / 2.0
    distance = abs(forecast_bundle.consensus_value - midpoint)

    base_mass = width / (sigma * 2.4) if width > 0 else 1.0 / (sigma * 4.4)
    distance_penalty = max(0.0, 1.0 - min(distance / max(sigma, 1.0), 1.0) * 0.55)
    return max(0.08, min(base_mass * distance_penalty, 0.40))



def _threshold_confidence(forecast_bundle: ForecastBundle) -> float:
    source_bonus = min(forecast_bundle.source_count, 3) * 0.02
    history_bonus = 0.04 if forecast_bundle.historical_station_available else 0.0
    dispersion_bonus = max(0.0, 2.0 - (forecast_bundle.dispersion or 2.0)) * 0.025
    return 0.56 + source_bonus + history_bonus + dispersion_bonus



def _exact_bin_confidence(forecast_bundle: ForecastBundle) -> float:
    source_bonus = min(forecast_bundle.source_count, 3) * 0.02
    history_bonus = 0.04 if forecast_bundle.historical_station_available else 0.0
    dispersion_penalty = max((forecast_bundle.dispersion or 1.8) - 1.8, 0.0) * 0.03
    return 0.46 + source_bonus + history_bonus - dispersion_penalty



def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(value, upper))
