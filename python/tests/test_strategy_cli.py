from __future__ import annotations

import json

from prediction_core.strategies.cli import main, strategy_smoke_summary


EXPECTED_PROFILE_IDS = [
    "surface_grid_trader",
    "exact_bin_anomaly_hunter",
    "threshold_resolution_harvester",
    "profitable_consensus_radar",
    "conviction_signal_follower",
    "macro_weather_event_trader",
]

EXPECTED_EXECUTABLE_IDS = ["weather_baseline", "panoptique_shadow_flow", *(f"weather_profile_{profile_id}_v1" for profile_id in EXPECTED_PROFILE_IDS)]


def test_strategy_smoke_summary_fixture_safe() -> None:
    summary = strategy_smoke_summary()
    assert summary["fixture"] is True
    assert summary["safety"] == {"credentials_required": False, "db_required": False, "live_network_required": False, "trading_action": "none"}
    assert summary["available_strategy_profile_count"] == 6
    assert [item["id"] for item in summary["available_strategy_profiles"]] == EXPECTED_PROFILE_IDS
    assert [item["strategy_id"] for item in summary["executable_strategies"]] == EXPECTED_EXECUTABLE_IDS
    assert [item["strategy_id"] for item in summary["results"]] == EXPECTED_EXECUTABLE_IDS
    assert [item["mode"] for item in summary["executable_strategies"][2:]] == ["paper_only"] * 6
    assert [item["target"] for item in summary["executable_strategies"][2:]] == ["event_outcome_forecasting"] * 6
    assert "strategies" not in summary
    assert all("recommendation" not in result for result in summary["results"])
    assert all(result["errors"] == [] for result in summary["results"])
    assert sum(result["signal_count"] for result in summary["results"]) == 8


def test_cli_main_prints_json(capsys) -> None:
    code = main(["strategy-smoke", "--fixture"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "strategy-smoke"
    assert payload["safety"]["trading_action"] == "none"
    assert [item["mode"] for item in payload["executable_strategies"][:2]] == ["paper_only", "research_only"]
    assert [item["strategy_id"] for item in payload["executable_strategies"][2:]] == EXPECTED_EXECUTABLE_IDS[2:]
    assert "strategies" not in payload
