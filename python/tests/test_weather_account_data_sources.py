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


def test_account_data_source_manifest_lists_historical_sources() -> None:
    from weather_pm.account_data_sources import build_account_data_source_manifest

    payload = build_account_data_source_manifest()

    assert payload["paper_only"] is True
    assert payload["live_order_allowed"] is False
    source_ids = {row["source_id"] for row in payload["sources"]}
    assert "polymarket_data_api_trades" in source_ids
    assert "sii_wangzj_polymarket_data_hf" in source_ids
    assert "pmxt_l2_archive" in source_ids
    assert "telonex_full_depth_snapshots" in source_ids
    assert "gamma_closed_markets" in source_ids


def test_cli_account_data_source_manifest_reports_compact_guarded_summary() -> None:
    result = _run_weather_pm("account-data-source-manifest")

    assert result["paper_only"] is True
    assert result["live_order_allowed"] is False
    assert result["sources"] >= 7
    assert "sii_wangzj_polymarket_data_hf" in result["high_priority_sources"]
    assert "pmxt_l2_archive" in result["high_priority_sources"]
    assert "gamma_closed_markets" in result["high_priority_sources"]
