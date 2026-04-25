from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

from weather_pm.traders import load_weather_traders, reverse_engineer_weather_traders


FIXTURE_ROWS = [
    {
        "rank": "3",
        "userName": "ColdMath",
        "proxyWallet": "0x594edb9112f526fa6a80b8f858a6379c8a2c1c11",
        "weather_pnl_usd": "121208.000000",
        "weather_volume_usd": "8824482.000000",
        "pnl_over_volume_pct": "1.373000",
        "classification": "weather specialist / weather-heavy",
        "confidence": "high",
        "active_positions": "100",
        "active_weather_positions": "95",
        "active_nonweather_positions": "0",
        "recent_activity": "200",
        "recent_weather_activity": "124",
        "recent_nonweather_activity": "0",
        "sample_weather_titles": "Will the highest temperature in Cape Town be 16°C on April 20? | Will the highest temperature in Ankara be 10°C or higher on March 1?",
        "sample_nonweather_titles": "",
        "profile_url": "https://polymarket.com/profile/0x594edb9112f526fa6a80b8f858a6379c8a2c1c11",
    },
    {
        "rank": "8",
        "userName": "automatedAItradingbot",
        "proxyWallet": "0xd8f8c13644ea84d62e1ec88c5d1215e436eb0f11",
        "weather_pnl_usd": "64618.000000",
        "weather_volume_usd": "2362464.000000",
        "pnl_over_volume_pct": "2.735000",
        "classification": "weather specialist / weather-heavy",
        "confidence": "high",
        "active_positions": "80",
        "active_weather_positions": "60",
        "active_nonweather_positions": "0",
        "recent_activity": "90",
        "recent_weather_activity": "77",
        "recent_nonweather_activity": "0",
        "sample_weather_titles": "Will the highest temperature in Seoul be 22°C on April 23? | Will the highest temperature in Los Angeles be between 70-71°F on April 19?",
        "sample_nonweather_titles": "",
        "profile_url": "https://polymarket.com/profile/0xd8f8c13644ea84d62e1ec88c5d1215e436eb0f11",
    },
    {
        "rank": "1",
        "userName": "gopfan2",
        "proxyWallet": "0xf2f6af4f27ec2dcf4072095ab804016e14cd5817",
        "weather_pnl_usd": "343787.000000",
        "weather_volume_usd": "4571380.000000",
        "pnl_over_volume_pct": "7.521000",
        "classification": "profitable in weather but currently/recently generalist",
        "confidence": "medium",
        "active_positions": "100",
        "active_weather_positions": "2",
        "active_nonweather_positions": "70",
        "recent_activity": "200",
        "recent_weather_activity": "2",
        "recent_nonweather_activity": "150",
        "sample_weather_titles": "Will there be more than 25 named storms during Atlantic Hurricane Season?",
        "sample_nonweather_titles": "Will Congo DR win the 2026 FIFA World Cup? | Will Kamala Harris win the 2028 US Presidential Election?",
        "profile_url": "https://polymarket.com/profile/0xf2f6af4f27ec2dcf4072095ab804016e14cd5817",
    },
]


def _write_fixture(path: Path) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(FIXTURE_ROWS[0].keys()))
        writer.writeheader()
        writer.writerows(FIXTURE_ROWS)


def test_load_weather_traders_preserves_profitability_and_classification(tmp_path: Path) -> None:
    fixture = tmp_path / "classified.csv"
    _write_fixture(fixture)

    traders = load_weather_traders(fixture)

    assert [trader.handle for trader in traders] == ["gopfan2", "ColdMath", "automatedAItradingbot"]
    coldmath = traders[1]
    assert coldmath.rank == 3
    assert coldmath.wallet == "0x594edb9112f526fa6a80b8f858a6379c8a2c1c11"
    assert coldmath.weather_pnl_usd == 121208.0
    assert coldmath.is_weather_heavy is True
    assert coldmath.weather_signal_count == 219
    assert coldmath.profile_url.endswith(coldmath.wallet)


def test_reverse_engineer_weather_traders_separates_specialists_from_generalists(tmp_path: Path) -> None:
    fixture = tmp_path / "classified.csv"
    _write_fixture(fixture)
    traders = load_weather_traders(fixture)

    report = reverse_engineer_weather_traders(traders, min_pnl_usd=10000.0)

    assert report["total_accounts"] == 3
    assert report["weather_heavy_count"] == 2
    assert report["generalist_count"] == 1
    assert report["priority_accounts"] == ["ColdMath", "automatedAItradingbot"]
    assert report["patterns"]["dominant_market_types"] == ["exact_temperature_bins", "threshold_temperature_contracts"]
    assert "city/date/bucket grid" in report["reverse_engineering_hypotheses"][0]
    assert report["accounts"][0]["handle"] == "ColdMath"
    assert report["accounts"][0]["recommended_use"] == "model_and_execution_template"
    assert report["accounts"][-1]["recommended_use"] == "signal_only_generalist"


def test_cli_import_weather_traders_writes_project_registry_and_reverse_engineering_report(tmp_path: Path) -> None:
    fixture = tmp_path / "classified.csv"
    registry = tmp_path / "registry.json"
    report = tmp_path / "reverse.json"
    _write_fixture(fixture)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "weather_pm.cli",
            "import-weather-traders",
            "--classified-csv",
            str(fixture),
            "--registry-out",
            str(registry),
            "--reverse-engineering-out",
            str(report),
            "--min-pnl",
            "10000",
        ],
        capture_output=True,
        text=True,
        check=False,
        env={"PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["registry_path"] == str(registry)
    assert payload["reverse_engineering_path"] == str(report)
    assert payload["total_accounts"] == 3
    assert payload["weather_heavy_count"] == 2

    registry_payload = json.loads(registry.read_text())
    assert registry_payload["source"] == "polymarket_weather_leaderboard"
    assert registry_payload["accounts"][0]["handle"] == "gopfan2"

    report_payload = json.loads(report.read_text())
    assert report_payload["priority_accounts"] == ["ColdMath", "automatedAItradingbot"]
