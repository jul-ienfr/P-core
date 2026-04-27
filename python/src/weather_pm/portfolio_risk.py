from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class PortfolioRiskConfig:
    total_paper_cap_usdc: float = 100.0
    total_live_cap_usdc: float = 0.0
    city_date_cap_usdc: float = 25.0
    station_source_cap_usdc: float = 25.0
    archetype_cap_usdc: float = 30.0
    side_cap_usdc: float = 40.0
    correlated_surface_cap_usdc: float = 20.0
    min_paper_size_usdc: float = 1.0
    micro_paper_size_usdc: float = 1.0
    medium_paper_size_usdc: float = 5.0
    robust_paper_size_usdc: float = 10.0


def classify_stress_robustness(
    candidate: dict[str, Any],
    *,
    forecast_biases: Iterable[float] = (-1.0, 0.0, 1.0),
    sigma_multipliers: Iterable[float] = (1.0, 1.5, 2.0),
    error_widths: Iterable[float] | None = None,
) -> dict[str, Any]:
    """Stress a weather candidate against bias and error-width scenarios.

    The classifier is intentionally conservative: a candidate is robust only when
    every stressed scenario remains on the candidate side with meaningful margin.
    """
    side = str(candidate.get("candidate_side") or candidate.get("side") or "YES").upper()
    forecast = _num(candidate.get("forecast_value", candidate.get("model_value")))
    threshold = _num(candidate.get("threshold"))
    edge = _num(candidate.get("probability_edge")) or 0.0
    sigma = abs(_num(candidate.get("sigma")) or _num(candidate.get("forecast_sigma")) or 1.0)
    base_error = abs(_num(candidate.get("error_width")) or _num(candidate.get("forecast_error_width")) or sigma)

    if forecast is None or threshold is None:
        label = "fragile" if edge > 0 else "avoid"
        return {
            "label": label,
            "min_stressed_margin": None,
            "scenario_count": 0,
            "failed_scenarios": 0,
            "reason": "missing_forecast_or_threshold",
        }

    widths = list(error_widths) if error_widths is not None else [0.0, base_error]
    scenario_margins: list[float] = []
    failed = 0
    for bias in forecast_biases:
        for multiplier in sigma_multipliers:
            for width in widths:
                stressed_value = forecast + float(bias) - (sigma * (float(multiplier) - 1.0))
                raw_margin = stressed_value - threshold
                side_margin = raw_margin if side == "YES" else -raw_margin
                conservative_margin = side_margin - abs(float(width))
                scenario_margins.append(round(conservative_margin, 6))
                if conservative_margin <= 0:
                    failed += 1

    min_margin = min(scenario_margins) if scenario_margins else None
    base_side_margin = (forecast - threshold) if side == "YES" else (threshold - forecast)
    if edge <= 0 or base_side_margin < 0:
        label = "avoid"
    elif failed == 0 and (min_margin or 0.0) >= 0.5 and edge >= 0.12:
        label = "robust"
    elif base_side_margin >= 1.0 and edge >= 0.07:
        label = "medium"
    else:
        label = "fragile"

    return {
        "label": label,
        "min_stressed_margin": round(min_margin, 6) if min_margin is not None else None,
        "scenario_count": len(scenario_margins),
        "failed_scenarios": failed,
        "scenario_margins": scenario_margins,
        "reason": _stress_reason(label, failed, min_margin, edge),
    }


def enforce_portfolio_caps(
    candidate: dict[str, Any],
    *,
    requested_size_usdc: float,
    existing_exposures: Iterable[dict[str, Any]] = (),
    config: PortfolioRiskConfig | None = None,
    mode: str = "paper",
) -> dict[str, Any]:
    config = config or PortfolioRiskConfig()
    requested = max(float(requested_size_usdc), 0.0)
    mode_key = "total_live" if mode == "live" else "total_paper"
    capacities = {
        mode_key: _cap_for(mode_key, config) - _sum_matching(existing_exposures, lambda e: str(e.get("mode") or "paper") == mode),
        "city_date": config.city_date_cap_usdc - _sum_matching(existing_exposures, lambda e: _city_date_key(e) == _city_date_key(candidate)),
        "station_source": config.station_source_cap_usdc - _sum_matching(existing_exposures, lambda e: _station_key(e) == _station_key(candidate)),
        "archetype": config.archetype_cap_usdc - _sum_matching(existing_exposures, lambda e: _archetype(e) == _archetype(candidate)),
        "side": config.side_cap_usdc - _sum_matching(existing_exposures, lambda e: _side(e) == _side(candidate)),
        "correlated_surface": config.correlated_surface_cap_usdc - _sum_matching(existing_exposures, lambda e: _correlated_key(e) == _correlated_key(candidate)),
    }
    remaining = {key: round(max(value, 0.0), 6) for key, value in capacities.items()}
    min_capacity = min(remaining.values()) if remaining else requested
    approved = round(min(requested, min_capacity), 6)
    if approved < config.min_paper_size_usdc and requested >= config.min_paper_size_usdc:
        approved = 0.0
    binding = sorted(key for key, capacity in remaining.items() if capacity <= approved + 1e-9)
    status = "approved"
    if approved <= 0.0 and requested > 0:
        status = "blocked"
    elif approved < requested:
        status = "capped"
    return {
        "requested_size_usdc": round(requested, 6),
        "approved_size_usdc": approved,
        "cap_status": status,
        "binding_caps": binding,
        "remaining_capacity_usdc": remaining,
        "mode": mode,
        "live_order_allowed": False,
    }


