from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from weather_pm.event_surface import build_weather_event_surface


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


def test_build_weather_event_surface_groups_city_date_and_flags_monotonic_threshold_violation() -> None:
    markets = [
        {"id": "london-19", "question": "Will the highest temperature in London be 19°C or higher on April 25?", "yes_price": 0.40},
        {"id": "london-20", "question": "Will the highest temperature in London be 20°C or higher on April 25?", "yes_price": 0.45},
        {"id": "london-21", "question": "Will the highest temperature in London be 21°C or higher on April 25?", "yes_price": 0.20},
        {"id": "paris-18", "question": "Will the highest temperature in Paris be 18°C or higher on April 25?", "yes_price": 0.55},
    ]

    surface = build_weather_event_surface(markets)

    assert surface["event_count"] == 2
    london = surface["events"][0]
    assert london["event_key"] == "London|high|c|April 25"
    assert london["market_count"] == 3
    assert london["threshold_count"] == 3
    assert london["inconsistencies"] == [
        {
            "type": "threshold_monotonicity_violation",
            "direction": "higher",
            "lower_market_id": "london-19",
            "higher_market_id": "london-20",
            "lower_target": 19.0,
            "higher_target": 20.0,
            "lower_price": 0.4,
            "higher_price": 0.45,
            "severity": 0.05,
        }
    ]


def test_build_weather_event_surface_flags_exact_bin_mass_overround() -> None:
    markets = [
        {"id": "nyc-70", "question": "Will the highest temperature in New York City be exactly 70°F on April 25?", "yes_price": 0.34},
        {"id": "nyc-71", "question": "Will the highest temperature in New York City be exactly 71°F on April 25?", "yes_price": 0.33},
        {"id": "nyc-72", "question": "Will the highest temperature in New York City be exactly 72°F on April 25?", "yes_price": 0.36},
    ]

    surface = build_weather_event_surface(markets, exact_mass_tolerance=1.0)

    nyc = surface["events"][0]
    assert nyc["exact_bin_count"] == 3
    assert nyc["exact_bin_price_mass"] == 1.03
    assert nyc["inconsistencies"] == [
        {
            "type": "exact_bin_mass_overround",
            "price_mass": 1.03,
            "tolerance": 1.0,
            "severity": 0.03,
        }
    ]


def test_build_weather_event_surface_keeps_between_bins_with_dates_and_requires_source_identity() -> None:
    markets = [
        {"id": "chi-70-71", "question": "Will the highest temperature in Chicago be between 70°F and 71°F on April 30?", "yes_price": 0.44, "resolution": {}},
        {"id": "chi-72-73", "question": "Will the highest temperature in Chicago be between 72°F and 73°F on April 30?", "yes_price": 0.62, "resolution": {"provider": "noaa"}},
    ]

    surface = build_weather_event_surface(markets)

    chicago = surface["events"][0]
    assert chicago["event_key"] == "Chicago|high|f|April 30"
    assert chicago["exact_bin_count"] == 2
    assert chicago["source"]["status"] == "source_confirmed"


def test_build_weather_event_surface_does_not_confirm_empty_resolution_objects() -> None:
    surface = build_weather_event_surface([
        {"id": "chi-70", "question": "Will the highest temperature in Chicago be exactly 70°F on April 30?", "yes_price": 0.25, "resolution": {}}
    ])

    event = surface["events"][0]
    assert event["source"]["status"] == "source_missing"
    assert event["execution_status"] == "source_missing_do_not_trade"


def test_cli_event_surface_reads_market_json_and_outputs_grouped_surface(tmp_path: Path) -> None:
    markets_path = tmp_path / "markets.json"
    markets_path.write_text(
        json.dumps(
            {
                "markets": [
                    {"id": "london-19", "question": "Will the highest temperature in London be 19°C or higher on April 25?", "yes_price": 0.40},
                    {"id": "london-20", "question": "Will the highest temperature in London be 20°C or higher on April 25?", "yes_price": 0.45},
                ]
            }
        )
    )

    result = _run_cli("event-surface", "--markets-json", str(markets_path))

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["event_count"] == 1
    assert payload["events"][0]["event_key"] == "London|high|c|April 25"
    assert payload["events"][0]["inconsistencies"][0]["type"] == "threshold_monotonicity_violation"


def test_cli_event_surface_can_write_full_report_and_print_compact_summary(tmp_path: Path) -> None:
    markets_path = tmp_path / "markets.json"
    out_path = tmp_path / "event-surface.json"
    markets_path.write_text(
        json.dumps(
            {
                "markets": [
                    {"id": "london-19", "question": "Will the highest temperature in London be 19°C or higher on April 25?", "yes_price": 0.40},
                    {"id": "london-20", "question": "Will the highest temperature in London be 20°C or higher on April 25?", "yes_price": 0.45},
                ]
            }
        )
    )

    result = _run_cli("event-surface", "--markets-json", str(markets_path), "--output-json", str(out_path))

    assert result.returncode == 0, result.stderr
    compact = json.loads(result.stdout)
    full = json.loads(out_path.read_text())
    assert compact == {
        "event_count": 1,
        "events_with_inconsistencies": 1,
        "market_count": 2,
        "artifacts": {"output_json": str(out_path)},
    }
    assert full["event_count"] == 1
    assert full["events"][0]["event_key"] == "London|high|c|April 25"
    assert full["artifacts"]["source_markets_json"] == str(markets_path)
    assert full["artifacts"]["output_json"] == str(out_path)
    assert len(result.stdout) < len(out_path.read_text())
