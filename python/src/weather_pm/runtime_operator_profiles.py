from __future__ import annotations

from typing import Any, Mapping

from pathlib import Path

from prediction_core.decision.entry_policy import EntryPolicy
from prediction_core.strategies.contracts import StrategyMode, StrategyRunRequest, StrategySignal
from prediction_core.strategies.config_store import StrategyConfigStore, default_strategy_config_path
from prediction_core.strategies.paper_bridge import PaperBridgeContext, paper_decision_from_signal
from prediction_core.strategies.weather_profile_strategies import WeatherProfileStrategy

from .consensus_tracker import build_weather_consensus_tracker
from .event_surface import build_weather_event_surface
from .strategy_profiles import list_strategy_profiles, strategy_id_for_profile
from .threshold_watcher import build_threshold_watch_report


def _number(value: Any, default: float | None = None) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _first_market(markets: list[Mapping[str, Any]]) -> Mapping[str, Any]:
    return markets[0] if markets else {}


def _token_id_for_market(market: Mapping[str, Any]) -> str:
    token_ids = market.get("clobTokenIds") or market.get("clob_token_ids") or []
    if isinstance(token_ids, list) and token_ids:
        return str(token_ids[0])
    return str(market.get("clob_token_id") or market.get("token_id") or "")


def _probability_for_market(market: Mapping[str, Any], probabilities: Mapping[str, Any]) -> float | None:
    token_id = _token_id_for_market(market)
    if token_id and token_id in probabilities:
        return _number(probabilities[token_id])
    for value in probabilities.values():
        resolved = _number(value)
        if resolved is not None:
            return resolved
    return None


def _liquidity_for_market(market: Mapping[str, Any]) -> float:
    return float(_number(market.get("liquidity") or market.get("volume") or market.get("ask_depth_usd"), 0.0) or 0.0)


def _price_context(market: Mapping[str, Any], probability: float | None) -> dict[str, Any]:
    best_bid = _number(market.get("best_bid") or market.get("bestBid"))
    best_ask = _number(market.get("best_ask") or market.get("bestAsk"))
    market_price = best_ask if best_ask is not None else best_bid if best_bid is not None else probability
    if market_price is None:
        market_price = 0.5
    spread = max(0.0, float(best_ask - best_bid)) if best_bid is not None and best_ask is not None else 0.05
    return {"market_price": float(market_price), "best_bid": best_bid, "best_ask": best_ask, "spread": round(spread, 6)}


def _feature_reports(markets: list[Mapping[str, Any]]) -> dict[str, Any]:
    normalized = []
    for market in markets:
        yes_price = _number(market.get("yes_price") or market.get("best_ask") or market.get("bestAsk"))
        normalized.append({**dict(market), "yes_price": yes_price})
    reports: dict[str, Any] = {}
    try:
        reports["event_surface"] = build_weather_event_surface(normalized)
    except Exception as exc:
        reports["event_surface_error"] = repr(exc)
    try:
        reports["threshold_watch"] = build_threshold_watch_report({"markets": normalized})
    except Exception as exc:
        reports["threshold_watch_error"] = repr(exc)
    try:
        reports["consensus"] = build_weather_consensus_tracker([
            {"question": market.get("question"), "side": "YES", "handle": "runtime_model", "notional": market.get("liquidity") or 0}
            for market in normalized
        ])
    except Exception as exc:
        reports["consensus_error"] = repr(exc)
    return reports


