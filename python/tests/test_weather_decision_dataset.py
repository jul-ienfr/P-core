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


def test_positive_weather_trades_become_trade_examples() -> None:
    from weather_pm.decision_dataset import build_account_decision_dataset

    payload = build_account_decision_dataset(
        {
            "trades": [
                {
                    "account": "alice",
                    "wallet": "0xabc",
                    "market_id": "m-paris-hi-21",
                    "timestamp": "2026-05-04T12:35:00Z",
                    "city": "Paris",
                    "date": "2026-05-04",
                    "market_type": "high_temperature",
                    "side": "YES",
                    "price": 0.37,
                }
            ]
        },
        {"markets": []},
        bucket_minutes=60,
    )

    assert payload["paper_only"] is True
    assert payload["live_order_allowed"] is False
    examples = payload["examples"]
    assert len(examples) == 1
    row = examples[0]
    assert row["label"] == "trade"
    assert row["account"] == "alice"
    assert row["wallet"] == "0xabc"
    assert row["market_id"] == "m-paris-hi-21"
    assert row["timestamp_bucket"] == "2026-05-04T12:00:00Z"
    assert row["city"] == "Paris"
    assert row["market_type"] == "high_temperature"
    assert row["side"] == "YES"
    assert row["price"] == 0.37


def test_no_trade_examples_require_observable_active_same_surface_and_ratio_cap() -> None:
    from weather_pm.decision_dataset import build_account_decision_dataset

    trades = {
        "trades": [
            {
                "account": "alice",
                "wallet": "0xabc",
                "market_id": "m-traded",
                "timestamp": "2026-05-04T12:10:00Z",
                "city": "Paris",
                "date": "2026-05-04",
                "market_type": "high_temperature",
                "side": "YES",
                "price": 0.41,
            }
        ]
    }
    markets = {
        "markets": [
            {
                "market_id": "m-alt-1",
                "active_timestamp": "2026-05-04T12:15:00Z",
                "observable": True,
                "city": "Paris",
                "date": "2026-05-04",
                "market_type": "high_temperature",
                "side": "YES",
                "price": 0.32,
            },
            {
                "market_id": "m-alt-2",
                "active_timestamp": "2026-05-04T12:20:00Z",
                "observable": True,
                "city": "Paris",
                "date": "2026-05-04",
                "market_type": "high_temperature",
            },
            {
                "market_id": "m-hidden",
                "active_timestamp": "2026-05-04T12:25:00Z",
                "observable": False,
                "city": "Paris",
                "date": "2026-05-04",
                "market_type": "high_temperature",
            },
            {
                "market_id": "m-missing-ts",
                "observable": True,
                "city": "Paris",
                "date": "2026-05-04",
                "market_type": "high_temperature",
            },
        ]
    }

    payload = build_account_decision_dataset(trades, markets, bucket_minutes=60, no_trade_per_trade=1)

    no_trades = [row for row in payload["examples"] if row["label"] == "no_trade"]
    assert len(no_trades) == 1
    assert no_trades[0]["market_id"] == "m-alt-1"
    assert no_trades[0]["reason"] == "similar_surface_no_account_trade"
    assert no_trades[0]["observable"] is True
    assert no_trades[0]["timestamp_bucket"] == "2026-05-04T12:00:00Z"
    assert payload["summary"]["trade_examples"] == 1
    assert payload["summary"]["no_trade_examples"] == 1
    assert payload["summary"]["observable_markets_considered"] == 2
    assert payload["summary"]["skipped_unobservable"] == 2


def test_cli_build_account_decision_dataset_writes_artifact_and_compact_summary(tmp_path: Path) -> None:
    trades_path = tmp_path / "trades.json"
    markets_path = tmp_path / "markets.json"
    output_path = tmp_path / "decision_dataset.json"
    trades_path.write_text(
        json.dumps(
            {
                "trades": [
                    {
                        "account": "alice",
                        "wallet": "0xabc",
                        "market_id": "m-traded",
                        "timestamp": "2026-05-04T12:10:00Z",
                        "city": "Paris",
                        "date": "2026-05-04",
                        "market_type": "high_temperature",
                        "side": "YES",
                        "price": 0.41,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    markets_path.write_text(
        json.dumps(
            {
                "markets": [
                    {
                        "market_id": "m-alt",
                        "active_timestamp": "2026-05-04T12:15:00Z",
                        "observable": True,
                        "city": "Paris",
                        "date": "2026-05-04",
                        "market_type": "high_temperature",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = _run_weather_pm(
        "build-account-decision-dataset",
        "--trades-json",
        str(trades_path),
        "--markets-snapshots-json",
        str(markets_path),
        "--output-json",
        str(output_path),
        "--bucket-minutes",
        "60",
        "--no-trade-per-trade",
        "5",
    )

    assert result["paper_only"] is True
    assert result["live_order_allowed"] is False
    assert result["accounts"] == 1
    assert result["trade_examples"] == 1
    assert result["no_trade_examples"] == 1
    artifact = json.loads(output_path.read_text(encoding="utf-8"))
    assert artifact["summary"]["paper_only"] is True
    assert artifact["summary"]["live_order_allowed"] is False
    assert {row["label"] for row in artifact["examples"]} == {"trade", "no_trade"}
