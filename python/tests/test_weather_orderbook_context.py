from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

PYTHON_SRC = Path(__file__).resolve().parents[1] / "src"


def _run_weather_pm(*args: str) -> dict[str, object]:
    result = subprocess.run(
        [sys.executable, "-m", "weather_pm.cli", *args],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONPATH": str(PYTHON_SRC)},
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_nearest_snapshot_within_max_staleness_computes_touch_features() -> None:
    from weather_pm.orderbook_context import enrich_trade_with_orderbook_context

    trade = {"id": "t1", "market_id": "m1", "token_id": "yes", "timestamp": "2026-04-29T12:35:00Z", "side": "BUY", "price": 0.42, "size": 20}
    snapshots = [
        {
            "market_id": "m1",
            "token_id": "yes",
            "timestamp": "2026-04-29T12:30:00Z",
            "bids": [[0.40, 100], [0.39, 50]],
            "asks": [[0.44, 60], [0.45, 80]],
        },
        {
            "market_id": "m1",
            "token_id": "yes",
            "timestamp": "2026-04-29T12:40:00Z",
            "bids": [[0.41, 90], [0.40, 10]],
            "asks": [[0.43, 25], [0.44, 75]],
        },
    ]

    enriched = enrich_trade_with_orderbook_context(trade, snapshots, max_staleness_seconds=600)

    assert enriched["orderbook_context_available"] is True
    assert enriched["snapshot_timestamp"] == "2026-04-29T12:30:00Z"
    assert enriched["staleness_seconds"] == 300
    assert enriched["best_bid"] == 0.40
    assert enriched["best_ask"] == 0.44
    assert enriched["mid"] == 0.42
    assert enriched["spread"] == 0.04
    assert enriched["depth_near_touch"] == 160.0
    assert enriched["available_size_at_or_better_price"] == 60.0
    assert enriched["estimated_slippage_for_5_usdc"] >= 0.0
    assert enriched["estimated_slippage_for_20_usdc"] >= 0.0
    assert enriched["imbalance"] is not None
    assert enriched["microprice"] is not None
    assert enriched["paper_only"] is True
    assert enriched["live_order_allowed"] is False


def test_stale_snapshot_marks_missing_reason_explicitly() -> None:
    from weather_pm.orderbook_context import enrich_trade_with_orderbook_context

    trade = {"market_id": "m1", "token_id": "yes", "timestamp": "2026-04-29T12:35:00Z"}
    snapshots = [{"market_id": "m1", "token_id": "yes", "timestamp": "2026-04-29T11:00:00Z", "bids": [[0.4, 10]], "asks": [[0.5, 10]]}]

    enriched = enrich_trade_with_orderbook_context(trade, snapshots, max_staleness_seconds=300)

    assert enriched["orderbook_context_available"] is False
    assert enriched["missing_reason"] == "no_snapshot_within_max_staleness"
    assert enriched["best_bid"] is None
    assert enriched["best_ask"] is None
    assert enriched["paper_only"] is True
    assert enriched["live_order_allowed"] is False


def test_latest_snapshot_mapping_by_embedded_resolution_primary_key() -> None:
    from weather_pm.orderbook_context import enrich_trade_with_orderbook_context

    trade = {
        "slug": "highest-temperature-in-paris-on-april-15-2026-18c",
        "timestamp": "1776282196",
        "side": "SELL",
        "price": 0.999,
        "size": 510,
        "resolution": {"primary_key": "1965242", "matched_key": "highest-temperature-in-paris-on-april-15-2026-18c"},
    }
    snapshots = {
        "1965242": {"best_bid": 0.001, "best_ask": 0.0175, "depth_usd": 1000},
        "1965243": {"best_bid": 0.4, "best_ask": 0.5, "depth_usd": 10},
    }

    enriched = enrich_trade_with_orderbook_context(trade, snapshots, max_staleness_seconds=3600)

    assert enriched["orderbook_context_available"] is True
    assert enriched["missing_reason"] is None
    assert enriched["snapshot_timestamp"] == "latest"
    assert enriched["staleness_seconds"] == 0
    assert enriched["best_bid"] == 0.001
    assert enriched["best_ask"] == 0.0175
    assert enriched["depth_near_touch"] == 1000.0
    assert enriched["paper_only"] is True
    assert enriched["live_order_allowed"] is False


def test_cli_enrich_trades_orderbook_context_writes_artifact_and_compact_summary(tmp_path: Path) -> None:
    trades_path = tmp_path / "trades.json"
    snapshots_path = tmp_path / "snapshots.json"
    output_path = tmp_path / "enriched.json"
    trades_path.write_text(
        json.dumps({"trades": [{"id": "t1", "market_id": "m1", "token_id": "yes", "timestamp": "2026-04-29T12:35:00Z", "side": "BUY", "price": 0.42, "size": 10}]}),
        encoding="utf-8",
    )
    snapshots_path.write_text(
        json.dumps({"snapshots": [{"market_id": "m1", "token_id": "yes", "timestamp": "2026-04-29T12:30:00Z", "bids": [[0.40, 100]], "asks": [[0.43, 100]]}]}),
        encoding="utf-8",
    )

    result = _run_weather_pm(
        "enrich-trades-orderbook-context",
        "--trades-json",
        str(trades_path),
        "--orderbook-snapshots-json",
        str(snapshots_path),
        "--output-json",
        str(output_path),
        "--max-staleness-seconds",
        "600",
    )

    assert result == {"paper_only": True, "live_order_allowed": False, "trades": 1, "with_orderbook_context": 1, "missing_orderbook_context": 0}
    artifact = json.loads(output_path.read_text(encoding="utf-8"))
    assert artifact["paper_only"] is True
    assert artifact["live_order_allowed"] is False
    assert artifact["summary"]["with_orderbook_context"] == 1
    assert artifact["trades"][0]["orderbook_context_available"] is True
    assert artifact["trades"][0]["capturability"] == "capturable"
    assert "PMXT hourly L2 archive candidate" in artifact["limitations"]
    assert "Telonex full-depth candidate" in artifact["limitations"]
    assert "evan-kolberg/prediction-market-backtesting" in artifact["limitations"]
