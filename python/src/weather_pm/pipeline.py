from __future__ import annotations

from weather_pm.decision import build_decision
from weather_pm.execution_features import build_execution_features
from weather_pm.forecast_client import build_forecast_bundle
from weather_pm.market_parser import parse_market_question
from weather_pm.models import MarketStructure
from weather_pm.neighbor_context import build_neighbor_context
from weather_pm.polymarket_client import get_fixture_market_by_id, list_fixture_weather_markets
from weather_pm.probability_model import build_model_output
from weather_pm.resolution_parser import parse_resolution_metadata
from weather_pm.scoring import score_market
from weather_pm.source_routing import build_resolution_source_route


def _default_forecast(structure: MarketStructure, resolution=None, *, live: bool = False):
    return build_forecast_bundle(structure, live=live, resolution=resolution)


def _default_model(structure: MarketStructure, forecast_bundle):
    return build_model_output(structure, forecast_bundle)


def score_market_from_question(
    question: str,
    yes_price: float,
    *,
    resolution_source: str | None = None,
    description: str | None = None,
    rules: str | None = None,
    market_data: dict[str, object] | None = None,
    max_impact_bps: float | None = None,
    live: bool = False,
    direct_client=None,
    infer_default_resolution: bool = False,
) -> dict[str, object]:
    structure = parse_market_question(question)
    if infer_default_resolution:
        resolution_source = resolution_source or _default_resolution_source(structure)
        description = description or _default_description(structure)
        rules = rules or _default_rules(structure)
    resolution = parse_resolution_metadata(
        resolution_source=resolution_source,
        description=description,
        rules=rules,
    )
    forecast_bundle = build_forecast_bundle(structure, live=live, resolution=resolution, direct_client=direct_client)
    model_output = _default_model(structure, forecast_bundle)
    neighbor_context = build_neighbor_context(structure, list_fixture_weather_markets())
    execution_market_data = dict(market_data or _default_execution_market_data())
    if max_impact_bps is not None:
        execution_market_data["max_impact_bps"] = max_impact_bps
    execution = build_execution_features(execution_market_data)
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
    model_payload = _model_payload_with_source(model_output, forecast_bundle)
    source_route = build_resolution_source_route(structure, resolution)
    return {
        "market": structure.to_dict(),
        "resolution": resolution.to_dict(),
        "source_route": source_route.to_dict(),
        "model": model_payload,
        "forecast": forecast_bundle.to_dict(),
        "edge": {
            "market_implied_yes_probability": round(float(yes_price), 2),
            "probability_edge": round(score.raw_edge, 2),
            "theoretical_yes_price": round(model_output.probability_yes, 2),
        },
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
    forecast_bundle = _default_forecast(structure, resolution)
    model_output = _default_model(structure, forecast_bundle)
    neighbor_context = build_neighbor_context(structure, list_fixture_weather_markets())
    execution = build_execution_features(raw_market)
    yes_price = float(raw_market.get("yes_price", 0.0))
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
    model_payload = _model_payload_with_source(model_output, forecast_bundle)
    source_route = build_resolution_source_route(structure, resolution)
    return {
        "market": structure.to_dict(),
        "resolution": resolution.to_dict(),
        "source_route": source_route.to_dict(),
        "model": model_payload,
        "forecast": forecast_bundle.to_dict(),
        "edge": {
            "market_implied_yes_probability": round(yes_price, 2),
            "probability_edge": round(score.raw_edge, 2),
            "theoretical_yes_price": round(model_output.probability_yes, 2),
        },
        "score": score.to_dict(),
        "decision": decision.to_dict(),
        "neighbors": neighbor_context.to_dict(),
        "execution": execution.to_dict(),
    }


def _model_payload_with_source(model_output, forecast_bundle) -> dict[str, object]:
    payload = model_output.to_dict()
    payload.update(
        {
            "source_provider": forecast_bundle.source_provider,
            "source_station_code": forecast_bundle.source_station_code,
            "source_url": forecast_bundle.source_url,
            "source_latency_tier": forecast_bundle.source_latency_tier,
        }
    )
    return payload


def _default_resolution_source(structure: MarketStructure) -> str:
    station_code = _station_code_for_city(structure.city)
    return f"Resolution source: Wunderground observed temperature for station {station_code}"


def _default_description(structure: MarketStructure) -> str:
    station_code = _station_code_for_city(structure.city)
    return f"This market resolves according to the official observed {structure.measurement_kind} temperature for {structure.city} station {station_code}."


def _default_rules(structure: MarketStructure) -> str:
    station_code = _station_code_for_city(structure.city)
    return f"Source: https://www.wunderground.com weather station {station_code}."


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
