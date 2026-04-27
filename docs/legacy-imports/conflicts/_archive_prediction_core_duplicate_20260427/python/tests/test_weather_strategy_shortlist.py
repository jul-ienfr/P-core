from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import weather_pm.cli as cli_module
from weather_pm.cli import build_strategy_shortlist_report_from_args, build_operator_refresh_report, enrich_shortlist_with_resolution_status
from weather_pm.operator_summary import build_profitable_accounts_operator_summary
from weather_pm.strategy_shortlist import build_operator_shortlist_report, build_strategy_shortlist


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
                "prediction_probability": 0.67,
                "market_price": 0.55,
                "edge_side": "buy",
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
    assert london["edge_sizing"] == {
        "prediction_probability": 0.67,
        "market_price": 0.55,
        "side": "buy",
        "raw_edge": 0.12,
        "net_edge": 0.108,
        "edge_bps": 1200,
        "net_edge_bps": 1080,
        "kelly_fraction": 0.2667,
        "suggested_fraction": 0.02,
        "recommendation": "buy",
    }
    assert london["entry_policy"] == {
        "name": "weather_station",
        "q_min": 0.08,
        "q_max": 0.92,
        "min_edge": 0.07,
        "min_confidence": 0.75,
        "max_spread": 0.08,
        "min_depth_usd": 50.0,
        "max_position_usd": 10.0,
    }
    assert london["entry_decision"] == {
        "policy": "weather_station",
        "enter": True,
        "action": "paper_trade_small",
        "side": "yes",
        "market_price": 0.55,
        "model_probability": 0.67,
        "confidence": 0.8,
        "edge_gross": 0.12,
        "edge_net_all_in": 0.108,
        "blocked_by": [],
        "size_hint_usd": 10.0,
    }
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
    assert london["weather_bookmaker_signal"]["strategy_id"] == "weather_bookmaker_v1"
    assert london["weather_bookmaker_signal"]["mode"] == "paper_only"
    assert london["weather_bookmaker_signal"]["trading_action"] == "none"
    assert london["weather_bookmaker_signal"]["features"]["decision"] == "PAPER_ADD"
    assert london["weather_bookmaker_signal"]["gate_status"] == "paper_add"


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


def test_build_strategy_shortlist_embeds_dynamic_sizing_with_surface_key_and_wallet_style() -> None:
    shortlist = build_strategy_shortlist(
        {
            "accounts": [
                {
                    "handle": "GridSharp",
                    "wallet_style": "breadth/grid small-ticket surface trader",
                    "top_cities": [{"city": "London", "count": 8}],
                    "weather_pnl_usd": 12000.0,
                }
            ]
        },
        {
            "opportunities": [
                {
                    "market_id": "london-20",
                    "question": "Will the highest temperature in London be 20°C or higher on April 25?",
                    "decision_status": "trade_small",
                    "prediction_probability": 0.67,
                    "market_price": 0.55,
                    "probability_edge": 0.12,
                    "all_in_cost_bps": 120.0,
                    "order_book_depth_usd": 900.0,
                    "confidence": 0.82,
                    "spread": 0.03,
                    "hours_to_resolution": 18.0,
                    "source_direct": True,
                }
            ]
        },
        {"events": [{"event_key": "London|high|c|April 25", "inconsistencies": []}]},
    )

    row = shortlist["shortlist"][0]
    assert row["surface_key"] == "London|April 25|high"
    assert row["dynamic_sizing"]["action"] == "OPEN"
    assert 5.0 <= row["dynamic_sizing"]["recommended_size_usdc"] <= 15.0
    assert row["dynamic_sizing"]["wallet_style_reference"] == "breadth/grid small-ticket surface trader"
    assert "grid_style_reference" in row["dynamic_sizing"]["reasons"]


def test_build_strategy_shortlist_dynamic_sizing_caps_repeated_surface_adds() -> None:
    shortlist = build_strategy_shortlist(
        {"accounts": []},
        {
            "opportunities": [
                {
                    "market_id": "dallas-70",
                    "question": "Will the highest temperature in Dallas be 70°F or higher on April 25?",
                    "decision_status": "trade_small",
                    "prediction_probability": 0.8,
                    "market_price": 0.62,
                    "probability_edge": 0.18,
                    "all_in_cost_bps": 300.0,
                    "order_book_depth_usd": 1500.0,
                    "confidence": 0.9,
                    "spread": 0.02,
                    "hours_to_resolution": 4.0,
                    "current_surface_exposure_usdc": 50.0,
                    "source_direct": True,
                }
            ]
        },
        {"events": []},
    )

    dynamic = shortlist["shortlist"][0]["dynamic_sizing"]
    assert dynamic["action"] == "HOLD_CAPPED"
    assert dynamic["recommended_size_usdc"] == 0.0
    assert "surface_cap_reached" in dynamic["reasons"]


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


def test_summary_recommends_watch_only_when_all_matched_markets_are_blocked() -> None:
    recommendation = build_profitable_accounts_operator_summary(
        classified_accounts_csv="classified.csv",
        reverse_engineering_json=_write_json_fixture(
            {
                "accounts": [
                    {
                        "handle": "SharpWx",
                        "classification": "weather specialist / weather-heavy",
                        "weather_pnl_usd": 4200,
                        "weather_volume_usd": 100000,
                        "top_cities": [{"city": "Dallas", "count": 8}],
                    }
                ]
            }
        ),
        operator_report_json=_write_json_fixture(
            {
                "summary": {"shortlisted": 1, "blocked_count": 1, "tradeable_count": 0},
                "watchlist": [
                    {
                        "market_id": "dallas-noquote",
                        "city": "Dallas",
                        "date": "April 27",
                        "matched_traders": ["SharpWx"],
                        "blocker": "missing_tradeable_quote",
                        "decision_status": "skip",
                    }
                ],
            }
        ),
    )["live_matched_profitable_weather_summary"]["operator_recommendation"]

    assert recommendation["status"] == "watch_only"
    assert recommendation["confidence"] == "profitable_weather_signal_but_no_executable_market"
    assert recommendation["next_actions"] == ["wait_for_executable_depth", "keep_polling_direct_resolution_sources"]


