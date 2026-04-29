from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
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


def test_normalize_hf_trade_row_maps_aliases_and_preserves_unknowns() -> None:
    from weather_pm.hf_polymarket_dataset import normalize_hf_trade_row

    row = {
        "proxyWallet": "0xabc",
        "market": "Will NYC high temperature exceed 80F?",
        "conditionId": "cond-123",
        "asset": "token-yes",
        "price": 0.42,
        "size": 12.5,
        "timestamp": "2024-04-01T12:00:00Z",
        "unexpected_field": {"kept": True},
    }

    normalized = normalize_hf_trade_row(row)

    assert normalized["wallet"] == "0xabc"
    assert normalized["title"] == "Will NYC high temperature exceed 80F?"
    assert normalized["condition_id"] == "cond-123"
    assert normalized["token_id"] == "token-yes"
    assert normalized["market_id"] is None
    assert normalized["price"] == 0.42
    assert normalized["size"] == 12.5
    assert normalized["timestamp"] == "2024-04-01T12:00:00Z"
    assert normalized["paper_only"] is True
    assert normalized["live_order_allowed"] is False
    assert normalized["raw"]["unexpected_field"] == {"kept": True}


def test_normalize_hf_trade_row_converts_parquet_style_unknowns_to_json_nulls() -> None:
    from weather_pm.hf_polymarket_dataset import normalize_hf_trade_row

    normalized = normalize_hf_trade_row(
        {
            "proxyWallet": "0xabc",
            "price": float("nan"),
            "createdAt": datetime(2024, 4, 1, 12, 0, tzinfo=timezone.utc),
            "unexpected_field": {"missing": float("nan")},
        }
    )

    assert normalized["price"] is None
    assert normalized["timestamp"] == "2024-04-01T12:00:00+00:00"
    assert normalized["raw"]["unexpected_field"] == {"missing": None}
    dumped_payload = json.loads(json.dumps(normalized, allow_nan=False))
    assert dumped_payload["raw"]["unexpected_field"] == {"missing": None}


def test_iter_hf_dataset_rows_reads_jsonl_and_respects_limit(tmp_path: Path) -> None:
    from weather_pm.hf_polymarket_dataset import iter_hf_dataset_rows

    input_path = tmp_path / "trades.jsonl"
    input_path.write_text(
        "\n".join(
            [
                json.dumps({"wallet": "0x1", "price": 0.1}),
                json.dumps({"wallet": "0x2", "price": 0.2}),
                json.dumps({"wallet": "0x3", "price": 0.3}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    assert list(iter_hf_dataset_rows(input_path, limit=2)) == [
        {"wallet": "0x1", "price": 0.1},
        {"wallet": "0x2", "price": 0.2},
    ]


def test_cli_hf_account_trades_sample_filters_wallets_and_writes_artifact(tmp_path: Path) -> None:
    input_path = tmp_path / "hf_sample.jsonl"
    output_path = tmp_path / "normalized.json"
    input_path.write_text(
        "\n".join(
            [
                json.dumps({"proxyWallet": "0xabc", "market": "Weather A", "conditionId": "cond-a", "asset": "token-a", "price": 0.44, "size": 10, "timestamp": "2024-04-01T00:00:00Z"}),
                json.dumps({"proxyWallet": "0xdef", "market": "Weather B", "conditionId": "cond-b", "asset": "token-b", "price": 0.55, "size": 5, "timestamp": "2024-04-02T00:00:00Z"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = _run_weather_pm(
        "hf-account-trades-sample",
        "--input",
        str(input_path),
        "--wallet",
        "0xabc",
        "--output-json",
        str(output_path),
        "--limit",
        "10",
    )

    assert result == {
        "paper_only": True,
        "live_order_allowed": False,
        "rows_scanned": 2,
        "matched_trades": 1,
        "output_json": str(output_path),
    }
    artifact = json.loads(output_path.read_text(encoding="utf-8"))
    assert artifact["paper_only"] is True
    assert artifact["live_order_allowed"] is False
    assert artifact["rows_scanned"] == 2
    assert len(artifact["trades"]) == 1
    assert artifact["trades"][0]["wallet"] == "0xabc"
    assert artifact["trades"][0]["condition_id"] == "cond-a"
    assert artifact["trades"][0]["token_id"] == "token-a"
