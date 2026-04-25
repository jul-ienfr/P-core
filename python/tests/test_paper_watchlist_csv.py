from __future__ import annotations

import csv
import json
from pathlib import Path

from weather_pm.paper_watchlist import write_paper_watchlist_csv


def test_paper_watchlist_csv_writes_operator_rows(tmp_path: Path) -> None:
    report = {
        "summary": {"positions": 1, "total_spend": 7.24, "total_ev_now": 17.49},
        "watchlist": [
            {
                "city": "Seoul",
                "date": "April 26",
                "station": "RKSI",
                "side": "NO",
                "temp": 20,
                "unit": "C",
                "kind": "higher",
                "spend_usdc": 7.24,
                "entry_avg": 0.2512,
                "p_side_now": 0.858,
                "paper_ev_now_usdc": 17.487,
                "operator_action": "HOLD_MONITOR",
                "hard_stop_if_p_below": 0.2212,
                "trim_review_if_p_below": 0.2712,
                "take_profit_review_if_bid_above": 0.838,
                "add_allowed": False,
                "max_add_usdc": 0,
            }
        ],
    }
    input_json = tmp_path / "watchlist.json"
    output_csv = tmp_path / "watchlist.csv"
    input_json.write_text(json.dumps(report), encoding="utf-8")

    rows = write_paper_watchlist_csv(input_json, output_csv)

    assert rows == 1
    with output_csv.open(newline="", encoding="utf-8") as handle:
        data = list(csv.DictReader(handle))
    assert data == [
        {
            "city": "Seoul",
            "date": "April 26",
            "station": "RKSI",
            "side": "NO",
            "market": "higher 20°C",
            "spend_usdc": "7.24",
            "entry_avg": "0.2512",
            "p_side_now": "0.8580",
            "paper_ev_now_usdc": "17.49",
            "operator_action": "HOLD_MONITOR",
            "hard_stop_if_p_below": "0.2212",
            "trim_review_if_p_below": "0.2712",
            "take_profit_review_if_bid_above": "0.8380",
            "add_allowed": "false",
            "max_add_usdc": "0.00",
        }
    ]