def _write_json_fixture(payload: dict) -> Path:
    import tempfile

    handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    with handle:
        json.dump(payload, handle)
    return Path(handle.name)


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


def test_cli_strategy_shortlist_report_can_embed_operator_action_snapshot(tmp_path: Path) -> None:
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
        "shortlist-operator",
        "--source",
        "fixture",
        "--limit",
        "5",
        "--operator-limit",
        "1",
        "--output-json",
        str(out_path),
    )

    assert result.returncode == 0, result.stderr
    compact = json.loads(result.stdout)
    full = json.loads(out_path.read_text())
    assert compact["operator"]["run_id"] == "shortlist-operator"
    assert compact["operator"]["summary"]["tradeable_count"] >= 1
    assert compact["operator"]["watchlist"][0]["direct_source"] == "noaa:KDEN"
    assert compact["operator"]["watchlist"][0]["source_latest_url"] == "https://api.weather.gov/stations/KDEN/observations/latest"
    assert len(compact["operator"]["watchlist"]) == 1
    assert full["operator"] == compact["operator"]



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


def test_build_operator_shortlist_report_extracts_actionable_snapshot() -> None:
    payload = {
        "summary": {
            "shortlisted": 3,
            "action_counts": {"paper_trade_watch_direct_station": 1, "review_surface_anomaly": 1, "watch_only": 1},
            "execution_blocker_counts": {"missing_tradeable_quote": 1},
        },
        "run_id": "operator-run",
        "source": "live",
        "artifacts": {"output_json": "/tmp/shortlist.json"},
        "shortlist": [
            {
                "rank": 1,
                "market_id": "denver-65",
                "question": "Will the highest temperature in Denver be 65F or higher?",
                "city": "Denver",
                "date": "April 25",
                "decision_status": "trade_small",
                "probability_edge": 0.14,
                "all_in_cost_bps": 85.4,
                "order_book_depth_usd": 920.0,
                "spread": 0.04,
                "hours_to_resolution": 6.5,
                "grade": "A",
                "score": 77.2,
                "source_direct": True,
                "source_provider": "noaa",
                "source_station_code": "KDEN",
                "source_latency_tier": "direct_latest",
                "source_latency_priority": 1,
                "source_polling_focus": "station_observations_latest",
                "source_latest_url": "https://api.weather.gov/stations/KDEN/observations/latest",
                "matched_traders": ["DenverSharp", "ColdMath"],
                "surface_inconsistency_count": 1,
                "surface_inconsistency_types": ["threshold_monotonicity_violation"],
                "execution_blocker": None,
                "action": "paper_trade_watch_direct_station",
                "next_actions": ["poll_direct_resolution_source", "inspect_event_surface_prices", "paper_order_with_limit_and_fill_tracking"],
                "reasons": ["tradeable_decision", "surface_anomaly", "profitable_trader_city", "direct_resolution_source"],
                "dynamic_sizing": {
                    "policy": "paper_weather_grid_default",
                    "action": "OPEN",
                    "recommended_size_usdc": 10.0,
                    "max_market_remaining_usdc": 15.0,
                    "max_surface_remaining_usdc": 50.0,
                    "max_total_remaining_usdc": 250.0,
                    "wallet_style_reference": "breadth/grid small-ticket surface trader",
                    "reasons": ["grid_style_reference"],
                },
            },
            {
                "rank": 2,
                "market_id": "dallas-70",
                "question": "Will the highest temperature in Dallas be 70F or higher?",
                "city": "Dallas",
                "decision_status": "skipped",
                "spread": 1.0,
                "hours_to_resolution": 25.34,
                "grade": "C",
                "score": 53.3,
                "source_direct": True,
                "matched_traders": [],
                "surface_inconsistency_count": 0,
                "execution_blocker": "missing_tradeable_quote",
                "source_polling_focus": "station_history_page",
                "source_latest_url": "https://www.wunderground.com/history/daily/us/tx/dallas/KDAL",
                "action": "watch_only",
                "next_actions": ["poll_direct_resolution_source", "wait_for_executable_depth"],
                "reasons": ["direct_resolution_source"],
            },
            {
                "rank": 3,
                "market_id": "dallas-extreme",
                "question": "Will the highest temperature in Dallas be 67F or below?",
                "city": "Dallas",
                "decision_status": "trade_small",
                "spread": 0.0,
                "hours_to_resolution": 25.34,
                "grade": "C",
                "score": 53.3,
                "source_direct": True,
                "matched_traders": ["DallasSharp"],
                "surface_inconsistency_count": 0,
                "execution_blocker": "extreme_price",
                "source_polling_focus": "station_history_page",
                "source_latest_url": "https://www.wunderground.com/history/daily/us/tx/dallas/KDAL",
                "action": "paper_trade_watch_direct_station",
                "next_actions": ["poll_direct_resolution_source", "skip_until_next_daily_market"],
                "reasons": ["tradeable_decision", "direct_resolution_source"],
            },
        ],
    }

    direct_shortlist = build_strategy_shortlist(
        {"accounts": []},
        {"opportunities": [payload["shortlist"][2]]},
        limit=1,
    )
    assert direct_shortlist["shortlist"][0]["next_actions"] == [
        "poll_direct_resolution_source",
        "paper_micro_order_with_strict_limit_and_fill_tracking",
    ]

    report = build_operator_shortlist_report(payload, limit=3)

    assert report["run_id"] == "operator-run"
    assert report["source"] == "live"
    assert report["summary"] == {
        "shortlisted": 3,
        "tradeable_count": 2,
        "direct_source_count": 3,
        "surface_anomaly_count": 1,
        "blocked_count": 2,
        "top_actions": ["paper_trade_watch_direct_station", "review_surface_anomaly", "watch_only"],
        "top_blockers": ["missing_tradeable_quote"],
    }
    assert report["operator_focus"] == [
        "paper_trade_watch_direct_station: 1",
        "missing_tradeable_quote: 1",
    ]
    assert report["watchlist"][0] == {
        "rank": 1,
        "market_id": "denver-65",
        "city": "Denver",
        "date": "April 25",
        "action": "paper_trade_watch_direct_station",
        "decision_status": "trade_small",
        "edge": 0.14,
        "all_in_cost_bps": 85.4,
        "depth_usd": 920.0,
        "direct_source": "noaa:KDEN",
        "matched_traders": ["DenverSharp", "ColdMath"],
        "anomalies": ["threshold_monotonicity_violation"],
        "blocker": None,
        "next": ["poll_direct_resolution_source", "inspect_event_surface_prices", "paper_order_with_limit_and_fill_tracking"],
        "polling_focus": "station_observations_latest",
        "source_latest_url": "https://api.weather.gov/stations/KDEN/observations/latest",
        "latency_tier": "direct_latest",
        "latency_priority": 1,
        "blocker_detail": None,
        "execution_diagnostic": {
            "spread": 0.04,
            "hours_to_resolution": 6.5,
            "grade": "A",
            "score": 77.2,
            "liquidity_state": "executable",
            "timing_state": "near_resolution",
        },
        "operator_entry_summary": {
            "enter": None,
            "action": None,
            "side": None,
            "price_window": None,
            "market_price": None,
            "model_probability": None,
            "edge_net_all_in": None,
            "size_hint_usd": None,
            "blocked_by": [],
            "dynamic_action": "OPEN",
            "dynamic_size_usdc": 10.0,
            "dynamic_reasons": ["grid_style_reference"],
        },
    }
    assert report["watchlist"][1]["blocker"] == "missing_tradeable_quote"
    assert report["watchlist"][1]["execution_diagnostic"] == {
        "spread": 1.0,
        "hours_to_resolution": 25.34,
        "grade": "C",
        "score": 53.3,
        "liquidity_state": "missing_quote",
        "timing_state": "next_day",
    }
    assert report["watchlist"][1]["blocker_detail"] == {
        "kind": "quote_missing",
        "severity": "blocking",
        "operator_action": "wait_for_executable_depth",
        "polling_focus": "station_history_page",
        "source_latest_url": "https://www.wunderground.com/history/daily/us/tx/dallas/KDAL",
    }
    assert report["watchlist"][2]["blocker"] == "extreme_price"
    assert report["watchlist"][2]["next"] == ["poll_direct_resolution_source", "paper_micro_order_with_strict_limit_and_fill_tracking"]
    assert report["watchlist"][2]["blocker_detail"] == {
        "kind": "market_state",
        "severity": "caution",
        "operator_action": "paper_micro_order_with_strict_limit_and_fill_tracking",
        "polling_focus": "station_history_page",
        "source_latest_url": "https://www.wunderground.com/history/daily/us/tx/dallas/KDAL",
    }
    assert report["watchlist"][2]["execution_diagnostic"]["liquidity_state"] == "executable_extreme_price"
    assert report["artifacts"] == {"source_shortlist_json": "/tmp/shortlist.json"}


