from weather_pm.paper_watchlist import build_paper_watch_row, build_paper_watchlist_report


def test_build_paper_watch_row_marks_large_edge_position_as_capped_hold():
    position = {
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
    }

    row = build_paper_watch_row(position, p_side=0.858, best_bid=0.26, best_ask=0.29, forecast_c=18)

    assert row["operator_action"] == "HOLD_CAPPED"
    assert row["hard_stop_if_p_below"] == 0.2146
    assert row["trim_review_if_p_below"] == 0.2646
    assert row["add_allowed"] is False
    assert row["paper_ev_now_usdc"] == 43.237
    assert row["paper_mtm_bid_usdc"] == 1.086


def test_build_paper_watch_row_flags_exit_when_probability_below_hard_stop():
    position = {
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
    }

    row = build_paper_watch_row(position, p_side=0.49, best_bid=0.40, best_ask=0.52, forecast_c=35)

    assert row["operator_action"] == "EXIT_PAPER"
    assert row["hard_stop_if_p_below"] == 0.5
    assert row["reason"] == "p_side 0.4900 < hard_stop 0.5000"
    assert row["add_allowed"] is False


def test_build_paper_watch_row_caps_position_after_paper_add_to_prevent_repeat_add():
    position = {
        "city": "Shanghai",
        "date": "April 26",
        "station": "ZSPD",
        "side": "NO",
        "temp": 23,
        "unit": "C",
        "kind": "exact",
        "filled_usdc": 9.7552,
        "shares": 1257.43,
        "entry_avg": 0.00775805,
        "paper_add_executed_at": "20260426T192124Z",
    }

    row = build_paper_watch_row(position, p_side=0.721, best_bid=0.001, best_ask=0.004, forecast_c=23)

    assert row["operator_action"] == "HOLD_CAPPED"
    assert row["reason"] == "paper add already executed this cycle; no repeated add"
    assert row["add_allowed"] is False


def test_paper_watchlist_uses_dynamic_surface_cap_to_block_add():
    position = {
        "city": "Hong Kong",
        "date": "April 26",
        "station": "VHHH",
        "side": "NO",
        "temp": 29,
        "unit": "C",
        "kind": "higher",
        "filled_usdc": 8.0,
        "shares": 16.0,
        "entry_avg": 0.5,
        "market_id": "hk-higher-29",
        "surface_key": "Hong Kong|April 26|higher",
        "current_surface_exposure_usdc": 50.0,
    }

    row = build_paper_watch_row(position, p_side=0.82, best_bid=0.52, best_ask=0.58, forecast_c=27)

    assert row["operator_action"] == "HOLD_CAPPED"
    assert row["add_allowed"] is False
    assert row["max_add_usdc"] == 0
    assert row["dynamic_sizing"]["action"] == "HOLD_CAPPED"
    assert "surface_cap_reached" in row["dynamic_sizing"]["reasons"]


def test_paper_watchlist_caps_add_by_dynamic_recommended_size():
    position = {
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
        "market_id": "warsaw-exact-11",
        "surface_key": "Warsaw|April 26|exact",
    }

    row = build_paper_watch_row(position, p_side=0.82, best_bid=0.52, best_ask=0.58, forecast_c=11)

    assert row["operator_action"] == "HOLD_MONITOR"
    assert row["add_allowed"] is True
    assert row["dynamic_sizing"]["action"] == "ADD"
    assert row["dynamic_sizing"]["recommended_size_usdc"] == 3.0
    assert row["max_add_usdc"] == 3.0


def test_paper_watchlist_reconciles_spend_from_batches_when_legacy_filled_usdc_drifted():
    position = {
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
        "batches": [
            {"batch": "initial", "usdc": 2.24, "shares": 8.0, "avg": 0.28},
            {"batch": "add_monitor_1", "usdc": 5.0, "shares": 20.8192, "avg": 0.2402},
        ],
    }

    row = build_paper_watch_row(position, p_side=0.01, best_bid=0.30, best_ask=0.31, forecast_c=18)

    assert row["operator_action"] == "EXIT_PAPER"
    assert row["spend_usdc"] == 7.24
    assert row["shares"] == 28.8192
    assert row["entry_avg"] == 0.2512
    assert row["paper_mtm_bid_usdc"] == 1.406
    assert row["paper_mtm_bid_value_usdc"] == 8.646


def test_paper_watchlist_marks_due_dated_positions_for_resolution_review_not_active_hold():
    report = build_paper_watchlist_report(
        {
            "as_of_date": "2026-04-27",
            "positions": [
                {
                    "city": "Munich",
                    "date": "April 26",
                    "station": "EDDM",
                    "side": "NO",
                    "temp": 18,
                    "unit": "C",
                    "kind": "exact",
                    "filled_usdc": 10.0,
                    "shares": 14.0845,
                    "entry_avg": 0.71,
                    "base_p_side": 0.9,
                    "best_bid_now": 0.999,
                }
            ],
        }
    )

    row = report["watchlist"][0]
    assert row["operator_action"] == "RESOLUTION_REVIEW"
    assert row["reason"] == "market date elapsed; verify official resolution before final PnL"
    assert report["summary"]["active_positions"] == 0
    assert report["summary"]["resolution_review_positions"] == 1
