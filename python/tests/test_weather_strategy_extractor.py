from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from weather_pm.strategy_extractor import extract_weather_strategy_rules, summarize_strategy_rules
from weather_pm.traders import WeatherTrader


def _trader(handle: str, titles: list[str], *, pnl: float = 10000.0, volume: float = 100000.0) -> WeatherTrader:
    return WeatherTrader(
        rank=1,
        handle=handle,
        wallet=f"0x{handle.lower()[:8]:0<8}",
        weather_pnl_usd=pnl,
        weather_volume_usd=volume,
        pnl_over_volume_pct=round(pnl / volume * 100, 6),
        classification="weather specialist / weather-heavy",
        confidence="high",
        active_positions=100,
        active_weather_positions=95,
        active_nonweather_positions=0,
        recent_activity=120,
        recent_weather_activity=110,
        recent_nonweather_activity=0,
        sample_weather_titles=titles,
        sample_nonweather_titles=[],
        profile_url="https://polymarket.com/profile/test",
    )


def test_extract_weather_strategy_rules_classifies_city_market_type_and_reusable_actions() -> None:
    trader = _trader(
        "ColdMath",
        [
            "Will the highest temperature in London be 19°C on April 25?",
            "Will the highest temperature in London be exactly 20°C on April 25?",
            "Will the highest temperature in London be 21°C or higher on April 25?",
            "Will the highest temperature in New York City be between 70-71°F on April 25?",
        ],
    )

    rules = extract_weather_strategy_rules([trader])

    assert rules["account_count"] == 1
    coldmath = rules["accounts"][0]
    assert coldmath["handle"] == "ColdMath"
    assert coldmath["primary_archetype"] == "event_surface_grid_specialist"
    assert coldmath["market_type_counts"] == {"exact_value": 2, "exact_range": 1, "threshold": 1}
    assert coldmath["top_cities"] == [{"city": "London", "count": 3}, {"city": "New York City", "count": 1}]
    assert "build full city/date event surfaces before scoring isolated markets" in coldmath["strategy_rules"]
    assert "prioritize exact-bin and adjacent threshold inconsistencies" in coldmath["strategy_rules"]


def test_summarize_strategy_rules_prioritizes_repeated_archetypes() -> None:
    rules = extract_weather_strategy_rules(
        [
            _trader("GridBot", [
                "Will the highest temperature in Seoul be 21°C on April 25?",
                "Will the highest temperature in Seoul be 22°C on April 25?",
            ]),
            _trader("ThresholdBot", [
                "Will the highest temperature in London be 20°C or higher on April 25?",
                "Will the highest temperature in Paris be 18°C or below on April 25?",
            ]),
        ]
    )

    summary = summarize_strategy_rules(rules)

    assert summary["account_count"] == 2
    assert summary["archetype_counts"] == {
        "event_surface_grid_specialist": 1,
        "threshold_harvester": 1,
    }
    assert summary["implementation_priorities"][0] == "event_surface_builder"
    assert "London" in summary["top_cities"]


def test_cli_strategy_report_reads_reverse_engineering_json_and_outputs_priorities(tmp_path: Path) -> None:
    reverse_report = tmp_path / "reverse.json"
    reverse_report.write_text(
        json.dumps(
            {
                "accounts": [
                    {
                        "rank": 3,
                        "handle": "ColdMath",
                        "wallet": "0x594edb9112f526fa6a80b8f858a6379c8a2c1c11",
                        "weather_pnl_usd": 121208.0,
                        "weather_volume_usd": 8824482.0,
                        "pnl_over_volume_pct": 1.373,
                        "classification": "weather specialist / weather-heavy",
                        "confidence": "high",
                        "active_positions": 100,
                        "active_weather_positions": 95,
                        "active_nonweather_positions": 0,
                        "recent_activity": 200,
                        "recent_weather_activity": 124,
                        "recent_nonweather_activity": 0,
                        "sample_weather_titles": [
                            "Will the highest temperature in London be 19°C on April 25?",
                            "Will the highest temperature in London be 20°C on April 25?",
                        ],
                        "sample_nonweather_titles": [],
                        "profile_url": "https://polymarket.com/profile/0x594edb9112f526fa6a80b8f858a6379c8a2c1c11",
                    }
                ]
            }
        )
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "weather_pm.cli",
            "strategy-report",
            "--reverse-engineering-json",
            str(reverse_report),
        ],
        capture_output=True,
        text=True,
        check=False,
        env={"PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["summary"]["implementation_priorities"][0] == "event_surface_builder"
    assert payload["accounts"][0]["handle"] == "ColdMath"
    assert payload["accounts"][0]["primary_archetype"] == "event_surface_grid_specialist"