def test_strategy_shortlist_report_embeds_resolution_status_before_operator_snapshot(monkeypatch, tmp_path: Path) -> None:
    reverse_path = tmp_path / "reverse.json"
    reverse_path.write_text(json.dumps({"accounts": []}))

    def fake_paper_cycle_opportunity_report_request(payload):
        assert payload["source"] == "live"
        return {
            "opportunities": [
                {
                    "market_id": "dallas-70",
                    "question": "Will the highest temperature in Dallas be 70F or higher on April 27?",
                    "decision_status": "trade_small",
                    "source_direct": True,
                }
            ]
        }

    monkeypatch.setattr(
        "prediction_core.server.paper_cycle_opportunity_report_request",
        fake_paper_cycle_opportunity_report_request,
    )
    monkeypatch.setattr("weather_pm.cli.resolution_status_for_market_id", _fake_resolution_status_for_dallas)

    args = type(
        "Args",
        (),
        {
            "reverse_engineering_json": reverse_path,
            "run_id": "live-resolution-status",
            "source": "live",
            "limit": 1,
            "requested_quantity": 1.0,
            "include_skipped": False,
            "tradeable_only": False,
            "min_edge": None,
            "max_cost_bps": None,
            "min_depth_usd": None,
            "event_surface_json": None,
            "resolution_date": "2026-04-25",
            "operator_limit": 1,
        },
    )()

    report = build_strategy_shortlist_report_from_args(args)

    row = report["shortlist"][0]
    assert row["resolution_status_date"] == "2026-04-27"
    assert row["source_history_url"] == "https://www.wunderground.com/history/daily/us/tx/dallas/KDAL/date/2026-04-27"
    assert report["operator"]["watchlist"][0]["resolution_status"]["latency"]["official"]["expected_lag_seconds"] == 3600


def _fake_resolution_status_for_dallas(market_id: str, *, source: str, date: str):
    assert market_id == "dallas-70"
    assert source == "live"
    return {
        "date": date,
        "latest_direct": {"available": True, "value": 71.2, "timestamp": "2026-04-27T12:00:00Z", "latency_tier": "direct_latest"},
        "official_daily_extract": {"available": False, "value": None, "timestamp": None, "latency_tier": "direct_history"},
        "provisional_outcome": "yes",
        "confirmed_outcome": "pending",
        "action_operator": "monitor_until_official_daily_extract",
        "source_route": {
            "provider": "wunderground",
            "station_code": "KDAL",
            "direct": True,
            "latency_tier": "direct_latest",
            "latency_priority": 1,
            "polling_focus": "station_history_page",
            "latest_url": "https://www.wunderground.com/history/daily/us/tx/dallas/KDAL",
            "history_url": f"https://www.wunderground.com/history/daily/us/tx/dallas/KDAL/date/{date}",
        },
        "latency": {
            "latest": {"polling_focus": "station_history_page", "direct": True},
            "official": {"polling_focus": "station_history_page", "expected_lag_seconds": 3600},
        },
    }


