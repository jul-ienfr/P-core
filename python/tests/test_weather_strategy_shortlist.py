from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from weather_pm.strategy_shortlist import build_strategy_shortlist


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


def test_build_strategy_shortlist_prioritizes_tradeable_surface_anomalies_and_trader_cities() -> None:
    strategy_report = {
        "summary": {"top_cities": ["London", "New York City"]},
        "accounts": [
            {
                "handle": "ColdMath",
                "primary_archetype": "event_surface_grid_specialist",
                "top_cities": [{"city": "London", "count": 8}],
                "weather_pnl_usd": 121302.2,
            },
            {
                "handle": "Amano-Hina",
                "primary_archetype": "exact_bin_anomaly_hunter",
                "top_cities": [{"city": "New York City", "count": 6}],
                "weather_pnl_usd": 8831.7,
            },
        ],
    }
    opportunity_report = {
        "summary": {"selected": 4, "scored": 4, "traded": 2},
        "opportunities": [
            {
                "market_id": "london-20",
                "question": "Will the highest temperature in London be 20°C or higher on April 25?",
                "decision_status": "trade_small",
                "probability_edge": 0.12,
                "all_in_cost_bps": 120.0,
                "order_book_depth_usd": 900.0,
                "source_direct": True,
                "source_latency_tier": "direct_latest",
            },
            {
                "market_id": "nyc-70",
                "question": "Will the highest temperature in New York City be exactly 70°F on April 25?",
                "decision_status": "watchlist",
                "probability_edge": 0.2,
                "all_in_cost_bps": 90.0,
                "order_book_depth_usd": 700.0,
                "source_direct": True,
            },
            {
                "market_id": "paris-18",
                "question": "Will the highest temperature in Paris be 18°C or higher on April 25?",
                "decision_status": "trade",
                "probability_edge": 0.3,
                "all_in_cost_bps": 80.0,
                "order_book_depth_usd": 1000.0,
                "source_direct": False,
            },
        ],
    }
    event_surface = {
        "events": [
            {
                "event_key": "London|high|c|April 25",
                "inconsistencies": [
                    {"type": "threshold_monotonicity_violation", "severity": 0.05, "lower_market_id": "london-19", "higher_market_id": "london-20"}
                ],
            },
            {
                "event_key": "New York City|high|f|April 25",
                "inconsistencies": [{"type": "exact_bin_mass_overround", "severity": 0.03}],
            },
        ]
    }

    shortlist = build_strategy_shortlist(strategy_report, opportunity_report, event_surface, limit=3)

    assert shortlist["summary"] == {
        "input_opportunities": 3,
        "strategy_accounts": 2,
        "surface_events": 2,
        "shortlisted": 3,
    }
    assert [item["market_id"] for item in shortlist["shortlist"]] == ["london-20", "paris-18", "nyc-70"]
    london = shortlist["shortlist"][0]
    assert london["city"] == "London"
    assert london["decision_status"] == "trade_small"
    assert london["trader_archetype_match"] == ["event_surface_grid_specialist"]
    assert london["matched_traders"] == ["ColdMath"]
    assert london["surface_inconsistency_count"] == 1
    assert london["action"] == "paper_trade_watch_direct_station"
    assert "surface_anomaly" in london["reasons"]
    assert "profitable_trader_city" in london["reasons"]
    assert "direct_resolution_source" in london["reasons"]


def test_build_strategy_shortlist_extracts_city_when_question_has_no_date() -> None:
    shortlist = build_strategy_shortlist(
        {"accounts": [{"handle": "Signal", "primary_archetype": "threshold_harvester", "top_cities": [{"city": "Denver", "count": 3}], "weather_pnl_usd": 1000.0}]},
        {"opportunities": [{"market_id": "denver-high-65", "question": "Will the highest temperature in Denver be 65F or higher?", "decision_status": "trade", "source_direct": True}]},
        {"events": []},
    )

    row = shortlist["shortlist"][0]
    assert row["city"] == "Denver"
    assert row["date"] == ""
    assert row["matched_traders"] == ["Signal"]


def test_cli_strategy_shortlist_reads_reports_and_writes_ranked_json(tmp_path: Path) -> None:
    strategy_path = tmp_path / "strategy.json"
    opportunities_path = tmp_path / "opportunities.json"
    surface_path = tmp_path / "surface.json"
    strategy_path.write_text(
        json.dumps(
            {
                "summary": {"top_cities": ["London"]},
                "accounts": [
                    {
                        "handle": "ColdMath",
                        "primary_archetype": "event_surface_grid_specialist",
                        "top_cities": [{"city": "London", "count": 8}],
                        "weather_pnl_usd": 121302.2,
                    }
                ],
            }
        )
    )
    opportunities_path.write_text(
        json.dumps(
            {
                "opportunities": [
                    {
                        "market_id": "london-20",
                        "question": "Will the highest temperature in London be 20°C or higher on April 25?",
                        "decision_status": "trade_small",
                        "probability_edge": 0.12,
                        "all_in_cost_bps": 120.0,
                        "order_book_depth_usd": 900.0,
                        "source_direct": True,
                    }
                ]
            }
        )
    )
    surface_path.write_text(
        json.dumps(
            {
                "events": [
                    {
                        "event_key": "London|high|c|April 25",
                        "inconsistencies": [{"type": "threshold_monotonicity_violation", "severity": 0.05}],
                    }
                ]
            }
        )
    )

    result = _run_cli(
        "strategy-shortlist",
        "--strategy-report-json",
        str(strategy_path),
        "--opportunity-report-json",
        str(opportunities_path),
        "--event-surface-json",
        str(surface_path),
        "--limit",
        "1",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["summary"]["shortlisted"] == 1
    assert payload["shortlist"][0]["market_id"] == "london-20"
    assert payload["shortlist"][0]["action"] == "paper_trade_watch_direct_station"
