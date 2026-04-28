from __future__ import annotations

from typing import Protocol

from weather_pm.calibrated_probability import CalibratedProbabilityInput, exact_bin_probability, threshold_probability
from weather_pm.models import ForecastBundle, MarketStructure, ModelOutput


class RmsePolicy(Protocol):
    def sigma(self, dispersion: float | None, lead_time_hours: float | None = None, **kwargs: object) -> float: ...


_MIN_PROBABILITY = 0.05
_MAX_PROBABILITY = 0.95


def build_model_output(
    structure: MarketStructure,
    forecast_bundle: ForecastBundle,
    *,
    rmse_policy: RmsePolicy | None = None,
) -> ModelOutput:
    calibrated = _build_calibrated_probability(structure, forecast_bundle, rmse_policy=rmse_policy)
    if calibrated is not None:
        probability_yes, method = calibrated
        confidence = _calibrated_confidence(forecast_bundle)
    elif structure.is_threshold:
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
        version="v1",
    )



def _build_calibrated_probability(
    structure: MarketStructure,
    forecast_bundle: ForecastBundle,
    *,
    rmse_policy: RmsePolicy | None = None,
) -> tuple[float, str] | None:
    if forecast_bundle.consensus_value is None or forecast_bundle.dispersion is None:
        return None
    calibrated_input = CalibratedProbabilityInput(
        forecast_value=forecast_bundle.consensus_value,
        target_value=structure.target_value,
        threshold_direction=structure.threshold_direction,
        range_low=structure.range_low,
        range_high=structure.range_high,
        dispersion=forecast_bundle.dispersion,
        lead_time_hours=forecast_bundle.lead_time_hours,
    )
    try:
        if structure.is_threshold and structure.target_value is not None:
            output = threshold_probability(calibrated_input, rmse_policy=_contextual_rmse_policy(structure, forecast_bundle, rmse_policy))
            return output.probability_yes, "calibrated_gaussian_threshold_v1"
        if structure.is_exact_bin and structure.range_low is not None and structure.range_high is not None:
            output = exact_bin_probability(calibrated_input, rmse_policy=_contextual_rmse_policy(structure, forecast_bundle, rmse_policy))
            return output.probability_yes, "calibrated_gaussian_bin_v1"
    except ValueError:
        return None
    return None


class _ContextualRmsePolicy:
    def __init__(self, policy: RmsePolicy, structure: MarketStructure, forecast_bundle: ForecastBundle) -> None:
        self._policy = policy
        self._structure = structure
        self._forecast_bundle = forecast_bundle

    def sigma(self, dispersion: float | None, lead_time_hours: float | None = None) -> float:
        return self._policy.sigma(
            dispersion,
            lead_time_hours,
            city=self._forecast_bundle.calibration_city or self._structure.city,
            station_code=self._forecast_bundle.calibration_station_code or self._forecast_bundle.source_station_code,
            measurement_kind=self._structure.measurement_kind,
        )


def _contextual_rmse_policy(
    structure: MarketStructure,
    forecast_bundle: ForecastBundle,
    rmse_policy: RmsePolicy | None,
) -> RmsePolicy | None:
    if rmse_policy is None:
        return None
    return _ContextualRmsePolicy(rmse_policy, structure, forecast_bundle)



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



def _calibrated_confidence(forecast_bundle: ForecastBundle) -> float:
    source_bonus = min(forecast_bundle.source_count, 3) * 0.02
    history_bonus = 0.04 if forecast_bundle.historical_station_available else 0.0
    dispersion_penalty = max((forecast_bundle.dispersion or 1.8) - 1.8, 0.0) * 0.03
    return 0.56 + source_bonus + history_bonus - dispersion_penalty



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