def test_enrich_shortlist_with_resolution_status_preserves_full_source_route(monkeypatch) -> None:
    calls: list[tuple[str, str, str]] = []

    def fake_resolution_status_for_market_id(market_id: str, *, source: str, date: str):
        calls.append((market_id, source, date))
        return {
            "date": date,
            "latest_direct": {"available": True, "value": 71.2, "timestamp": "2026-04-27T12:00:00Z", "latency_tier": "direct_latest"},
            "official_daily_extract": {"available": False, "value": None, "timestamp": None, "latency_tier": "direct_history"},
            "provisional_outcome": "yes",
            "confirmed_outcome": "pending",
            "action_operator": "monitor_until_official_daily_extract",
            "source_route": {
                "provider": "wunderground",
                "station_code": "KDAL",
                "direct": True,
                "latency_tier": "direct_latest",
                "latency_priority": 1,
                "polling_focus": "station_history_page",
                "latest_url": "https://www.wunderground.com/history/daily/us/tx/dallas/KDAL",
                "history_url": "https://www.wunderground.com/history/daily/us/tx/dallas/KDAL/date/2026-04-27",
            },
            "latency": {
                "latest": {"polling_focus": "station_history_page", "direct": True},
                "official": {"polling_focus": "station_history_page", "expected_lag_seconds": 3600},
            },
        }

    monkeypatch.setattr("weather_pm.cli.resolution_status_for_market_id", fake_resolution_status_for_market_id)
    report = {
        "shortlist": [
            {
                "market_id": "dallas-70",
                "date": "April 27",
                "source_latency_priority": 99,
                "source_polling_focus": "stale_focus",
            }
        ]
    }

    enriched = enrich_shortlist_with_resolution_status(report, source="live", date="2026-04-25")

    row = enriched["shortlist"][0]
    assert calls == [("dallas-70", "live", "2026-04-27")]
    assert row["resolution_status_date"] == "2026-04-27"
    assert row["source_direct"] is True
    assert row["source_provider"] == "wunderground"
    assert row["source_station_code"] == "KDAL"
    assert row["source_latency_tier"] == "direct_latest"
    assert row["source_latency_priority"] == 1
    assert row["source_polling_focus"] == "station_history_page"
    assert row["source_latest_url"] == "https://www.wunderground.com/history/daily/us/tx/dallas/KDAL"
    assert row["source_history_url"] == "https://www.wunderground.com/history/daily/us/tx/dallas/KDAL/date/2026-04-27"
    assert row["resolution_status"]["confirmed_outcome"] == "pending"
    assert row["resolution_latency"]["latest"]["polling_focus"] == "station_history_page"


def test_operator_report_preserves_resolution_status_latency_diagnostics() -> None:
    payload = {
        "summary": {"shortlisted": 1, "action_counts": {"paper_trade_watch_direct_station": 1}, "execution_blocker_counts": {}},
        "source": "live",
        "shortlist": [
            {
                "rank": 1,
                "market_id": "dallas-70",
                "city": "Dallas",
                "date": "April 27",
                "resolution_status_date": "2026-04-27",
                "decision_status": "trade_small",
                "paper_side": "yes",
                "paper_notional_usd": 5.0,
                "paper_shares": 17.24,
                "source_direct": True,
                "source_provider": "wunderground",
                "source_station_code": "KDAL",
                "source_polling_focus": "station_history_page",
                "source_latest_url": "https://www.wunderground.com/history/daily/us/tx/dallas/KDAL",
                "action": "paper_trade_watch_direct_station",
                "next_actions": ["poll_direct_resolution_source"],
                "resolution_status": {
                    "latest_direct": {"available": True, "value": 71.2},
                    "official_daily_extract": {"available": False},
                    "provisional_outcome": "yes",
                    "confirmed_outcome": "pending",
                    "action_operator": "monitor_until_official_daily_extract",
                },
                "resolution_latency": {
                    "latest": {"polling_focus": "station_history_page", "direct": True},
                    "official": {"polling_focus": "station_history_page", "expected_lag_seconds": 3600},
                },
            }
        ],
    }

    operator = build_operator_shortlist_report(payload, limit=1)

    status = operator["watchlist"][0]["resolution_status"]
    assert status["confirmed_outcome"] == "pending"
    assert status["latency"]["latest"]["polling_focus"] == "station_history_page"
    assert status["latency"]["official"]["expected_lag_seconds"] == 3600
    assert operator["watchlist"][0]["monitor_paper_resolution"] == {
        "endpoint": "/weather/monitor-paper-resolution",
        "method": "POST",
        "payload": {
            "market_id": "dallas-70",
            "source": "live",
            "date": "2026-04-27",
            "paper_side": "yes",
            "paper_notional_usd": 5.0,
            "paper_shares": 17.24,
        },
        "cli": "PYTHONPATH=python/src python3 -m weather_pm.cli monitor-paper-resolution --market-id dallas-70 --source live --date 2026-04-27 --paper-side yes --paper-notional-usd 5.0 --paper-shares 17.24",
        "mode": "paper_only",
        "trigger": "confirmed_outcome_pending",
    }


