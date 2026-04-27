from __future__ import annotations

from typing import Any, Mapping

from prediction_core.strategies.contracts import StrategyMode, StrategyRunRequest
from prediction_core.strategies.weather_profile_strategies import build_weather_profile_strategies

from .strategy_profiles import list_strategy_profiles


def _number(value: Any, default: float | None = None) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _first_market(markets: list[Mapping[str, Any]]) -> Mapping[str, Any]:
    return markets[0] if markets else {}


def _probability_for_market(market: Mapping[str, Any], probabilities: Mapping[str, Any]) -> float | None:
    token_id = str(market.get("clob_token_id") or market.get("token_id") or "")
    if token_id and token_id in probabilities:
        return _number(probabilities[token_id])
    for value in probabilities.values():
        resolved = _number(value)
        if resolved is not None:
            return resolved
    return None


def _payload_for_profile(profile: Mapping[str, Any], *, markets: list[Mapping[str, Any]], probabilities: Mapping[str, Any], artifacts: Mapping[str, Any]) -> dict[str, Any]:
    market = _first_market(markets)
    profile_id = str(profile["id"])
    probability = _probability_for_market(market, probabilities)
    return {
        "market_id": str(market.get("id") or market.get("market_id") or f"weather-profile-{profile_id}"),
        "question": market.get("question"),
        "probability_yes": probability,
        "confidence": 0.0,
        "edge": None,
        "action": "watch_only",
        "satisfied_gates": [],
        "blockers": ["operator_review_required"],
        "source_references": [str(value) for value in artifacts.values() if value],
    }


def _signal_summary(signal: Any) -> dict[str, Any]:
    payload = signal.to_dict()
    features = payload.get("features") if isinstance(payload.get("features"), dict) else {}
    return {
        "profile_id": features.get("profile_id"),
        "strategy_id": payload["strategy_id"],
        "market_id": payload["market_id"],
        "mode": payload["mode"],
        "gate_status": payload["gate_status"],
        "side": payload["side"],
        "trading_action": payload["trading_action"],
        "missing_gates": list(features.get("missing_gates") or []),
        "blockers": list(features.get("blockers") or []),
    }


def build_runtime_weather_profile_summary(
    *,
    markets: list[Mapping[str, Any]] | None = None,
    probabilities: Mapping[str, Any] | None = None,
    runtime_result: Mapping[str, Any] | None = None,
    artifacts: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    markets = list(markets or [])
    probabilities = probabilities or {}
    runtime_result = runtime_result or {}
    artifacts = artifacts or {}
    profiles = list_strategy_profiles()
    payloads_by_profile = {str(profile["id"]): [_payload_for_profile(profile, markets=markets, probabilities=probabilities, artifacts=artifacts)] for profile in profiles}
    strategies = build_weather_profile_strategies(payloads_by_profile, mode=StrategyMode.PAPER_ONLY)
    signals = []
    errors: list[str] = []
    for strategy in strategies:
        result = strategy.run(StrategyRunRequest(market_id=str(_first_market(markets).get("id") or "weather-runtime-profiles")))
        errors.extend(result.errors)
        signals.extend(_signal_summary(signal) for signal in result.signals)

    execution = runtime_result.get("execution") if isinstance(runtime_result.get("execution"), Mapping) else {}
    orders_submitted = len(execution.get("orders_submitted") or []) if isinstance(execution, Mapping) else 0
    profile_ids = [str(profile["id"]) for profile in profiles]
    strategy_ids = [strategy.descriptor.strategy_id for strategy in strategies]
    return {
        "enabled": True,
        "auto_discovery": True,
        "paper_only": True,
        "trading_action": "none",
        "live_order_allowed": False,
        "profile_count": len(profile_ids),
        "strategy_count": len(strategy_ids),
        "signal_count": len(signals),
        "profile_ids": profile_ids,
        "strategy_ids": strategy_ids,
        "signals": signals,
        "errors": errors,
        "safety": {
            "paper_only": True,
            "no_real_orders": True,
            "live_order_allowed": False,
            "orders_submitted": orders_submitted,
        },
    }
