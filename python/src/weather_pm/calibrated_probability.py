from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LeadTimeRmsePolicy:
    base_rmse: float = 0.0
    rmse_per_day: float = 0.0
    minimum_sigma: float = 0.6

    def sigma(self, dispersion: float | None, lead_time_hours: float | None = None) -> float:
        observed_sigma = max(float(dispersion or 0.0), 0.0)
        lead_days = max(float(lead_time_hours or 0.0), 0.0) / 24.0
        lead_rmse = self.base_rmse + (self.rmse_per_day * lead_days)
        widened = math.sqrt((observed_sigma * observed_sigma) + (lead_rmse * lead_rmse))
        return round(max(widened, self.minimum_sigma), 4)


@dataclass(frozen=True, slots=True)
class CalibratedProbabilityInput:
    forecast_value: float
    target_value: float | None = None
    threshold_direction: str | None = None
    range_low: float | None = None
    range_high: float | None = None
    dispersion: float | None = None
    lead_time_hours: float | None = None
    market_yes_price: float | None = None


@dataclass(frozen=True, slots=True)
class CalibratedProbabilityOutput:
    probability_yes: float
    sigma: float
    z_score: float
    edge: float | None = None


def gaussian_cdf(z_score: float) -> float:
    return 0.5 * (1.0 + math.erf(float(z_score) / math.sqrt(2.0)))


def threshold_probability(
    probability_input: CalibratedProbabilityInput,
    *,
    rmse_policy: LeadTimeRmsePolicy | None = None,
) -> CalibratedProbabilityOutput:
    if probability_input.target_value is None:
        raise ValueError("target_value is required for threshold probability")
    sigma = _sigma(probability_input, rmse_policy)
    direction = (probability_input.threshold_direction or "above").lower()
    if direction == "below":
        signed_distance = probability_input.target_value - probability_input.forecast_value
    else:
        signed_distance = probability_input.forecast_value - probability_input.target_value
    z_score = signed_distance / sigma
    probability_yes = gaussian_cdf(z_score)
    return _output(probability_yes=probability_yes, sigma=sigma, z_score=z_score, market_yes_price=probability_input.market_yes_price)


def exact_bin_probability(
    probability_input: CalibratedProbabilityInput,
    *,
    rmse_policy: LeadTimeRmsePolicy | None = None,
) -> CalibratedProbabilityOutput:
    if probability_input.range_low is None or probability_input.range_high is None:
        raise ValueError("range_low and range_high are required for exact-bin probability")
    sigma = _sigma(probability_input, rmse_policy)
    low = min(probability_input.range_low, probability_input.range_high)
    high = max(probability_input.range_low, probability_input.range_high)
    low_z = (low - probability_input.forecast_value) / sigma
    high_z = (high - probability_input.forecast_value) / sigma
    probability_yes = exact_bin_mass(low_z, high_z)
    midpoint = (low + high) / 2.0
    z_score = abs(probability_input.forecast_value - midpoint) / sigma
    return _output(probability_yes=probability_yes, sigma=sigma, z_score=z_score, market_yes_price=probability_input.market_yes_price)


def exact_bin_mass(low_z: float, high_z: float) -> float:
    return max(0.0, gaussian_cdf(high_z) - gaussian_cdf(low_z))


def _sigma(probability_input: CalibratedProbabilityInput, rmse_policy: LeadTimeRmsePolicy | None) -> float:
    policy = rmse_policy or LeadTimeRmsePolicy()
    return policy.sigma(probability_input.dispersion, probability_input.lead_time_hours)


def _output(*, probability_yes: float, sigma: float, z_score: float, market_yes_price: float | None) -> CalibratedProbabilityOutput:
    rounded_probability = round(probability_yes, 4)
    edge = None if market_yes_price is None else round(rounded_probability - float(market_yes_price), 4)
    return CalibratedProbabilityOutput(
        probability_yes=rounded_probability,
        sigma=round(sigma, 4),
        z_score=round(z_score, 4),
        edge=edge,
    )