def test_profitable_accounts_operator_summary_bridges_accounts_to_live_watchlist(tmp_path: Path) -> None:
    reverse_path = tmp_path / "reverse.json"
    operator_path = tmp_path / "operator.json"
    csv_path = tmp_path / "classified.csv"
    csv_path.write_text("rank,userName\n1,DenverSharp\n")
    reverse_path.write_text(
        json.dumps(
            {
                "accounts": [
                    {
                        "rank": 1,
                        "handle": "DenverSharp",
                        "wallet": "0xdenver",
                        "weather_pnl_usd": 10000.0,
                        "weather_volume_usd": 200000.0,
                        "pnl_over_volume_pct": 5.0,
                        "classification": "weather specialist / weather-heavy",
                        "active_weather_positions": 4,
                        "recent_weather_activity": 20,
                        "recent_nonweather_activity": 0,
                        "recommended_use": "model_and_execution_template",
                        "profile_url": "https://polymarket.com/profile/0xdenver",
                        "sample_weather_titles": ["Will the highest temperature in Denver be 65F or higher?"],
                    },
                    {
                        "rank": 2,
                        "handle": "Generalist",
                        "weather_pnl_usd": 5000.0,
                        "classification": "profitable in weather but currently/recently generalist",
                    },
                ]
            }
        )
    )
    operator_path.write_text(
        json.dumps(
            {
                "summary": {"shortlisted": 1, "top_actions": ["paper_trade_watch_direct_station"], "top_blockers": []},
                "operator_focus": ["paper_trade_watch_direct_station: 1"],
                "watchlist": [
                    {
                        "rank": 1,
                        "market_id": "denver-65",
                        "city": "Denver",
                        "matched_traders": ["DenverSharp", "Generalist", "Unknown"],
                        "action": "paper_trade_watch_direct_station",
                        "blocker": "extreme_price",
                        "polling_focus": "station_observations_latest",
                        "source_latest_url": "https://api.weather.gov/stations/KDEN/observations/latest",
                        "edge_sizing": {
                            "prediction_probability": 0.67,
                            "market_price": 0.55,
                            "side": "buy",
                            "raw_edge": 0.12,
                            "net_edge": 0.108,
                            "edge_bps": 1200,
                            "net_edge_bps": 1080,
                            "kelly_fraction": 0.2667,
                            "suggested_fraction": 0.02,
                            "recommendation": "buy",
                        },
                        "entry_policy": {
                            "name": "weather_station",
                            "q_min": 0.08,
                            "q_max": 0.92,
                            "min_edge": 0.07,
                            "min_confidence": 0.75,
                            "max_spread": 0.08,
                            "min_depth_usd": 50.0,
                            "max_position_usd": 10.0,
                        },
                        "entry_decision": {
                            "policy": "weather_station",
                            "enter": True,
                            "action": "paper_trade_small",
                            "side": "yes",
                            "market_price": 0.55,
                            "model_probability": 0.67,
                            "confidence": 0.8,
                            "edge_gross": 0.12,
                            "edge_net_all_in": 0.108,
                            "blocked_by": [],
                            "size_hint_usd": 10.0,
                        },
                        "operator_entry_summary": {
                            "enter": True,
                            "action": "paper_trade_small",
                            "side": "yes",
                            "price_window": [0.08, 0.92],
                            "market_price": 0.55,
                            "model_probability": 0.67,
                            "edge_net_all_in": 0.108,
                            "size_hint_usd": 10.0,
                            "blocked_by": [],
                        },
                        "source_history_url": "https://api.weather.gov/stations/KDEN/observations",
                        "latency_tier": "direct_latest",
                        "latency_priority": 1,
                    }
                ],
            }
        )
    )

    summary = build_profitable_accounts_operator_summary(
        classified_accounts_csv=csv_path,
        reverse_engineering_json=reverse_path,
        operator_report_json=operator_path,
        priority_limit=5,
    )

    assert summary["classified_account_counts"] == {
        "profitable in weather but currently/recently generalist": 1,
        "weather specialist / weather-heavy": 1,
    }
    assert summary["priority_weather_accounts"][0]["handle"] == "DenverSharp"
    assert summary["live_watchlist"][0]["matched_weather_heavy_traders"] == ["DenverSharp"]
    assert summary["live_watchlist"][0]["matched_signal_only_traders"] == ["Generalist"]
    assert summary["live_watchlist"][0]["matched_profitable_weather_count"] == 2
    assert summary["live_watchlist"][0]["operator_verdict"] == {
        "status": "paper_micro",
        "confidence": "high_signal_cautious_execution",
        "reason": "profitable_weather_accounts_match_but_extreme_price_requires_micro_paper",
        "recommended_size": "micro_paper_only",
    }
    assert summary["live_market_signal_cards"] == [
        {
            "market_id": "denver-65",
            "city": "Denver",
            "date": None,
            "action": "paper_trade_watch_direct_station",
            "blocker": "extreme_price",
            "matched_profitable_weather_count": 2,
            "weather_heavy_count": 1,
            "signal_only_count": 1,
            "top_matched_accounts": [
                {"handle": "DenverSharp", "weather_pnl_usd": 10000.0, "pnl_over_volume_pct": 5.0},
                {"handle": "Generalist", "weather_pnl_usd": 5000.0, "pnl_over_volume_pct": 0.0},
            ],
            "operator_verdict": {
                "status": "paper_micro",
                "confidence": "high_signal_cautious_execution",
                "reason": "profitable_weather_accounts_match_but_extreme_price_requires_micro_paper",
                "recommended_size": "micro_paper_only",
            },
            "next": [],
            "source_latest_url": "https://api.weather.gov/stations/KDEN/observations/latest",
            "edge_sizing": {
                "prediction_probability": 0.67,
                "market_price": 0.55,
                "side": "buy",
                "raw_edge": 0.12,
                "net_edge": 0.108,
                "edge_bps": 1200,
                "net_edge_bps": 1080,
                "kelly_fraction": 0.2667,
                "suggested_fraction": 0.02,
                "recommendation": "buy",
            },
            "entry_policy": {
                "name": "weather_station",
                "q_min": 0.08,
                "q_max": 0.92,
                "min_edge": 0.07,
                "min_confidence": 0.75,
                "max_spread": 0.08,
                "min_depth_usd": 50.0,
                "max_position_usd": 10.0,
            },
            "entry_decision": {
                "policy": "weather_station",
                "enter": True,
                "action": "paper_trade_small",
                "side": "yes",
                "market_price": 0.55,
                "model_probability": 0.67,
                "confidence": 0.8,
                "edge_gross": 0.12,
                "edge_net_all_in": 0.108,
                "blocked_by": [],
                "size_hint_usd": 10.0,
            },
            "operator_entry_summary": {
                "enter": True,
                "action": "paper_trade_small",
                "side": "yes",
                "price_window": [0.08, 0.92],
                "market_price": 0.55,
                "model_probability": 0.67,
                "edge_net_all_in": 0.108,
                "size_hint_usd": 10.0,
                "blocked_by": [],
            },
            "source_history_url": "https://api.weather.gov/stations/KDEN/observations",
            "polling_focus": "station_observations_latest",
            "latency_tier": "direct_latest",
            "latency_priority": 1,
        }
    ]
    assert summary["discord_operator_brief"] == (
        "Météo Polymarket: 1 marché live avec comptes météo rentables. Reco globale: paper_micro_only.\n"
        "- denver-65 — Denver — 2 comptes (1 heavy), blocker=extreme_price, verdict=paper_micro, "
        "top=DenverSharp $10,000.00 / Generalist $5,000.00"
    )


