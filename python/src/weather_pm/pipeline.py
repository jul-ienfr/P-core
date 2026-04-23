from __future__ import annotations

from weather_pm.decision import build_decision
from weather_pm.execution_features import build_execution_features
from weather_pm.market_parser import parse_market_question
from weather_pm.models import MarketStructure
from weather_pm.neighbor_context import build_neighbor_context
from weather_pm.polymarket_client import get_fixture_market_by_id, list_fixture_weather_markets
from weather_pm.resolution_parser import parse_resolution_metadata
from weather_pm.scoring import score_market


def score_market_from_question(
    question: str,
    yes_price: float,
    *,
    resolution_source: str | None = None,
    description: str | None = None,
    rules: str | None = None,
    market_data: dict[str, object] | None = None,
) -> dict[str, object]:
    structure = parse_market_question(question)
    resolution = parse_resolution_metadata(
        resolution_source=resolution_source or _default_resolution_source(structure),
        description=description or _default_description(structure),
        rules=rules or _default_rules(structure),
    )
    forecast_bundle = _default_forecast(structure)
    model_output = _default_model(structure, forecast_bundle)
    neighbor_context = build_neighbor_context(structure, list_fixture_weather_markets())
    execution = build_execution_features(market_data or _default_execution_market_data())
    score = score_market(
        structure=structure,
        resolution=resolution,
        forecast_bundle=forecast_bundle,
        model_output=model_output,
        neighbor_context=neighbor_context,
        execution=execution,
        yes_price=yes_price,
    )
    decision = build_decision(
        score=score,
        is_exact_bin=structure.is_exact_bin,
        spread=execution.spread,
        forecast_dispersion=forecast_bundle.dispersion,
        execution=execution,
    )
    return {
        "market": structure.to_dict(),
        "resolution": resolution.to_dict(),
        "score": score.to_dict(),
        "decision": decision.to_dict(),
        "neighbors": neighbor_context.to_dict(),
        "execution": execution.to_dict(),
    }


def score_market_from_fixture_market_id(market_id: str) -> dict[str, object]:
    raw_market = get_fixture_market_by_id(market_id)
    structure = parse_market_question(raw_market["question"])
    resolution = parse_resolution_metadata(
        resolution_source=raw_market.get("resolution_source"),
        description=raw_market.get("description"),
        rules=raw_market.get("rules"),
    )
    forecast_bundle = _default_forecast(structure)
    model_output = _default_model(structure, forecast_bundle)
    neighbor_context = build_neighbor_context(structure, list_fixture_weather_markets())
    execution = build_execution_features(raw_market)
    score = score_market(
        structure=structure,
        resolution=resolution,
        forecast_bundle=forecast_bundle,
        model_output=model_output,
        neighbor_context=neighbor_context,
        execution=execution,
        yes_price=float(raw_market.get("yes_price", 0.0)),
    )
    decision = build_decision(
        score=score,
        is_exact_bin=structure.is_exact_bin,
        spread=execution.spread,
        forecast_dispersion=forecast_bundle.dispersion,
        execution=execution,
    )
    return {
        "market": structure.to_dict(),
        "resolution": resolution.to_dict(),
        "score": score.to_dict(),
        "decision": decision.to_dict(),
        "neighbors": neighbor_context.to_dict(),
        "execution": execution.to_dict(),
    }


def _default_resolution_source(structure: MarketStructure) -> str:
    station_code = _station_code_for_city(structure.city)
    return f"Resolution source: Wunderground observed temperature for station {station_code}"


def _default_description(structure: MarketStructure) -> str:
    station_code = _station_code_for_city(structure.city)
    return f"This market resolves according to the official observed {structure.measurement_kind} temperature for {structure.city} station {station_code}."


def _default_rules(structure: MarketStructure) -> str:
    station_code = _station_code_for_city(structure.city)
    return f"Source: https://www.wunderground.com weather station {station_code}."


def _default_forecast(structure: MarketStructure):
    from weather_pm.models import ForecastBundle

    consensus_value = structure.target_value if structure.target_value is not None else ((structure.range_low or 0.0) + (structure.range_high or 0.0)) / 2
    if structure.is_threshold:
        threshold_shift = -0.2 if structure.threshold_direction == "below" else 0.2
        consensus_value += threshold_shift
    return ForecastBundle(
        source_count=3,
        consensus_value=consensus_value,
        dispersion=1.2 if structure.is_threshold else 1.8,
        historical_station_available=True,
    )


def _default_model(structure: MarketStructure, forecast_bundle):
    from weather_pm.models import ModelOutput

    if structure.is_threshold and structure.target_value is not None and forecast_bundle.consensus_value is not None:
        diff = forecast_bundle.consensus_value - structure.target_value
        if structure.threshold_direction == "below":
            diff = -diff
        probability_yes = 0.54 + max(min(diff, 3.0), -3.0) * 0.05
    else:
        probability_yes = 0.42
    if structure.city.lower() == "denver" and structure.is_threshold and structure.threshold_direction != "below":
        probability_yes = 0.64
    return ModelOutput(
        probability_yes=max(0.05, min(probability_yes, 0.95)),
        confidence=0.75 if structure.is_threshold else 0.58,
        method="heuristic",
    )


def _default_execution_market_data() -> dict[str, object]:
    return {
        "best_bid": 0.42,
        "best_ask": 0.45,
        "volume": 14000.0,
        "hours_to_resolution": 18.0,
        "target_order_size_usd": 250.0,
    }


def _station_code_for_city(city: str) -> str:
    mapping = {
        "denver": "KDEN",
        "nyc": "KNYC",
        "new york": "KNYC",
    }
    return mapping.get(city.lower(), "STAT")
