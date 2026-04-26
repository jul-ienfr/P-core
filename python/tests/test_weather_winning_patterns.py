from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from weather_pm.winning_patterns import build_winning_patterns_operator_report


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    project_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(project_root / "src")
    return subprocess.run(
        [sys.executable, "-m", "weather_pm.cli", *args],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def test_build_winning_patterns_operator_report_extracts_rules_and_priorities() -> None:
    report = build_winning_patterns_operator_report(
        classified_summary={
            "classification_counts": {
                "weather specialist / weather-heavy": 36,
                "weather-heavy mixed": 24,
                "profitable in weather but currently/recently generalist": 20,
                "not enough public recent data to classify": 10,
            },
            "weather_heavy_or_specialist_count": 60,
        },
        continued_summary={"total_profitable_weather_pnl_accounts": 90},
        strategy_patterns={
            "kind_counts": {"range_or_bin": 150, "threshold": 25},
            "top_cities": [["London", 12], ["Seoul", 10]],
        },
        strategy_report={
            "summary": {
                "account_count": 8,
                "archetype_counts": {
                    "event_surface_grid_specialist": 5,
                    "exact_bin_anomaly_hunter": 2,
                    "threshold_harvester": 1,
                },
                "implementation_priorities": ["event_surface_builder", "paper_then_live_execution_loop"],
            }
        },
        future_consensus={
            "rows": [
                {
                    "city": "Shanghai",
                    "date": "April 26",
                    "side": "NO",
                    "top_temp": "21°C",
                    "accounts": 10,
                    "signals": 30,
                    "side_share": 0.963,
                    "forecast_max_c": 23.8,
                    "source_verdict_future": "NO_aligned_with_proxy_exact_bin_false",
                    "action_score": 529.5,
                },
                {
                    "city": "Moscow",
                    "date": "April 26",
                    "side": "NO",
                    "top_temp": "12°C",
                    "accounts": 9,
                    "signals": 32,
                    "side_share": 0.994,
                    "forecast_max_c": 10.0,
                    "source_verdict_future": None,
                    "action_score": 570.0,
                },
            ]
        },
        orderbook_bridge={
            "rows": [
                {
                    "city": "Shanghai",
                    "date": "April 26",
                    "label": "21C",
                    "source_status": "source_ok",
                    "tradability": "ok",
                    "no_best_ask": "0.935",
                    "no_20_avg": "0.935",
                    "volume": "8730",
                    "consensus_score": "586",
                    "unique_accounts": 20,
                    "signal_count": 93,
                },
                {
                    "city": "Moscow",
                    "date": "April 26",
                    "label": "12C",
                    "source_status": "source_missing",
                    "tradability": "ok",
                    "no_best_ask": "0.99",
                    "volume": "5100",
                    "consensus_score": "415",
                    "unique_accounts": 14,
                    "signal_count": 51,
                },
            ]
        },
        limit=5,
    )

    assert report["summary"]["positive_weather_accounts"] == 90
    assert report["summary"]["weather_heavy_or_mixed_accounts"] == 60
    assert report["archetype_counts"]["event_surface_grid_specialist"] == 5
    assert report["rules"][0]["id"] == "R1"
    assert report["rules"][0]["operator_rule"] == "Group all markets by city/date/unit before scoring isolated bins."
    assert report["consensus_surfaces"][0] == {
        "city": "Moscow",
        "date": "April 26",
        "side": "NO",
        "top_temp": "12°C",
        "accounts": 9,
        "signals": 32,
        "side_share": 0.994,
        "forecast_max_c": 10.0,
        "source_verdict": None,
        "action_score": 570.0,
        "operator_status": "watch_source_missing",
    }
    assert report["orderbook_candidates"][0]["city"] == "Shanghai"
    assert report["orderbook_candidates"][0]["target_ask"] == 0.935
    assert report["implementation_priorities"] == ["event_surface_builder", "paper_then_live_execution_loop"]
    assert "Météo patterns gagnants" in report["discord_brief"]


def test_cli_winning_patterns_report_reads_artifacts_and_writes_markdown(tmp_path: Path) -> None:
    classified = tmp_path / "classified.json"
    continued = tmp_path / "continued.json"
    patterns = tmp_path / "patterns.json"
    strategy = tmp_path / "strategy.json"
    future = tmp_path / "future.json"
    bridge = tmp_path / "bridge.json"
    output_json = tmp_path / "report.json"
    output_md = tmp_path / "report.md"

    classified.write_text(json.dumps({"classification_counts": {"weather specialist / weather-heavy": 1}, "weather_heavy_or_specialist_count": 1}), encoding="utf-8")
    continued.write_text(json.dumps({"total_profitable_weather_pnl_accounts": 2}), encoding="utf-8")
    patterns.write_text(json.dumps({"kind_counts": {"range_or_bin": 3}, "top_cities": [["London", 2]]}), encoding="utf-8")
    strategy.write_text(json.dumps({"summary": {"account_count": 1, "archetype_counts": {"event_surface_grid_specialist": 1}, "implementation_priorities": ["event_surface_builder"]}}), encoding="utf-8")
    future.write_text(json.dumps({"rows": [{"city": "London", "date": "April 26", "side": "NO", "top_temp": "20°C", "accounts": 3, "signals": 9, "action_score": 99}]}), encoding="utf-8")
    bridge.write_text(json.dumps({"rows": [{"city": "London", "date": "April 26", "label": "20C", "source_status": "source_ok", "tradability": "ok", "no_best_ask": "0.7", "volume": "1000", "consensus_score": "50"}]}), encoding="utf-8")

    result = _run_cli(
        "winning-patterns-report",
        "--classified-summary-json",
        str(classified),
        "--continued-summary-json",
        str(continued),
        "--strategy-patterns-json",
        str(patterns),
        "--strategy-report-json",
        str(strategy),
        "--future-consensus-json",
        str(future),
        "--orderbook-bridge-json",
        str(bridge),
        "--output-json",
        str(output_json),
        "--output-md",
        str(output_md),
        "--limit",
        "3",
    )

    assert result.returncode == 0, result.stderr
    compact = json.loads(result.stdout)
    assert compact["summary"]["positive_weather_accounts"] == 2
    assert compact["artifacts"]["output_json"] == str(output_json)
    assert compact["artifacts"]["output_md"] == str(output_md)
    saved = json.loads(output_json.read_text(encoding="utf-8"))
    assert saved["rules"][0]["id"] == "R1"
    markdown = output_md.read_text(encoding="utf-8")
    assert "# Polymarket météo — patterns gagnants" in markdown
    assert "London April 26" in markdown