def test_cli_profitable_accounts_operator_summary_writes_json_and_prints_compact_payload(tmp_path: Path) -> None:
    reverse_path = tmp_path / "reverse.json"
    operator_path = tmp_path / "operator.json"
    csv_path = tmp_path / "classified.csv"
    out_path = tmp_path / "summary.json"
    csv_path.write_text("rank,userName\n1,DenverSharp\n")
    reverse_path.write_text(
        json.dumps(
            {
                "accounts": [
                    {
                        "rank": 1,
                        "handle": "DenverSharp",
                        "weather_pnl_usd": 10000.0,
                        "weather_volume_usd": 200000.0,
                        "pnl_over_volume_pct": 5.0,
                        "classification": "weather specialist / weather-heavy",
                        "active_weather_positions": 4,
                        "recent_weather_activity": 20,
                        "sample_weather_titles": [],
                    }
                ]
            }
        )
    )
    operator_path.write_text(
        json.dumps(
            {
                "summary": {"shortlisted": 1, "top_actions": ["paper_trade_watch_direct_station"], "top_blockers": ["extreme_price"]},
                "watchlist": [{"rank": 1, "market_id": "denver-65", "matched_traders": ["DenverSharp"]}],
            }
        )
    )

    result = _run_cli(
        "profitable-accounts-operator-summary",
        "--classified-csv",
        str(csv_path),
        "--reverse-engineering-json",
        str(reverse_path),
        "--operator-report-json",
        str(operator_path),
        "--output-json",
        str(out_path),
    )

    assert result.returncode == 0, result.stderr
    compact = json.loads(result.stdout)
    full = json.loads(out_path.read_text())
    assert compact["output_json"] == str(out_path)
    assert compact["priority_account_count"] == 1
    assert compact["live_matched_profitable_weather_count"] == 1
    assert compact["live_top_blockers"] == ["extreme_price"]
    assert full["live_watchlist"][0]["matched_weather_heavy_traders"] == ["DenverSharp"]


def test_build_operator_refresh_report_refreshes_existing_shortlist_and_rebuilds_operator(monkeypatch) -> None:
    calls: list[tuple[str, str, str]] = []

    def fake_resolution_status_for_market_id(market_id: str, *, source: str, date: str):
        calls.append((market_id, source, date))
        return _fake_resolution_status_for_dallas(market_id, source=source, date=date)

    monkeypatch.setattr("weather_pm.cli.resolution_status_for_market_id", fake_resolution_status_for_market_id)
    payload = {
        "run_id": "saved-run",
        "source": "live",
        "summary": {"shortlisted": 1, "action_counts": {"paper_trade_watch_direct_station": 1}, "execution_blocker_counts": {}},
        "shortlist": [
            {
                "rank": 1,
                "market_id": "dallas-70",
                "city": "Dallas",
                "date": "April 27",
                "decision_status": "trade_small",
                "paper_side": "yes",
                "paper_notional_usd": 5.0,
                "paper_shares": 17.24,
                "action": "paper_trade_watch_direct_station",
                "next_actions": ["poll_direct_resolution_source"],
            }
        ],
    }

    refreshed = build_operator_refresh_report(payload, source="live", resolution_date="2026-04-25", operator_limit=1, skip_orderbook=True)

    assert calls == [("dallas-70", "live", "2026-04-27")]
    assert refreshed["summary"] == {
        "paper_only": True,
        "input_kind": "shortlist",
        "rows": 1,
        "resolution_status_refreshed": 1,
        "execution_snapshot_refreshed": 0,
        "execution_snapshot_errors": 0,
        "operator_watchlist_rows": 1,
    }
    assert refreshed["shortlist"][0]["resolution_status"]["confirmed_outcome"] == "pending"
    assert refreshed["shortlist"][0]["source_provider"] == "wunderground"
    watch = refreshed["operator"]["watchlist"][0]
    assert watch["resolution_status"]["confirmed_outcome"] == "pending"
    assert watch["monitor_paper_resolution"]["payload"] == {
        "market_id": "dallas-70",
        "source": "live",
        "date": "2026-04-27",
        "paper_side": "yes",
        "paper_notional_usd": 5.0,
        "paper_shares": 17.24,
    }
    assert refreshed["artifacts"] == {"source_operator_refresh_input": None}


