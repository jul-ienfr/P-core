from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from unittest.mock import patch


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


def test_paper_cycle_opportunity_report_ranks_tradeable_real_net_interest_and_stable_fields() -> None:
    from prediction_core.server import paper_cycle_opportunity_report_request

    cycle_payload = {
        "run_id": "report-run-1",
        "source": "live",
        "limit": 4,
        "summary": {"selected": 4, "scored": 3, "scoreable": 3, "traded": 1, "skipped": 3, "skipped_reasons": {"decision_not_tradeable": 2, "missing_tradeable_quote": 1}},
        "markets": [
            {
                "market_id": "skip-high-score",
                "market": {"id": "skip-high-score", "question": "Skip high score?", "spread": 0.01, "hours_to_resolution": 8.0},
                "decision_status": "watchlist",
                "score_bundle": {
                    "edge": {"probability_edge": 0.31},
                    "score": {"total_score": 99.0, "grade": "A"},
                    "decision": {"reasons": ["not quite tradeable"]},
                    "execution": {"spread": 0.01, "all_in_cost_bps": 100.0, "order_book_depth_usd": 1000.0, "hours_to_resolution": 8.0},
                },
                "skip_reason": "decision_not_tradeable",
            },
            {
                "market_id": "trade-lower-cost",
                "market": {"id": "trade-lower-cost", "question": "Trade lower cost?", "spread": 0.02, "hours_to_resolution": 6.0},
                "decision_status": "trade_small",
                "score_bundle": {
                    "edge": {"probability_edge": 0.20},
                    "score": {"total_score": 80.0, "grade": "B"},
                    "decision": {"reasons": ["small trade"]},
                    "execution": {"spread": 0.02, "all_in_cost_bps": 150.0, "order_book_depth_usd": 900.0, "hours_to_resolution": 6.0},
                    "source_route": {
                        "provider": "noaa",
                        "station_code": "KDEN",
                        "direct": True,
                        "latency_tier": "direct_latest",
                        "latency_priority": "direct_source_low_latency",
                        "polling_focus": "station_observations_latest",
                        "latest_url": "https://api.weather.gov/stations/KDEN/observations/latest",
                    },
                },
            },
            {
                "market_id": "trade-expensive",
                "market": {"id": "trade-expensive", "question": "Trade expensive?", "spread": 0.12, "hours_to_resolution": 4.0},
                "decision_status": "trade",
                "score_bundle": {
                    "edge": {"probability_edge": 0.22},
                    "score": {"total_score": 82.0, "grade": "A"},
                    "decision": {"reasons": ["full trade"]},
                    "execution": {"spread": 0.12, "all_in_cost_bps": 1200.0, "order_book_depth_usd": 1100.0, "hours_to_resolution": 4.0},
                },
            },
            {
                "market_id": "unquoted",
                "market": {"id": "unquoted", "question": "Unquoted?", "spread": None, "hours_to_resolution": 5.0},
                "decision_status": "skipped",
                "score_bundle": None,
                "skip_reason": "missing_tradeable_quote",
            },
        ],
    }

    with patch("prediction_core.server.live_paper_cycle_request", return_value=cycle_payload) as cycle_mock:
        report = paper_cycle_opportunity_report_request({"run_id": "report-run-1", "source": "live", "limit": 4, "include_skipped": True})

    cycle_mock.assert_called_once_with({"run_id": "report-run-1", "source": "live", "limit": 4, "include_skipped": True})
    assert report["summary"] == cycle_payload["summary"]
    assert [item["market_id"] for item in report["opportunities"]] == [
        "trade-lower-cost",
        "trade-expensive",
        "skip-high-score",
        "unquoted",
    ]
    assert [item["rank"] for item in report["opportunities"]] == [1, 2, 3, 4]
    assert report["opportunities"][0] == {
        "rank": 1,
        "market_id": "trade-lower-cost",
        "question": "Trade lower cost?",
        "decision_status": "trade_small",
        "score": 80.0,
        "grade": "B",
        "probability_edge": 0.2,
        "spread": 0.02,
        "all_in_cost_bps": 150.0,
        "order_book_depth_usd": 900.0,
        "hours_to_resolution": 6.0,
        "source_provider": "noaa",
        "source_station_code": "KDEN",
        "source_direct": True,
        "source_latency_tier": "direct_latest",
        "source_latency_priority": "direct_source_low_latency",
        "source_polling_focus": "station_observations_latest",
        "source_latest_url": "https://api.weather.gov/stations/KDEN/observations/latest",
        "source_route": {
            "provider": "noaa",
            "station_code": "KDEN",
            "direct": True,
            "latency_tier": "direct_latest",
            "latency_priority": "direct_source_low_latency",
            "polling_focus": "station_observations_latest",
            "latest_url": "https://api.weather.gov/stations/KDEN/observations/latest",
            "history_url": None,
            "manual_review_needed": False,
        },
        "reasons": ["small trade"],
    }
    assert report["opportunities"][2]["skip_reason"] == "decision_not_tradeable"
    assert set(report["opportunities"][0]) == {
        "rank",
        "market_id",
        "question",
        "decision_status",
        "score",
        "grade",
        "probability_edge",
        "spread",
        "all_in_cost_bps",
        "order_book_depth_usd",
        "hours_to_resolution",
        "source_provider",
        "source_station_code",
        "source_direct",
        "source_latency_tier",
        "source_latency_priority",
        "source_polling_focus",
        "source_latest_url",
        "source_route",
        "reasons",
    }


