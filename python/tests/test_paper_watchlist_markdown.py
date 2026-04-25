from __future__ import annotations

import json
from pathlib import Path

from weather_pm.paper_watchlist import write_paper_watchlist_markdown


def test_paper_watchlist_markdown_renders_operator_actions(tmp_path: Path) -> None:
    report = {
        "summary": {"positions": 2, "total_spend": 22.24, "total_ev_now": 21.39, "action_counts": {"HOLD_MONITOR": 1, "HOLD_CAPPED": 1}},
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
            },
            {
                "city": "Beijing",
                "date": "April 26",
                "station": "ZBAA",
                "side": "NO",
                "temp": 25,
                "unit": "C",
                "kind": "exact",
                "spend_usdc": 15.0,
                "entry_avg": 0.62,
                "p_side_now": 0.7815,
                "paper_ev_now_usdc": 3.907,
                "operator_action": "HOLD_CAPPED",
                "hard_stop_if_p_below": 0.59,
                "trim_review_if_p_below": 0.64,
                "take_profit_review_if_bid_above": 0.7615,
                "add_allowed": False,
                "max_add_usdc": 0,
            },
        ],
    }
    input_json = tmp_path / "watchlist.json"
    output_md = tmp_path / "watchlist.md"
    input_json.write_text(json.dumps(report), encoding="utf-8")

    write_paper_watchlist_markdown(input_json, output_md)

    markdown = output_md.read_text(encoding="utf-8")
    assert "# Polymarket weather paper watchlist" in markdown
    assert "Positions: 2" in markdown
    assert "HOLD_MONITOR: 1" in markdown
    assert "## Operator decision" in markdown
    assert "Global action: HOLD" in markdown
    assert "Positive paper EV, but no add allowed" in markdown
    assert "Top EV: Seoul April 26 NO higher 20°C (+17.49 USDC)" in markdown
    assert "| Seoul | April 26 | RKSI | NO | higher 20°C | 7.24 | 0.2512 | 0.8580 | 17.49 | HOLD_MONITOR | 0.2212 | 0.2712 | 0.8380 | no |" in markdown
    assert "| Beijing | April 26 | ZBAA | NO | exact 25°C | 15.00 | 0.6200 | 0.7815 | 3.91 | HOLD_CAPPED | 0.5900 | 0.6400 | 0.7615 | no |" in markdown
