from __future__ import annotations

import argparse
import json
from typing import Sequence

from .config import StrategyConfig
from .measurement import group_signals_for_read_model
from .panoptique_shadow_flow import PanoptiqueShadowFlowStrategy
from .registry import StrategyRegistry
from .weather_baseline import WeatherBaselineStrategy
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


def strategy_smoke_summary() -> dict[str, object]:
    registry = StrategyRegistry()
    registry.register(WeatherBaselineStrategy(payloads=[WEATHER_FIXTURE]), StrategyConfig(strategy_id="weather_baseline", enabled=True))
    registry.register(PanoptiqueShadowFlowStrategy(records=[PANOPTIQUE_FIXTURE]), StrategyConfig(strategy_id="panoptique_shadow_flow", enabled=True))
    results = registry.run_enabled(StrategyRunRequest(market_id="fixture"))
    signals = [signal for result in results for signal in result.signals]
    return {
        "command": "strategy-smoke",
        "fixture": True,
        "strategies": [
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