def _profile_payload_features(profile_id: str, market: Mapping[str, Any], probability: float | None, price: Mapping[str, Any], reports: Mapping[str, Any]) -> dict[str, Any]:
    question = str(market.get("question") or "")
    liquidity = _liquidity_for_market(market)
    market_price = float(price["market_price"])
    edge = round(float(probability) - market_price, 4) if probability is not None else None
    base = {
        "question": question,
        "token_id": _token_id_for_market(market),
        "probability_yes": probability,
        "market_price": market_price,
        "best_bid": price.get("best_bid"),
        "best_ask": price.get("best_ask"),
        "spread": price.get("spread"),
        "liquidity_usd": liquidity,
        "edge": edge,
    }
    if profile_id == "surface_grid_trader":
        return {**base, "feature_family": "event_surface", "surface": reports.get("event_surface") or {"probability_yes": probability, "market_price": market_price, "edge": edge}}
    if profile_id == "exact_bin_anomaly_hunter":
        surface = reports.get("event_surface") if isinstance(reports.get("event_surface"), Mapping) else {}
        events = surface.get("events") if isinstance(surface.get("events"), list) else []
        inconsistencies = [item for event in events if isinstance(event, Mapping) for item in event.get("inconsistencies", []) if isinstance(item, Mapping)]
        return {**base, "feature_family": "surface_inconsistency", "anomaly": {"edge": edge, "question": question, "inconsistencies": inconsistencies}}
    if profile_id == "threshold_resolution_harvester":
        return {**base, "feature_family": "threshold_watcher", "threshold_watch": reports.get("threshold_watch") or {}, "resolution": {"source_status": market.get("resolution_source_status") or "unknown"}}
    if profile_id == "profitable_consensus_radar":
        return {**base, "feature_family": "consensus_tracker", "consensus": reports.get("consensus") or {"probability_yes": probability, "market_price": market_price}}
    if profile_id == "conviction_signal_follower":
        return {**base, "feature_family": "strategy_shortlist", "conviction": {"score": 0.65 if edge is not None and edge > 0 else 0.0}}
    if profile_id == "macro_weather_event_trader":
        return {**base, "feature_family": "macro_weather_event", "macro": {"weather_keywords": [word for word in ("rain", "temperature", "weather", "heat", "snow") if word in question.lower()]}}
    return {**base, "feature_family": "generic_weather_profile"}


def _runtime_gate_inputs(features: Mapping[str, Any], probability: float | None) -> dict[str, bool]:
    edge = _number(features.get("edge"), 0.0) or 0.0
    spread = _number(features.get("spread"), 1.0) or 1.0
    liquidity = _number(features.get("liquidity_usd"), 0.0) or 0.0
    has_probability = probability is not None
    has_price = features.get("market_price") is not None
    has_source = has_probability
    has_edge = has_probability and edge > 0.0
    has_liquidity = liquidity > 0.0
    strict_limit_ok = has_price and spread <= 0.05
    macro_identified = bool((features.get("macro") or {}).get("weather_keywords")) if isinstance(features.get("macro"), Mapping) else has_probability
    return {
        "surface_inconsistency_present": has_edge,
        "source_confirmed": has_source,
        "edge_survives_fill": has_edge and strict_limit_ok,
        "strict_limit_not_crossed": strict_limit_ok,
        "exact_bin_mass_anomaly": has_edge,
        "neighbor_bins_consistent": has_probability,
        "near_resolution_window": has_probability,
        "source_margin_favors_side": has_edge,
        "latest_source_available": has_source,
        "multi_handle_consensus": has_probability,
        "independent_source_confirms": has_source,
        "not_wallet_copy_only": has_probability,
        "conviction_archetype_match": has_edge,
        "min_edge_met": has_edge,
        "macro_event_identified": macro_identified,
        "forecast_source_supported": has_source,
        "rules_clear": has_probability,
        "liquidity_sufficient": has_liquidity,
    }


def _satisfied_gates_for_payload(profile: Mapping[str, Any], features: Mapping[str, Any], probability: float | None) -> list[str]:
    gates = _runtime_gate_inputs(features, probability)
    return [str(gate) for gate in profile.get("entry_gates") or [] if gates.get(str(gate), False)]


def _payload_for_profile(profile: Mapping[str, Any], *, markets: list[Mapping[str, Any]], probabilities: Mapping[str, Any], artifacts: Mapping[str, Any], reports: Mapping[str, Any]) -> dict[str, Any]:
    market = _first_market(markets)
    profile_id = str(profile["id"])
    probability = _probability_for_market(market, probabilities)
    price = _price_context(market, probability)
    features = _profile_payload_features(profile_id, market, probability, price, reports)
    blockers = [] if probability is not None else ["missing_probability"]
    if float(features.get("liquidity_usd") or 0.0) <= 0.0:
        blockers.append("missing_liquidity")
    return {
        "market_id": str(market.get("id") or market.get("market_id") or f"weather-profile-{profile_id}"),
        "question": market.get("question"),
        "token_id": features.get("token_id"),
        "probability_yes": probability,
        "confidence": 0.65 if probability is not None else 0.0,
        "edge": features.get("edge"),
        "action": "paper_probe" if probability is not None and not blockers else "watch_only",
        "satisfied_gates": _satisfied_gates_for_payload(profile, features, probability),
        "blockers": blockers,
        "source_references": [str(value) for value in artifacts.values() if value],
        "score": features,
    }


