from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_monitor_module():
    path = Path(__file__).resolve().parents[2] / "scripts" / "weather_cron_monitor_refresh.py"
    spec = importlib.util.spec_from_file_location("weather_cron_monitor_refresh", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_runtime_analytics_rows_include_paper_basket_tables() -> None:
    module = _load_monitor_module()
    report = {
        "run_id": "20260427T190852Z",
        "runtime_execution_mode": "dry_run",
        "summary": {
            "portfolio_report": {
                "counts": {"exit_paper": 0, "open": 1, "settled": 1, "total": 2},
                "pnl_usdc": {"realized_total": 3.0, "realized_plus_open_mtm": 4.5},
                "spend_usdc": {"total_displayed": 20.0},
            }
        },
        "positions": [
            {
                "question": "Will it rain?",
                "token_id": "token-1",
                "side": "NO",
                "action": "HOLD_CAPPED",
                "shares": 10.0,
                "filled_usdc": 10.0,
                "entry_avg": 1.0,
                "paper_mtm_bid_usdc": 1.5,
            }
        ],
        "closed_positions": [
            {
                "question": "Will it snow?",
                "token_id": "token-2",
                "side": "NO",
                "action": "SETTLED_WON",
                "settlement_status": "SETTLED_WON",
                "shares": 10.0,
                "filled_usdc": 10.0,
                "entry_avg": 1.0,
                "paper_realized_pnl_usdc": 3.0,
            }
        ],
        "runtime_strategies": {"weather_profiles": {"decisions": []}, "execution_events": []},
    }

    rows = module.build_runtime_analytics_rows(report, "20260427T190852Z")

    assert len(rows["paper_orders"]) == 2
    assert len(rows["paper_positions"]) == 2
    assert len(rows["paper_pnl_snapshots"]) == 1
    assert rows["paper_pnl_snapshots"][0]["net_pnl_usdc"] == 4.5
    assert rows["paper_pnl_snapshots"][0]["exposure_usdc"] == 20.0
    assert rows["paper_orders"][0]["run_id"] == "20260427T190852Z"
