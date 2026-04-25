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
                "source_provider": "noaa",
                "source_station_code": "EGLL",
                "source_latency_tier": "direct_latest",
                "source_latency_priority": "direct_source_low_latency",
                "source_polling_focus": "station_observations_latest",
                "source_latest_url": "https://api.weather.gov/stations/EGLL/observations/latest",
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
        "action_counts": {
            "paper_trade_watch_direct_station": 1,
            "paper_trade_watch_fallback_source": 1,
            "review_surface_anomaly": 1,
        },
        "execution_blocker_counts": {"watchlist": 1},
    }
    assert [item["market_id"] for item in shortlist["shortlist"]] == ["london-20", "paris-18", "nyc-70"]
    london = shortlist["shortlist"][0]
    assert london["city"] == "London"
    assert london["decision_status"] == "trade_small"
    assert london["trader_archetype_match"] == ["event_surface_grid_specialist"]
    assert london["matched_traders"] == ["ColdMath"]
    assert london["surface_inconsistency_count"] == 1
    assert london["source_provider"] == "noaa"
    assert london["source_station_code"] == "EGLL"
    assert london["source_latency_priority"] == "direct_source_low_latency"
    assert london["source_polling_focus"] == "station_observations_latest"
    assert london["source_latest_url"] == "https://api.weather.gov/stations/EGLL/observations/latest"
    assert london["execution_blocker"] is None
    assert london["action"] == "paper_trade_watch_direct_station"
    assert london["next_actions"] == [
        "poll_direct_resolution_source",
        "inspect_event_surface_prices",
        "paper_order_with_limit_and_fill_tracking",
    ]
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


def test_build_strategy_shortlist_turns_execution_blockers_into_operational_next_actions() -> None:
    shortlist = build_strategy_shortlist(
        {"accounts": []},
        {
            "opportunities": [
                {
                    "market_id": "thin-book",
                    "question": "Will the highest temperature in Dallas be 70°F or below on April 25?",
                    "decision_status": "skipped",
                    "skip_reason": "high_slippage_risk",
                    "source_direct": True,
                },
                {
                    "market_id": "no-quote",
                    "question": "Will the highest temperature in Dallas be 69°F or below on April 25?",
                    "decision_status": "skipped",
                    "skip_reason": "missing_tradeable_quote",
                    "source_direct": True,
                },
            ]
        },
        {"events": []},
    )

    assert shortlist["summary"]["execution_blocker_counts"] == {
        "high_slippage_risk": 1,
        "missing_tradeable_quote": 1,
    }
    rows = {row["market_id"]: row for row in shortlist["shortlist"]}
    assert rows["thin-book"]["execution_blocker"] == "high_slippage_risk"
    assert rows["thin-book"]["next_actions"] == ["poll_direct_resolution_source", "wait_for_tighter_spread"]
    assert rows["no-quote"]["next_actions"] == ["poll_direct_resolution_source", "wait_for_executable_depth"]


