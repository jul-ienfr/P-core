from __future__ import annotations

import json

from prediction_core.strategies.cli import main, strategy_smoke_summary


def test_strategy_smoke_summary_fixture_safe() -> None:
    summary = strategy_smoke_summary()
    assert summary["fixture"] is True
    assert summary["safety"] == {"credentials_required": False, "db_required": False, "live_network_required": False, "trading_action": "none"}
    assert {item["strategy_id"] for item in summary["strategies"]} == {"weather_baseline", "panoptique_shadow_flow"}
    assert all("recommendation" not in result for result in summary["results"])
    assert sum(result["signal_count"] for result in summary["results"]) == 2


def test_cli_main_prints_json(capsys) -> None:
    code = main(["strategy-smoke", "--fixture"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "strategy-smoke"
    assert payload["safety"]["trading_action"] == "none"
    assert [item["mode"] for item in payload["strategies"]] == ["paper_only", "research_only"]