def test_paper_cycle_report_cli_outputs_compact_fixture_json() -> None:
    result = _run_cli("paper-cycle-report", "--run-id", "fixture-report", "--source", "fixture", "--limit", "5")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["run_id"] == "fixture-report"
    assert payload["source"] == "fixture"
    assert payload["summary"]["selected"] == 3
    assert [item["rank"] for item in payload["opportunities"]] == [1, 2]
    assert payload["opportunities"][0]["decision_status"] == "trade"
    assert payload["opportunities"][0]["market_id"] == "denver-high-65"
    assert all(item["decision_status"] in {"trade", "trade_small"} for item in payload["opportunities"])
    assert "score_bundle" not in payload["opportunities"][0]
    assert "simulation" not in payload["opportunities"][0]
    assert set(payload["opportunities"][0]) == {
        "rank",
        "market_id",
        "question",
        "decision_status",
        "score",
        "grade",
        "probability_edge",
        "spread",
        "all_in_cost_bps",
        "order_book_depth_usd",
        "hours_to_resolution",
        "source_provider",
        "source_station_code",
        "source_direct",
        "source_latency_tier",
        "source_latency_priority",
        "source_polling_focus",
        "source_latest_url",
        "source_route",
        "reasons",
    }


def test_paper_cycle_report_cli_can_output_tradeable_only_fixture_candidates() -> None:
    result = _run_cli("paper-cycle-report", "--run-id", "fixture-report", "--source", "fixture", "--limit", "5", "--tradeable-only")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["opportunities"]
    assert all(item["decision_status"] in {"trade", "trade_small"} for item in payload["opportunities"])
    assert len(payload["opportunities"]) < payload["summary"]["selected"]


def test_paper_cycle_opportunity_report_hides_non_tradeable_noise_by_default() -> None:
    from prediction_core.server import paper_cycle_opportunity_report_request

    cycle_payload = _threshold_cycle_payload()

    with patch("prediction_core.server.live_paper_cycle_request", return_value=cycle_payload):
        report = paper_cycle_opportunity_report_request({"run_id": "report-run-filter", "source": "live", "limit": 5})

    assert {item["market_id"] for item in report["opportunities"]} == {"tradeable", "thin-depth", "expensive"}
    assert report["summary"] == cycle_payload["summary"]


def test_paper_cycle_opportunity_report_can_include_skipped_noise_for_diagnostics() -> None:
    from prediction_core.server import paper_cycle_opportunity_report_request

    cycle_payload = _threshold_cycle_payload()

    with patch("prediction_core.server.live_paper_cycle_request", return_value=cycle_payload):
        report = paper_cycle_opportunity_report_request({"run_id": "report-run-filter", "source": "live", "limit": 5, "include_skipped": True})

    assert {item["market_id"] for item in report["opportunities"]} == {"tradeable", "thin-depth", "expensive", "watchlist", "unquoted"}
    assert report["summary"] == cycle_payload["summary"]


