from __future__ import annotations

import argparse
import json
from typing import Sequence

from weather_pm.strategy_profiles import operator_profile_matrix

from .config import StrategyConfig
from .measurement import group_signals_for_read_model
from .panoptique_shadow_flow import PanoptiqueShadowFlowStrategy
from .registry import StrategyRegistry
from .weather_baseline import WeatherBaselineStrategy
from .weather_profile_strategies import build_weather_profile_strategies
from .contracts import StrategyRunRequest


WEATHER_FIXTURE = {
    "market_id": "fixture-weather",
    "score": {"probability_yes": 0.62, "confidence": 0.74, "edge": 0.04},
    "decision": {"action": "skip", "execution_caveats": ["fixture only"], "gate_status": "fixture"},
    "source_references": ["fixture://weather"],
}

PANOPTIQUE_FIXTURE = {
    "market_id": "fixture-panoptique",
    "predicted_crowd_direction": "up",
    "confidence": 0.68,
    "expected_crowd_move": 0.03,
    "archetype": "fixture_flow",
    "window": "15m",
    "observed_count": 3,
    "matched_count": 0,
    "status": "not_enough_data",
}

WEATHER_PROFILE_FIXTURES = {
    "surface_grid_trader": {
        "market_id": "fixture-surface-grid",
        "probability_yes": 0.58,
        "confidence": 0.64,
        "edge": 0.04,
        "action": "paper_probe",
        "satisfied_gates": ["surface_inconsistency_present", "source_confirmed", "edge_survives_fill", "strict_limit_not_crossed"],
        "blockers": [],
        "source_references": ["fixture://surface-grid"],
        "surface_inconsistency_count": 2,
    },
    "exact_bin_anomaly_hunter": {
        "market_id": "fixture-exact-bin",
        "probability_yes": 0.56,
        "confidence": 0.62,
        "edge": 0.05,
        "action": "paper_probe",
        "satisfied_gates": ["exact_bin_mass_anomaly", "source_confirmed", "neighbor_bins_consistent", "strict_limit_not_crossed"],
        "blockers": [],
        "source_references": ["fixture://exact-bin"],
        "exact_bin_price_mass": 1.16,
    },
    "threshold_resolution_harvester": {
        "market_id": "fixture-threshold-resolution",
        "probability_yes": 0.61,
        "confidence": 0.66,
        "edge": 0.03,
        "action": "paper_probe",
        "satisfied_gates": ["near_resolution_window", "source_margin_favors_side", "latest_source_available", "strict_limit_not_crossed"],
        "blockers": [],
        "source_references": ["fixture://threshold-resolution"],
        "threshold_watch": {"eligible": True, "recommendation": "paper_micro_strict_limit"},
    },
    "profitable_consensus_radar": {
        "market_id": "fixture-profitable-consensus",
        "probability_yes": 0.57,
        "confidence": 0.6,
        "edge": 0.06,
        "action": "paper_probe",
        "satisfied_gates": ["multi_handle_consensus", "independent_source_confirms", "edge_survives_fill", "not_wallet_copy_only"],
        "blockers": [],
        "source_references": ["fixture://profitable-consensus"],
        "consensus_signal": {"handle_count": 3, "net_side": "YES"},
    },
    "conviction_signal_follower": {
        "market_id": "fixture-conviction-signal",
        "probability_yes": 0.63,
        "confidence": 0.67,
        "edge": 0.07,
        "action": "paper_probe",
        "satisfied_gates": ["conviction_archetype_match", "min_edge_met", "source_confirmed", "edge_survives_fill"],
        "blockers": [],
        "source_references": ["fixture://conviction-signal"],
        "matched_traders": ["fixture-alpha", "fixture-beta"],
    },
    "macro_weather_event_trader": {
        "market_id": "fixture-macro-weather",
        "probability_yes": 0.55,
        "confidence": 0.59,
        "edge": 0.08,
        "action": "paper_probe",
        "satisfied_gates": ["macro_event_identified", "forecast_source_supported", "rules_clear", "liquidity_sufficient"],
        "blockers": [],
        "source_references": ["fixture://macro-weather"],
        "macro_event_context": {"event_type": "hurricane", "region": "fixture"},
    },
}


def strategy_smoke_summary() -> dict[str, object]:
    registry = StrategyRegistry()
    registry.register(WeatherBaselineStrategy(payloads=[WEATHER_FIXTURE]), StrategyConfig(strategy_id="weather_baseline", enabled=True))
    registry.register(PanoptiqueShadowFlowStrategy(records=[PANOPTIQUE_FIXTURE]), StrategyConfig(strategy_id="panoptique_shadow_flow", enabled=True))
    for strategy in build_weather_profile_strategies(WEATHER_PROFILE_FIXTURES):
        registry.register(strategy, StrategyConfig(strategy_id=strategy.descriptor.strategy_id, enabled=True, mode=strategy.descriptor.mode))
    results = registry.run_enabled(StrategyRunRequest(market_id="fixture"))
    signals = [signal for result in results for signal in result.signals]
    return {
        "command": "strategy-smoke",
        "fixture": True,
        "available_strategy_profiles": operator_profile_matrix(),
        "available_strategy_profile_count": len(operator_profile_matrix()),
        "executable_strategies": [
            {
                "strategy_id": item.strategy_id,
                "mode": item.descriptor.mode.value,
                "target": item.descriptor.target.value,
                "enabled": item.enabled,
            }
            for item in registry.registered()
        ],
        "results": [
            {"strategy_id": result.strategy_id, "mode": result.mode.value, "signal_count": len(result.signals), "errors": result.errors}
            for result in results
        ],
        "measurement": group_signals_for_read_model(signals),
        "safety": {"credentials_required": False, "db_required": False, "live_network_required": False, "trading_action": "none"},
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="prediction-core-strategies")
    sub = parser.add_subparsers(dest="command")
    smoke = sub.add_parser("strategy-smoke")
    smoke.add_argument("--fixture", action="store_true", required=True)
    args = parser.parse_args(argv)
    if args.command == "strategy-smoke" and args.fixture:
        print(json.dumps(strategy_smoke_summary(), sort_keys=True))
        return 0
    parser.print_help()
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
