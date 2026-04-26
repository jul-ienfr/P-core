from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _run_weather_pm(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT / "src")
    return subprocess.run(
        [sys.executable, "-m", "weather_pm.cli", *args],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        env=env,
        check=False,
    )


def test_paper_watchlist_cli_builds_operator_report_from_saved_monitor(tmp_path: Path) -> None:
    monitor = {
        "positions": [
            {
                "city": "Seoul",
                "date": "April 26",
                "station": "RKSI",
                "side": "NO",
                "temp": 20,
                "unit": "C",
                "kind": "higher",
                "filled_usdc": 17.24,
                "shares": 70.485867,
                "entry_avg": 0.2446,
                "current_forecast_max_c": 18,
                "base_p_side": 0.858,
                "best_bid": 0.26,
                "best_ask": 0.29,
            }
        ]
    }
    input_json = tmp_path / "monitor.json"
    output_json = tmp_path / "watchlist.json"
    input_json.write_text(json.dumps(monitor), encoding="utf-8")

    result = _run_weather_pm("paper-watchlist", "--input-json", str(input_json), "--output-json", str(output_json))

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["summary"]["positions"] == 1
    assert payload["summary"]["action_counts"] == {"HOLD_CAPPED": 1}
    assert payload["watchlist"][0]["operator_action"] == "HOLD_CAPPED"
    assert output_json.exists()
    written = json.loads(output_json.read_text(encoding="utf-8"))
    assert written["watchlist"][0]["hard_stop_if_p_below"] == 0.2146


def test_paper_watchlist_cli_builds_operator_report_from_saved_monitor_with_nested_paper_fill(tmp_path: Path) -> None:
    monitor = {
        "positions": [
            {
                "city": "Warsaw",
                "date": "April 26",
                "station": "EPWA",
                "side": "NO",
                "temp": 11,
                "unit": "C",
                "kind": "exact",
                "paper_fill": {"filled_usdc": 5.0, "shares": 9.0909, "avg_price": 0.55},
                "p_side_now": 0.7339,
                "live_best_bid_now": 0.52,
                "live_best_ask_now": 0.55,
            }
        ]
    }
    input_json = tmp_path / "monitor.json"
    output_json = tmp_path / "watchlist.json"
    input_json.write_text(json.dumps(monitor), encoding="utf-8")

    result = _run_weather_pm("paper-watchlist", "--input-json", str(input_json), "--output-json", str(output_json))

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["summary"]["positions"] == 1
    assert payload["summary"]["total_spend"] == 5.0
    assert payload["watchlist"][0]["entry_avg"] == 0.55
    assert payload["watchlist"][0]["spend_usdc"] == 5.0
    assert payload["watchlist"][0]["paper_ev_now_usdc"] == 1.672
    assert output_json.exists()


def test_paper_watchlist_cli_can_print_compact_operator_payload(tmp_path: Path) -> None:
    monitor = {
        "positions": [
            {
                "city": "Seoul",
                "date": "April 26",
                "station": "RKSI",
                "side": "NO",
                "temp": 20,
                "unit": "C",
                "kind": "higher",
                "filled_usdc": 7.24,
                "shares": 28.8192,
                "entry_avg": 0.2512,
                "current_forecast_max_c": 18,
                "base_p_side": 0.858,
            },
            {
                "city": "Beijing",
                "date": "April 26",
                "station": "ZBAA",
                "side": "NO",
                "temp": 25,
                "unit": "C",
                "kind": "exact",
                "filled_usdc": 15.0,
                "shares": 24.1935,
                "entry_avg": 0.62,
                "current_forecast_max_c": 26,
                "base_p_side": 0.7815,
            },
        ]
    }
    input_json = tmp_path / "monitor.json"
    output_json = tmp_path / "watchlist.json"
    output_csv = tmp_path / "watchlist.csv"
    output_md = tmp_path / "watchlist.md"
    input_json.write_text(json.dumps(monitor), encoding="utf-8")

    result = _run_weather_pm(
        "paper-watchlist",
        "--input-json",
        str(input_json),
        "--output-json",
        str(output_json),
        "--output-csv",
        str(output_csv),
        "--output-md",
        str(output_md),
        "--compact",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload == {
        "positions": 2,
        "total_spend": 22.24,
        "total_ev_now": 21.39,
        "global_action": "HOLD",
        "top_ev": "Seoul April 26 NO higher 20°C (+17.49 USDC)",
        "add_allowed_count": 0,
        "artifacts": {
            "json": str(output_json),
            "csv": str(output_csv),
            "markdown": str(output_md),
        },
    }
    assert output_json.exists()
    assert output_csv.exists()
    assert output_md.exists()