def size_candidate_for_portfolio(
    candidate: dict[str, Any],
    *,
    existing_exposures: Iterable[dict[str, Any]] = (),
    config: PortfolioRiskConfig | None = None,
) -> dict[str, Any]:
    config = config or PortfolioRiskConfig()
    stress = classify_stress_robustness(candidate)
    label = _label_with_source_penalty(candidate, stress["label"])

    if label == "avoid":
        requested = 0.0
        recommendation = "avoid"
    elif label == "fragile":
        requested = config.micro_paper_size_usdc
        recommendation = "paper_micro_only"
    elif label == "medium":
        requested = config.medium_paper_size_usdc
        recommendation = "paper_small_capped"
    else:
        requested = config.robust_paper_size_usdc
        recommendation = "paper_larger_capped"

    caps = enforce_portfolio_caps(candidate, requested_size_usdc=requested, existing_exposures=existing_exposures, config=config, mode="paper")
    if caps["cap_status"] == "blocked" and recommendation != "avoid":
        recommendation = "blocked_by_portfolio_caps"
    return {
        **caps,
        "robustness_label": label,
        "stress_test": stress,
        "recommendation": recommendation,
        "paper_only": True,
        "live_order_allowed": False,
    }


def apply_portfolio_risk_to_candidates(
    candidates: Iterable[dict[str, Any]],
    *,
    existing_exposures: Iterable[dict[str, Any]] = (),
    config: PortfolioRiskConfig | None = None,
) -> list[dict[str, Any]]:
    config = config or PortfolioRiskConfig()
    rolling = [dict(item) for item in existing_exposures if isinstance(item, dict)]
    result: list[dict[str, Any]] = []
    for raw in candidates:
        candidate = dict(raw)
        risk = size_candidate_for_portfolio(candidate, existing_exposures=rolling, config=config)
        candidate["portfolio_risk"] = risk
        candidate["paper_notional_usdc"] = risk["approved_size_usdc"]
        candidate["paper_size_label"] = _paper_size_label(risk)
        candidate["live_order_allowed"] = False
        if risk["approved_size_usdc"] > 0:
            rolling.append({**candidate, "mode": "paper", "notional_usdc": risk["approved_size_usdc"]})
        result.append(candidate)
    return result


def _label_with_source_penalty(candidate: dict[str, Any], label: str) -> str:
    edge_source = str(candidate.get("edge_source") or candidate.get("raw_edge_reason") or "").lower()
    source_confirmed = bool(candidate.get("source_direct")) or str(candidate.get("source_status") or "") in {"source_confirmed", "source_confirmed_fixture"}
    if "crude_proxy" in edge_source or "long_tail" in edge_source:
        return "fragile" if (_num(candidate.get("probability_edge")) or 0.0) > 0 else "avoid"
    if not source_confirmed and label == "robust":
        return "medium"
    if not source_confirmed and label == "medium":
        return "fragile"
    return label


def _stress_reason(label: str, failed: int, min_margin: float | None, edge: float) -> str:
    if label == "avoid":
        return "negative_or_breaks_under_stress"
    if label == "robust":
        return "all_bias_sigma_width_scenarios_preserve_edge"
    if label == "medium":
        return "some_stress_scenarios_preserve_edge"
    return "fragile_under_bias_or_error_width"


def _paper_size_label(risk: dict[str, Any]) -> str:
    recommendation = risk.get("recommendation")
    if recommendation == "paper_micro_only":
        return "micro"
    if recommendation == "paper_larger_capped":
        return "capped_large" if risk.get("cap_status") == "capped" else "large"
    if recommendation == "paper_small_capped":
        return "small"
    return "none"


def _cap_for(key: str, config: PortfolioRiskConfig) -> float:
    return config.total_live_cap_usdc if key == "total_live" else config.total_paper_cap_usdc


def _sum_matching(exposures: Iterable[dict[str, Any]], predicate) -> float:
    total = 0.0
    for exposure in exposures:
        if not isinstance(exposure, dict) or not predicate(exposure):
            continue
        total += _num(exposure.get("notional_usdc", exposure.get("filled_usdc", exposure.get("paper_notional_usdc")))) or 0.0
    return total


def _city_date_key(value: dict[str, Any]) -> tuple[str, str]:
    return (str(value.get("city") or ""), str(value.get("date") or ""))


def _station_key(value: dict[str, Any]) -> tuple[str, str]:
    return (str(value.get("source_provider") or value.get("provider") or ""), str(value.get("source_station_code") or value.get("station") or ""))


def _archetype(value: dict[str, Any]) -> str:
    return str(value.get("primary_archetype") or value.get("archetype") or "")


def _side(value: dict[str, Any]) -> str:
    return str(value.get("candidate_side") or value.get("side") or "YES").upper()


def _correlated_key(value: dict[str, Any]) -> str:
    explicit = value.get("correlated_surface_id") or value.get("surface_id")
    if explicit:
        return str(explicit)
    return "|".join([*_city_date_key(value), *_station_key(value)])


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