def test_paper_cycle_opportunity_report_applies_configurable_thresholds_without_changing_summary() -> None:
    from prediction_core.server import paper_cycle_opportunity_report_request

    cycle_payload = _threshold_cycle_payload()

    with patch("prediction_core.server.live_paper_cycle_request", return_value=cycle_payload):
        report = paper_cycle_opportunity_report_request(
            {
                "run_id": "report-run-thresholds",
                "source": "live",
                "limit": 5,
                "tradeable_only": True,
                "min_edge": 0.10,
                "max_cost_bps": 200.0,
                "min_depth_usd": 200.0,
            }
        )

    assert [item["market_id"] for item in report["opportunities"]] == ["tradeable"]
    assert report["summary"] == cycle_payload["summary"]


def test_paper_cycle_report_cli_accepts_threshold_arguments() -> None:
    result = _run_cli(
        "paper-cycle-report",
        "--run-id",
        "fixture-report",
        "--source",
        "fixture",
        "--limit",
        "5",
        "--tradeable-only",
        "--min-edge",
        "0.01",
        "--max-cost-bps",
        "1000",
        "--min-depth-usd",
        "0",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["opportunities"]
    assert all(item["decision_status"] in {"trade", "trade_small"} for item in payload["opportunities"])


def test_paper_cycle_report_cli_can_include_skipped_diagnostics() -> None:
    result = _run_cli("paper-cycle-report", "--run-id", "fixture-report", "--source", "fixture", "--limit", "5", "--include-skipped")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert any(item["decision_status"] not in {"trade", "trade_small"} for item in payload["opportunities"])



def test_live_paper_cycle_applies_conservative_post_score_filters() -> None:
    from prediction_core.server import live_paper_cycle_request

    markets = [
        {
            "id": "clean-trade",
            "question": "Will the highest temperature in Denver be 64F or higher?",
            "yes_price": 0.42,
            "best_bid": 0.41,
            "best_ask": 0.43,
            "spread": 0.02,
            "hours_to_resolution": 10.0,
            "volume": 10000.0,
        },
        {
            "id": "too-wide",
            "question": "Will the highest temperature in Denver be 65F or higher?",
            "yes_price": 0.45,
            "best_bid": 0.40,
            "best_ask": 0.49,
            "spread": 0.09,
            "hours_to_resolution": 10.0,
            "volume": 10000.0,
        },
        {
            "id": "too-small",
            "question": "Will the highest temperature in Denver be 66F or higher?",
            "yes_price": 0.45,
            "best_bid": 0.44,
            "best_ask": 0.46,
            "spread": 0.02,
            "hours_to_resolution": 10.0,
            "volume": 10000.0,
        },
        {
            "id": "too-extreme",
            "question": "Will the highest temperature in Denver be 67F or higher?",
            "yes_price": 0.995,
            "best_bid": 0.99,
            "best_ask": 0.995,
            "spread": 0.005,
            "hours_to_resolution": 10.0,
            "volume": 10000.0,
        },
    ]
    bundles = {
        "clean-trade": _score_bundle("trade_small", fillable_size_usd=100.0, spread=0.02, slippage_risk="low"),
        "too-wide": _score_bundle("trade", fillable_size_usd=100.0, spread=0.09, slippage_risk="low"),
        "too-small": _score_bundle("trade", fillable_size_usd=10.0, spread=0.02, slippage_risk="low"),
        "too-extreme": _score_bundle("trade", fillable_size_usd=100.0, spread=0.005, slippage_risk="low"),
    }

    with patch("prediction_core.server.list_weather_markets", return_value=markets), patch(
        "prediction_core.server._score_market_from_market_id", side_effect=lambda market_id, **_: bundles[market_id]
    ):
        cycle = live_paper_cycle_request({"run_id": "post-score-filters", "source": "live", "limit": 4, "requested_quantity": 1.0})

    assert cycle["summary"]["filtered_out"] == 3
    assert cycle["summary"]["filtered_reasons"] == {"extreme_price": 1, "tiny_fillable_size": 1, "wide_spread": 1}
    assert cycle["summary"]["traded"] == 1
    assert {item["market_id"]: item.get("skip_reason") for item in cycle["markets"]} == {
        "clean-trade": None,
        "too-wide": "wide_spread",
        "too-small": "tiny_fillable_size",
        "too-extreme": "extreme_price",
    }


def test_live_paper_cycle_reports_missing_quote_before_extreme_price_for_unfillable_markets() -> None:
    from prediction_core.server import live_paper_cycle_request

    markets = [
        {
            "id": "unfillable-extreme",
            "question": "Will the highest temperature in Dallas be 67°F or below on April 26?",
            "yes_price": 0.0005,
            "best_bid": 0.0,
            "best_ask": 0.999,
            "hours_to_resolution": 26.0,
            "volume": 10000.0,
        }
    ]
    bundle = _score_bundle(
        "skip",
        fillable_size_usd=0.0,
        spread=1.0,
        slippage_risk="high",
        best_effort_reason="missing_tradeable_quote",
        reasons=["skip: missing tradeable quote"],
    )

    with patch("prediction_core.server.list_weather_markets", return_value=markets), patch(
        "prediction_core.server._score_market_from_market_id", return_value=bundle
    ):
        cycle = live_paper_cycle_request({"run_id": "missing-quote-priority", "source": "live", "limit": 1, "requested_quantity": 1.0})

    assert cycle["summary"]["filtered_reasons"] == {"missing_tradeable_quote": 1}
    assert cycle["markets"][0]["skip_reason"] == "missing_tradeable_quote"


def _score_bundle(
    status: str,
    *,
    fillable_size_usd: float,
    spread: float,
    slippage_risk: str,
    best_effort_reason: str | None = None,
    reasons: list[str] | None = None,
) -> dict:
    return {
        "edge": {"probability_edge": 0.2},
        "score": {"total_score": 82.0, "grade": "A", "edge_theoretical": 0.66},
        "decision": {"status": status, "reasons": reasons or ["test fixture"]},
        "execution": {
            "spread": spread,
            "fillable_size_usd": fillable_size_usd,
            "slippage_risk": slippage_risk,
            "best_effort_reason": best_effort_reason,
            "all_in_cost_bps": 120.0,
            "order_book_depth_usd": 500.0,
            "hours_to_resolution": 10.0,
        },
    }

def _threshold_cycle_payload() -> dict:
    return {
        "run_id": "report-run-filter",
        "source": "live",
        "limit": 5,
        "summary": {"selected": 5, "scored": 4, "scoreable": 4, "traded": 3, "skipped": 2, "skipped_reasons": {"decision_not_tradeable": 1, "missing_tradeable_quote": 1}},
        "markets": [
            {
                "market_id": "tradeable",
                "market": {"id": "tradeable", "question": "Tradeable?"},
                "decision_status": "trade_small",
                "score_bundle": {
                    "edge": {"probability_edge": 0.12},
                    "score": {"total_score": 71.0, "grade": "B"},
                    "decision": {"reasons": ["passes filters"]},
                    "execution": {"spread": 0.02, "all_in_cost_bps": 120.0, "order_book_depth_usd": 250.0, "hours_to_resolution": 9.0},
                },
            },
            {
                "market_id": "thin-depth",
                "market": {"id": "thin-depth", "question": "Too thin?"},
                "decision_status": "trade",
                "score_bundle": {
                    "edge": {"probability_edge": 0.18},
                    "score": {"total_score": 83.0, "grade": "A"},
                    "decision": {"reasons": ["good edge but thin"]},
                    "execution": {"spread": 0.02, "all_in_cost_bps": 110.0, "order_book_depth_usd": 50.0, "hours_to_resolution": 5.0},
                },
            },
            {
                "market_id": "expensive",
                "market": {"id": "expensive", "question": "Too expensive?"},
                "decision_status": "trade",
                "score_bundle": {
                    "edge": {"probability_edge": 0.16},
                    "score": {"total_score": 82.0, "grade": "A"},
                    "decision": {"reasons": ["good edge but expensive"]},
                    "execution": {"spread": 0.08, "all_in_cost_bps": 900.0, "order_book_depth_usd": 700.0, "hours_to_resolution": 4.0},
                },
            },
            {
                "market_id": "watchlist",
                "market": {"id": "watchlist", "question": "Watch only?"},
                "decision_status": "watchlist",
                "score_bundle": {
                    "edge": {"probability_edge": 0.2},
                    "score": {"total_score": 88.0, "grade": "A"},
                    "decision": {"reasons": ["not tradeable"]},
                    "execution": {"spread": 0.02, "all_in_cost_bps": 100.0, "order_book_depth_usd": 500.0, "hours_to_resolution": 4.0},
                },
            },
            {
                "market_id": "unquoted",
                "market": {"id": "unquoted", "question": "Unquoted?"},
                "decision_status": "skipped",
                "score_bundle": None,
                "skip_reason": "missing_tradeable_quote",
            },
        ],
    }