def test_cli_strategy_shortlist_report_builds_inputs_and_outputs_ranked_json(tmp_path: Path) -> None:
    reverse_path = tmp_path / "reverse.json"
    out_path = tmp_path / "shortlist.json"
    reverse_path.write_text(
        json.dumps(
            {
                "accounts": [
                    {
                        "rank": 1,
                        "handle": "DenverSharp",
                        "slug": "denversharp",
                        "weather_pnl_usd": 10000.0,
                        "markets_traded": 12,
                        "profitable_market_count": 9,
                        "top_cities": [{"city": "Denver", "count": 9}],
                        "top_market_types": [{"type": "threshold", "count": 8}],
                        "sample_weather_titles": [
                            "Will the highest temperature in Denver be 65F or higher?",
                            "Will the highest temperature in Denver be 64F or higher?",
                        ],
                    }
                ]
            }
        )
    )

    result = _run_cli(
        "strategy-shortlist-report",
        "--reverse-engineering-json",
        str(reverse_path),
        "--run-id",
        "shortlist-fixture",
        "--source",
        "fixture",
        "--limit",
        "5",
        "--output-json",
        str(out_path),
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["summary"]["strategy_accounts"] == 1
    assert payload["summary"]["shortlisted"] >= 1
    assert payload["shortlist"][0]["city"] == "Denver"
    assert payload["shortlist"][0]["matched_traders"] == ["DenverSharp"]
    assert payload["artifacts"]["output_json"] == str(out_path)
    full_payload = json.loads(out_path.read_text())
    assert full_payload["summary"] == payload["summary"]
    assert full_payload["shortlist"] == payload["shortlist"]
    assert full_payload["artifacts"] == payload["artifacts"]
    assert "strategy_report" in full_payload
    assert "opportunity_report" in full_payload


def test_cli_strategy_shortlist_report_prints_compact_summary_when_output_file_is_used(tmp_path: Path) -> None:
    reverse_path = tmp_path / "reverse.json"
    out_path = tmp_path / "shortlist-full.json"
    reverse_path.write_text(
        json.dumps(
            {
                "accounts": [
                    {
                        "rank": 1,
                        "handle": "DenverSharp",
                        "slug": "denversharp",
                        "weather_pnl_usd": 10000.0,
                        "markets_traded": 12,
                        "profitable_market_count": 9,
                        "top_cities": [{"city": "Denver", "count": 9}],
                        "top_market_types": [{"type": "threshold", "count": 8}],
                        "sample_weather_titles": ["Will the highest temperature in Denver be 65F or higher?"],
                    }
                ]
            }
        )
    )

    result = _run_cli(
        "strategy-shortlist-report",
        "--reverse-engineering-json",
        str(reverse_path),
        "--run-id",
        "shortlist-compact",
        "--source",
        "fixture",
        "--limit",
        "5",
        "--output-json",
        str(out_path),
    )

    assert result.returncode == 0, result.stderr
    compact = json.loads(result.stdout)
    full = json.loads(out_path.read_text())
    assert set(compact) == {"summary", "shortlist", "run_id", "source", "artifacts"}
    assert compact["summary"] == full["summary"]
    assert compact["shortlist"] == full["shortlist"]
    assert compact["artifacts"]["output_json"] == str(out_path)
    assert "strategy_report" in full
    assert "opportunity_report" in full
    assert "strategy_report" not in compact
    assert len(result.stdout) < len(out_path.read_text())


def test_cli_strategy_shortlist_report_can_reuse_event_surface_json_override(tmp_path: Path) -> None:
    reverse_path = tmp_path / "reverse.json"
    surface_path = tmp_path / "surface.json"
    out_path = tmp_path / "shortlist-full.json"
    reverse_path.write_text(
        json.dumps(
            {
                "accounts": [
                    {
                        "rank": 1,
                        "handle": "DenverSharp",
                        "slug": "denversharp",
                        "weather_pnl_usd": 10000.0,
                        "markets_traded": 12,
                        "profitable_market_count": 9,
                        "top_cities": [{"city": "Denver", "count": 9}],
                        "top_market_types": [{"type": "threshold", "count": 8}],
                        "sample_weather_titles": ["Will the highest temperature in Denver be 65F or higher?"],
                    }
                ]
            }
        )
    )
    surface_path.write_text(
        json.dumps(
            {
                "event_count": 1,
                "events": [
                    {
                        "event_key": "Denver|high|f|",
                        "market_count": 2,
                        "inconsistencies": [{"type": "threshold_monotonicity_violation", "severity": 0.07}],
                    }
                ],
                "artifacts": {"source_markets_json": "prebuilt-markets.json"},
            }
        )
    )

    result = _run_cli(
        "strategy-shortlist-report",
        "--reverse-engineering-json",
        str(reverse_path),
        "--run-id",
        "shortlist-surface-override",
        "--source",
        "fixture",
        "--limit",
        "5",
        "--event-surface-json",
        str(surface_path),
        "--output-json",
        str(out_path),
    )

    assert result.returncode == 0, result.stderr
    compact = json.loads(result.stdout)
    full = json.loads(out_path.read_text())
    assert compact["summary"]["surface_events"] == 1
    assert compact["shortlist"][0]["surface_inconsistency_count"] == 1
    assert "surface_anomaly" in compact["shortlist"][0]["reasons"]
    assert full["event_surface"]["artifacts"]["source_event_surface_json"] == str(surface_path)
    assert full["event_surface"]["artifacts"]["source_markets_json"] == "prebuilt-markets.json"


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
