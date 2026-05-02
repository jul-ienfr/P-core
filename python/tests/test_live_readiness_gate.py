from __future__ import annotations

from weather_pm.operator_summary import _daily_operator_rollup, _live_quality_summary, _watchlist_row
from weather_pm.paper_watchlist import build_paper_watch_row, build_paper_watchlist_report


_READINESS_ACTIONS = {"WATCH", "PAPER_MICRO", "PAPER_STRICT", "BLOCKED"}


def _assert_paper_only_readiness(readiness: dict) -> None:
    assert readiness["action"] in _READINESS_ACTIONS
    assert isinstance(readiness["blockers"], list)
    assert readiness["paper_only"] is True
    assert readiness["live_order_allowed"] is False
    assert readiness["normal_size_allowed"] is False


def test_operator_watchlist_row_includes_paper_only_live_readiness_gate() -> None:
    row = _watchlist_row(
        {
            "market_id": "m-ready",
            "action": "WATCH",
            "matched_traders": ["weatherace"],
            "execution_snapshot": {
                "spread_yes": 0.02,
                "yes_ask_depth_usd": 100.0,
            },
            "resolution_status": {"official_daily_extract": {"available": True}},
        },
        handle_lookup={
            "weatherace": {
                "handle": "weatherace",
                "classification": "weather-heavy",
                "weather_pnl_usd": 1200,
                "weather_volume_usd": 4000,
            }
        },
    )

    readiness = row["live_readiness"]
    _assert_paper_only_readiness(readiness)
    assert readiness["action"] == "PAPER_STRICT"
    assert "paper_only_safety_gate" in readiness["blockers"]
    assert "live_execution_disabled" in readiness["blockers"]


def test_operator_live_readiness_exposes_useful_blockers_for_blocked_rows() -> None:
    row = _watchlist_row(
        {
            "market_id": "m-blocked",
            "action": "BLOCKED",
            "blocker": "source_stale",
            "matched_traders": [],
            "execution_snapshot": {},
            "resolution_status": {"official_daily_extract": {"available": False}},
        },
        handle_lookup={},
    )

    readiness = row["live_readiness"]
    _assert_paper_only_readiness(readiness)
    assert readiness["action"] == "BLOCKED"
    assert "source_stale" in readiness["blockers"]
    assert "no_profitable_account_match" in readiness["blockers"]
    assert "missing_or_zero_depth" in readiness["blockers"]
    assert "official_resolution_unavailable" in readiness["blockers"]


def test_operator_refresh_rollup_exposes_live_readiness_summary_counts() -> None:
    blocked = _watchlist_row({"market_id": "blocked", "action": "BLOCKED", "blocker": "bad_source"}, handle_lookup={})
    paper = _watchlist_row(
        {
            "market_id": "paper",
            "action": "WATCH",
            "matched_traders": ["weatherace"],
            "execution_snapshot": {"spread_yes": 0.02, "yes_ask_depth_usd": 100.0},
        },
        handle_lookup={"weatherace": {"handle": "weatherace", "classification": "weather-heavy"}},
    )

    quality_summary = _live_quality_summary([blocked, paper])
    rollup = _daily_operator_rollup([blocked, paper], live_quality_summary=quality_summary)

    summary = rollup["live_readiness_summary"]
    assert summary["rows"] == 2
    assert summary["paper_only"] is True
    assert summary["live_order_allowed"] is False
    assert summary["normal_size_allowed"] is False
    assert summary["action_counts"]["BLOCKED"] == 1
    assert summary["action_counts"][paper["live_readiness"]["action"]] == 1
    assert summary["blocker_counts"]["live_execution_disabled"] == 2
    assert quality_summary["live_readiness_summary"] == summary


def test_paper_watch_rows_include_live_readiness_and_report_summary_counts() -> None:
    report = build_paper_watchlist_report(
        {
            "positions": [
                {
                    "city": "Warsaw",
                    "date": "April 26",
                    "station": "EPWA",
                    "side": "NO",
                    "temp": 11,
                    "unit": "C",
                    "kind": "exact",
                    "filled_usdc": 12.0,
                    "shares": 24.0,
                    "entry_avg": 0.5,
                    "p_side_now": 0.82,
                    "best_bid_now": 0.52,
                    "best_ask_now": 0.58,
                },
                {
                    "city": "Karachi",
                    "date": "April 27",
                    "station": "OPKC",
                    "side": "NO",
                    "temp": 36,
                    "unit": "C",
                    "kind": "higher",
                    "filled_usdc": 10.0,
                    "shares": 18.867925,
                    "entry_avg": 0.53,
                    "p_side_now": 0.49,
                    "best_bid_now": 0.40,
                    "best_ask_now": 0.52,
                },
            ]
        }
    )

    rows = report["watchlist"]
    for row in rows:
        _assert_paper_only_readiness(row["live_readiness"])

    assert rows[0]["live_readiness"]["action"] == "PAPER_MICRO"
    assert rows[1]["live_readiness"]["action"] == "BLOCKED"
    assert report["summary"]["live_readiness_summary"]["rows"] == 2
    assert report["summary"]["live_readiness_summary"]["action_counts"]["PAPER_MICRO"] == 1
    assert report["summary"]["live_readiness_summary"]["action_counts"]["BLOCKED"] == 1


def test_direct_paper_watch_row_preserves_no_live_order_invariants() -> None:
    row = build_paper_watch_row(
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
        },
        p_side=0.858,
        best_bid=0.26,
        best_ask=0.29,
        forecast_c=18,
    )

    _assert_paper_only_readiness(row["live_readiness"])
    assert row["live_readiness"]["action"] in {"PAPER_STRICT", "BLOCKED"}
