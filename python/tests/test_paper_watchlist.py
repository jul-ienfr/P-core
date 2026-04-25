from weather_pm.paper_watchlist import build_paper_watch_row


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