def test_build_operator_refresh_report_refreshes_execution_snapshot(monkeypatch) -> None:
    monkeypatch.setattr("weather_pm.cli.resolution_status_for_market_id", _fake_resolution_status_for_dallas)

    monkeypatch.setattr(
        cli_module,
        "fetch_market_execution_snapshot",
        lambda market_id: {
            "market_id": market_id,
            "question": "Will the highest temperature in Dallas be 70°F or higher on April 27?",
            "book": {
                "yes": {"best_bid": 0.41, "best_ask": 0.43, "bid_depth_usd": 82.0, "ask_depth_usd": 129.0},
                "no": {"best_bid": 0.56, "best_ask": 0.58, "bid_depth_usd": 91.0, "ask_depth_usd": 114.0},
            },
            "spread": {"yes": 0.02, "no": 0.02},
            "fetched_at": "2026-04-25T18:00:00+00:00",
        },
    )
    payload = {
        "run_id": "saved-run",
        "source": "live",
        "summary": {"shortlisted": 1, "action_counts": {"paper_trade_watch_direct_station": 1}, "execution_blocker_counts": {}},
        "shortlist": [
            {
                "rank": 1,
                "market_id": "dallas-70",
                "city": "Dallas",
                "date": "April 27",
                "decision_status": "trade_small",
                "action": "paper_trade_watch_direct_station",
                "next_actions": ["poll_direct_resolution_source"],
            }
        ],
    }

    refreshed = build_operator_refresh_report(payload, source="live", resolution_date="2026-04-25", operator_limit=1)

    assert refreshed["summary"]["execution_snapshot_refreshed"] == 1
    assert refreshed["summary"]["execution_snapshot_errors"] == 0
    snapshot = refreshed["shortlist"][0]["execution_snapshot"]
    assert snapshot["best_ask_no"] == 0.58
    assert snapshot["spread_yes"] == 0.02
    assert snapshot["no_ask_depth_usd"] == 114.0
    watch = refreshed["operator"]["watchlist"][0]
    assert watch["execution_snapshot"] == snapshot
    assert watch["execution_diagnostic"]["liquidity_state"] == "executable"
    assert watch["execution_diagnostic"]["spread"] == 0.02
    assert watch["execution_diagnostic"]["depth_usd"] == 114.0
    assert watch["execution_diagnostic"]["fetched_at"] == "2026-04-25T18:00:00+00:00"


def test_operator_shortlist_preserves_execution_snapshot_and_updates_diagnostic() -> None:
    report = build_operator_shortlist_report(
        {
            "summary": {"shortlisted": 1, "action_counts": {"paper_trade_watch_direct_station": 1}, "execution_blocker_counts": {}},
            "shortlist": [
                {
                    "rank": 1,
                    "market_id": "dallas-70",
                    "city": "Dallas",
                    "decision_status": "trade_small",
                    "action": "paper_trade_watch_direct_station",
                    "order_book_depth_usd": 10.0,
                    "execution_snapshot": {
                        "best_bid_yes": 0.41,
                        "best_ask_yes": 0.43,
                        "best_bid_no": 0.56,
                        "best_ask_no": 0.58,
                        "spread_yes": 0.02,
                        "spread_no": 0.02,
                        "yes_ask_depth_usd": 129.0,
                        "no_ask_depth_usd": 114.0,
                        "fetched_at": "2026-04-25T18:00:00+00:00",
                    },
                }
            ],
        },
        limit=1,
    )

    watch = report["watchlist"][0]
    assert watch["execution_snapshot"]["best_ask_no"] == 0.58
    assert watch["execution_diagnostic"]["liquidity_state"] == "executable"
    assert watch["execution_diagnostic"]["spread"] == 0.02
    assert watch["execution_diagnostic"]["depth_usd"] == 114.0


def test_cli_operator_refresh_skip_orderbook_does_not_fetch_execution_snapshot(tmp_path: Path) -> None:
    shortlist_path = tmp_path / "shortlist.json"
    out_path = tmp_path / "refresh.json"
    shortlist_path.write_text(
        json.dumps(
            {
                "run_id": "saved-run",
                "source": "fixture",
                "summary": {"shortlisted": 1, "action_counts": {"paper_trade_watch_direct_station": 1}, "execution_blocker_counts": {}},
                "shortlist": [
                    {
                        "rank": 1,
                        "market_id": "denver-high-65",
                        "city": "Denver",
                        "date": "April 25",
                        "decision_status": "trade_small",
                        "action": "paper_trade_watch_direct_station",
                        "next_actions": ["poll_direct_resolution_source"],
                    }
                ],
            }
        )
    )

    result = _run_cli(
        "operator-refresh",
        "--input-json",
        str(shortlist_path),
        "--source",
        "fixture",
        "--resolution-date",
        "2026-04-25",
        "--operator-limit",
        "1",
        "--skip-orderbook",
        "--output-json",
        str(out_path),
    )

    assert result.returncode == 0, result.stderr
    written = json.loads(out_path.read_text())
    assert written["summary"]["resolution_status_refreshed"] == 1
    assert written["summary"]["execution_snapshot_refreshed"] == 0
    assert written["summary"]["execution_snapshot_errors"] == 0
    assert "execution_snapshot" not in written["shortlist"][0]
    assert "execution_snapshot" not in written["operator"]["watchlist"][0]