def _configured_profile_ids(profiles: list[Mapping[str, Any]], config_path: Path | None) -> tuple[list[str], dict[str, Any], bool]:
    path = config_path or default_strategy_config_path()
    profile_ids = [str(profile["id"]) for profile in profiles]
    if not path.exists():
        return profile_ids, {}, True
    store = StrategyConfigStore(path)
    configs = store.list_configs()["strategies"]
    enabled_ids = []
    config_by_strategy_id = {}
    for profile_id in profile_ids:
        strategy_id = strategy_id_for_profile(profile_id)
        config = configs.get(strategy_id, {})
        if not config.get("enabled", False):
            continue
        enabled_ids.append(profile_id)
        config_by_strategy_id[strategy_id] = config
    return enabled_ids, config_by_strategy_id, False


def _mode_for_profile(profile_id: str, config_by_strategy_id: Mapping[str, Any]) -> StrategyMode:
    config = config_by_strategy_id.get(strategy_id_for_profile(profile_id), {})
    mode = str(config.get("mode") or StrategyMode.PAPER_ONLY.value)
    if mode == StrategyMode.LIVE_ALLOWED.value:
        return StrategyMode.PAPER_ONLY
    return StrategyMode(mode)


def _signal_summary(signal: Any) -> dict[str, Any]:
    payload = signal.to_dict()
    features = payload.get("features") if isinstance(payload.get("features"), dict) else {}
    source = payload.get("source") if isinstance(payload.get("source"), dict) else {}
    return {
        "profile_id": features.get("profile_id"),
        "strategy_id": payload["strategy_id"],
        "market_id": payload["market_id"],
        "token_id": features.get("token_id"),
        "mode": payload["mode"],
        "gate_status": payload["gate_status"],
        "side": payload["side"],
        "probability": payload.get("probability"),
        "market_price": features.get("market_price"),
        "edge": payload.get("expected_move"),
        "confidence": payload.get("confidence"),
        "trading_action": payload["trading_action"],
        "missing_gates": list(features.get("missing_gates") or []),
        "blockers": list(features.get("blockers") or []),
        "feature_family": features.get("feature_family"),
        "source_references": list(source.get("references") or []),
    }


def _paper_context_for_signal(signal: StrategySignal, payload_by_market: Mapping[str, Mapping[str, Any]]) -> PaperBridgeContext:
    payload = payload_by_market.get(signal.market_id, {})
    score = payload.get("score") if isinstance(payload.get("score"), Mapping) else {}
    features = signal.features if isinstance(signal.features, Mapping) else {}
    risk_caps = features.get("risk_caps") if isinstance(features.get("risk_caps"), Mapping) else {}
    market_price = _number(score.get("market_price"), signal.probability if signal.probability is not None else 0.5)
    spread = _number(score.get("spread"), 0.05)
    depth_usd = _number(score.get("liquidity_usd"), 100.0)
    policy = EntryPolicy(
        name="weather_profile_paper",
        q_min=0.001,
        q_max=0.999,
        min_edge=float(_number(risk_caps.get("min_edge"), 0.02) or 0.02),
        min_confidence=0.6,
        max_spread=0.05,
        min_depth_usd=100.0,
        max_position_usd=float(_number(risk_caps.get("max_order_usdc"), 10.0) or 10.0),
    )
    return PaperBridgeContext(market_price=float(market_price or 0.5), spread=float(spread or 0.05), depth_usd=float(depth_usd or 0.0), policy=policy)


