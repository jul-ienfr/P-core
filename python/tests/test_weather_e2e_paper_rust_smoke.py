from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from prediction_core.paper.ledger import paper_ledger_place, paper_ledger_refresh
from weather_pm.strategy_shortlist import build_strategy_shortlist

ROOT = Path(__file__).resolve().parents[2]
PARITY_FIXTURE = ROOT / "python" / "tests" / "fixtures" / "orderbook_fill_parity.json"


def test_weather_paper_rust_opt_in_smoke_exports_analytics_dry_run(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("PREDICTION_CORE_RUST_ORDERBOOK", "1")
    shortlist = build_strategy_shortlist(
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
        },
        {
            "summary": {"selected": 1, "scored": 1, "traded": 1},
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
                }
            ],
        },
        {
            "events": [
                {
                    "event_key": "London|high|c|April 25",
                    "inconsistencies": [
                        {
                            "type": "threshold_monotonicity_violation",
                            "severity": 0.05,
                            "lower_market_id": "london-19",
                            "higher_market_id": "london-20",
                        }
                    ],
                }
            ]
        },
        limit=1,
    )
    row = shortlist["shortlist"][0]
    assert row["entry_decision"]["enter"] is True
    assert row["edge_sizing"]["recommendation"] == "buy"

    parity = json.loads(PARITY_FIXTURE.read_text(encoding="utf-8"))
    ledger = paper_ledger_place(
        {
            "surface_id": row["surface_key"],
            "market_id": row["market_id"],
            "token_id": "london-no-token",
            "side": "NO",
            "strict_limit": parity["requests"]["strict_limit"],
            "spend_usdc": parity["requests"]["spend_usdc"],
            "orderbook": parity["polymarket_orderbook"],
            "actual_refresh_price": parity["expected"]["spend_fill"]["top_ask"],
            "source_status": "source_confirmed",
            "station_status": "station_confirmed",
            "strategy_id": row["strategy_id"],
            "strategy_profile_id": row["strategy_profile_id"],
        }
    )
    ledger = paper_ledger_refresh(
        ledger,
        refreshes={
            "london-no-token": {
                "best_bid": parity["polymarket_orderbook"]["no_bids"][0]["price"],
                "exit_orderbook": {"no_bids": parity["polymarket_orderbook"]["no_bids"]},
            }
        },
    )
    order = ledger["orders"][0]
    assert order["paper_only"] is True
    assert order["live_order_allowed"] is False
    assert order["status"] == "filled"
    assert order["filled_usdc"] == 10.0
    assert order["paper_exit_value_usdc"] == pytest.approx(11.578574, rel=1e-6)

    shortlist_path = tmp_path / "shortlist.json"
    ledger_path = tmp_path / "ledger.json"
    shortlist_path.write_text(
        json.dumps(
            {
                "run_id": "rust-paper-smoke",
                "generated_at": "2026-04-28T12:00:00+00:00",
                "rows": [row],
                "shortlist": [row],
            }
        )
    )
    ledger_path.write_text(json.dumps({"run_id": "rust-paper-smoke", **ledger}))

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "weather_pm.cli",
            "export-analytics-clickhouse",
            "--shortlist-json",
            str(shortlist_path),
            "--paper-ledger-json",
            str(ledger_path),
            "--dry-run",
        ],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": "python/src", "PREDICTION_CORE_RUST_ORDERBOOK": "1"},
        text=True,
        capture_output=True,
        check=True,
    )

    lines = result.stdout.strip().splitlines()
    assert "analytics.strategy_signals.rows=1" in lines
    assert "analytics.paper_orders.rows=1" in lines
    assert "analytics.paper_positions.rows=1" in lines
    assert "analytics.paper_pnl_snapshots.rows=1" in lines
    assert lines[-1] == "analytics.enabled=false"