def test_cli_operator_refresh_reads_saved_shortlist_writes_wrapper_and_prints_compact(monkeypatch, tmp_path: Path) -> None:
    shortlist_path = tmp_path / "shortlist.json"
    out_path = tmp_path / "refresh.json"
    shortlist_path.write_text(
        json.dumps(
            {
                "run_id": "saved-run",
                "source": "fixture",
                "summary": {"shortlisted": 1, "action_counts": {"paper_trade_watch_direct_station": 1}, "execution_blocker_counts": {}},
                "shortlist": [
                    {
                        "rank": 1,
                        "market_id": "denver-high-65",
                        "city": "Denver",
                        "date": "April 25",
                        "decision_status": "trade_small",
                        "paper_side": "yes",
                        "paper_notional_usd": 5.0,
                        "paper_shares": 10.0,
                        "action": "paper_trade_watch_direct_station",
                        "next_actions": ["poll_direct_resolution_source"],
                    }
                ],
            }
        )
    )

    result = _run_cli(
        "operator-refresh",
        "--input-json",
        str(shortlist_path),
        "--source",
        "fixture",
        "--resolution-date",
        "2026-04-25",
        "--operator-limit",
        "1",
        "--output-json",
        str(out_path),
    )

    assert result.returncode == 0, result.stderr
    compact = json.loads(result.stdout)
    written = json.loads(out_path.read_text())
    assert compact == {
        "summary": written["summary"],
        "operator": written["operator"],
        "artifacts": {"source_operator_refresh_input": str(shortlist_path), "output_json": str(out_path)},
    }
    assert written["summary"]["paper_only"] is True
    assert written["summary"]["resolution_status_refreshed"] == 1
    assert written["operator"]["watchlist"][0]["monitor_paper_resolution"]["payload"]["market_id"] == "denver-high-65"


def test_cli_operator_shortlist_reads_saved_shortlist_and_outputs_action_report(tmp_path: Path) -> None:
    shortlist_path = tmp_path / "shortlist.json"
    out_path = tmp_path / "operator-refreshed.json"
    shortlist_path.write_text(
        json.dumps(
            {
                "run_id": "saved-run",
                "source": "live",
                "summary": {
                    "shortlisted": 1,
                    "action_counts": {"paper_trade_watch_direct_station": 1},
                    "execution_blocker_counts": {"extreme_price": 1},
                },
                "artifacts": {"output_json": str(shortlist_path)},
                "shortlist": [
                    {
                        "rank": 1,
                        "market_id": "denver-65",
                        "city": "Denver",
                        "decision_status": "trade",
                        "probability_edge": 0.22,
                        "all_in_cost_bps": 42.0,
                        "order_book_depth_usd": 1200.0,
                        "entry_policy": {
                            "name": "weather_station",
                            "q_min": 0.08,
                            "q_max": 0.92,
                            "min_edge": 0.07,
                            "min_confidence": 0.75,
                            "max_spread": 0.08,
                            "min_depth_usd": 50.0,
                            "max_position_usd": 10.0,
                        },
                        "entry_decision": {
                            "policy": "weather_station",
                            "enter": True,
                            "action": "paper_trade_small",
                            "side": "yes",
                            "market_price": 0.55,
                            "model_probability": 0.67,
                            "confidence": 0.81,
                            "edge_gross": 0.12,
                            "edge_net_all_in": 0.108,
                            "blocked_by": [],
                            "size_hint_usd": 10.0,
                        },
                        "edge_sizing": {
                            "prediction_probability": 0.67,
                            "market_price": 0.55,
                            "side": "buy",
                            "raw_edge": 0.12,
                            "net_edge": 0.108,
                            "edge_bps": 1200,
                            "net_edge_bps": 1080,
                            "kelly_fraction": 0.2667,
                            "suggested_fraction": 0.02,
                            "recommendation": "buy",
                        },
                        "source_direct": True,
                        "source_provider": "noaa",
                        "source_station_code": "KDEN",
                        "matched_traders": ["DenverSharp"],
                        "surface_inconsistency_types": [],
                        "execution_blocker": "extreme_price",
                        "action": "paper_trade_watch_direct_station",
                        "next_actions": ["poll_direct_resolution_source", "skip_until_next_daily_market"],
                    }
                ],
            }
        )
    )

    result = _run_cli("operator-shortlist", "--shortlist-json", str(shortlist_path), "--limit", "1", "--output-json", str(out_path))

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    written = json.loads(out_path.read_text())
    assert payload == written
    assert payload["run_id"] == "saved-run"
    assert payload["summary"]["tradeable_count"] == 1
    assert payload["watchlist"][0]["direct_source"] == "noaa:KDEN"
    assert payload["watchlist"][0]["edge_sizing"] == {
        "prediction_probability": 0.67,
        "market_price": 0.55,
        "side": "buy",
        "raw_edge": 0.12,
        "net_edge": 0.108,
        "edge_bps": 1200,
        "net_edge_bps": 1080,
        "kelly_fraction": 0.2667,
        "suggested_fraction": 0.02,
        "recommendation": "buy",
    }
    assert payload["watchlist"][0]["operator_entry_summary"] == {
        "enter": True,
        "action": "paper_trade_small",
        "side": "yes",
        "price_window": [0.08, 0.92],
        "market_price": 0.55,
        "model_probability": 0.67,
        "edge_net_all_in": 0.108,
        "size_hint_usd": 10.0,
        "blocked_by": [],
    }
    assert payload["watchlist"][0]["source_history_url"] == "https://api.weather.gov/stations/KDEN/observations"
    assert payload["watchlist"][0]["resolution_status"] == {
        "latest_direct": {"available": True, "value": 66.0},
        "official_daily_extract": {"available": False, "value": None},
        "provisional_outcome": {"status": "yes", "basis": "latest_direct"},
        "confirmed_outcome": {"status": "pending", "basis": "official_daily_extract"},
        "action_operator": "monitor_until_official_daily_extract",
        "source_latest_url": "https://api.weather.gov/stations/KDEN/observations/latest",
        "source_history_url": "https://api.weather.gov/stations/KDEN/observations",
    }
    assert payload["watchlist"][0]["next"] == ["poll_direct_resolution_source", "paper_micro_order_with_strict_limit_and_fill_tracking"]
    assert payload["watchlist"][0]["blocker_detail"]["severity"] == "caution"
    assert payload["artifacts"] == {"source_shortlist_json": str(shortlist_path), "output_json": str(out_path)}