def _decision_summary(signal: StrategySignal, payload_by_market: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    decision = paper_decision_from_signal(signal, _paper_context_for_signal(signal, payload_by_market)).to_dict()
    signal_payload = signal.to_dict()
    features = signal_payload.get("features") if isinstance(signal_payload.get("features"), dict) else {}
    blockers = list(features.get("blockers") or []) + list(decision.get("blocked_by") or [])
    action = str(decision.get("action") or "skip")
    return {
        "strategy_id": signal.strategy_id,
        "profile_id": features.get("profile_id"),
        "market_id": signal.market_id,
        "token_id": features.get("token_id"),
        "mode": signal_payload["mode"],
        "decision": "enter" if decision.get("enter") else "skip",
        "decision_status": action,
        "side": decision.get("side"),
        "gate_status": signal.gate_status,
        "skip_reason": ",".join(blockers),
        "blockers": blockers,
        "edge": decision.get("edge_net_all_in"),
        "gross_edge": decision.get("edge_gross"),
        "confidence": decision.get("confidence"),
        "market_price": decision.get("market_price"),
        "model_probability": decision.get("model_probability"),
        "requested_spend_usdc": decision.get("size_hint_usd"),
        "capped_spend_usdc": decision.get("size_hint_usd"),
        "risk_ok": not blockers,
        "paper_only": True,
        "live_order_allowed": False,
        "raw_decision": decision,
    }


def build_runtime_weather_profile_summary(
    *,
    markets: list[Mapping[str, Any]] | None = None,
    probabilities: Mapping[str, Any] | None = None,
    runtime_result: Mapping[str, Any] | None = None,
    artifacts: Mapping[str, Any] | None = None,
    config_path: Path | None = None,
) -> dict[str, Any]:
    markets = list(markets or [])
    probabilities = probabilities or {}
    runtime_result = runtime_result or {}
    artifacts = artifacts or {}
    profiles = list_strategy_profiles()
    feature_reports = _feature_reports(markets)
    enabled_profile_ids, config_by_strategy_id, default_enabled_all = _configured_profile_ids(profiles, config_path)
    profiles_by_id = {str(profile["id"]): profile for profile in profiles}
    payloads_by_profile = {
        profile_id: [_payload_for_profile(profiles_by_id[profile_id], markets=markets, probabilities=probabilities, artifacts=artifacts, reports=feature_reports)]
        for profile_id in enabled_profile_ids
    }
    strategies = [
        WeatherProfileStrategy(profile_id, payloads=payloads_by_profile[profile_id], mode=_mode_for_profile(profile_id, config_by_strategy_id))
        for profile_id in enabled_profile_ids
    ]
    raw_signals: list[StrategySignal] = []
    errors: list[str] = []
    for strategy in strategies:
        result = strategy.run(StrategyRunRequest(market_id=str(_first_market(markets).get("id") or "weather-runtime-profiles")))
        errors.extend(result.errors)
        raw_signals.extend(result.signals)
    payload_by_market = {
        str(payload.get("market_id")): payload
        for payloads in payloads_by_profile.values()
        for payload in payloads
    }
    signals = [_signal_summary(signal) for signal in raw_signals]
    decisions = [_decision_summary(signal, payload_by_market) for signal in raw_signals]

    execution = runtime_result.get("execution") if isinstance(runtime_result.get("execution"), Mapping) else {}
    orders_submitted = len(execution.get("orders_submitted") or []) if isinstance(execution, Mapping) else 0
    profile_ids = enabled_profile_ids
    strategy_ids = [strategy.descriptor.strategy_id for strategy in strategies]
    return {
        "enabled": True,
        "auto_discovery": True,
        "default_enabled_all": default_enabled_all,
        "config_path": str(config_path or default_strategy_config_path()),
        "paper_only": True,
        "trading_action": "none",
        "live_order_allowed": False,
        "available_profile_count": len(profiles),
        "profile_count": len(profile_ids),
        "strategy_count": len(strategy_ids),
        "signal_count": len(signals),
        "decision_count": len(decisions),
        "enter_count": sum(1 for decision in decisions if decision.get("decision") == "enter"),
        "skip_count": sum(1 for decision in decisions if decision.get("decision") == "skip"),
        "profile_ids": profile_ids,
        "strategy_ids": strategy_ids,
        "feature_reports": feature_reports,
        "payloads_by_profile": payloads_by_profile,
        "signals": signals,
        "decisions": decisions,
        "errors": errors,
        "safety": {
            "paper_only": True,
            "no_real_orders": True,
            "live_order_allowed": False,
            "orders_submitted": orders_submitted,
        },
    }
