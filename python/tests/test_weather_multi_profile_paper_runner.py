from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from weather_pm.multi_profile_paper_runner import MultiProfilePaperRunnerError, run_multi_profile_paper_batch
from weather_pm.strategy_profiles import strategy_id_for_profile


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _shortlist_payload() -> dict:
    return {
        "run_id": "weather-signal-001",
        "shortlist": [
            {
                "market_id": "mkt-denver-high",
                "token_id": "tok-yes-denver-high",
                "surface_id": "denver-2026-05-01-high",
                "decision_status": "trade",
                "side": "YES",
                "strict_limit": 0.42,
                "spend_usdc": 9.0,
                "probability_edge": 0.09,
                "source_status": "source_confirmed",
                "station_status": "station_confirmed",
                "orderbook": {"yes_asks": [{"price": 0.40, "size": 100.0}]},
            }
        ],
    }


def test_multi_profile_runner_replays_same_shortlist_into_separate_guarded_ledgers() -> None:
    profile_ids = ["surface_grid_trader", "threshold_resolution_harvester"]

    result = run_multi_profile_paper_batch(_shortlist_payload(), profile_ids=profile_ids, run_id="batch-001", mode="paper")

    assert result["paper_only"] is True
    assert result["live_order_allowed"] is False
    assert result["no_real_orders"] is True
    assert result["comparison"]["total_orders"] == 2
    assert set(result["ledgers"]) == set(profile_ids)
    for profile_id in profile_ids:
        strategy_id = strategy_id_for_profile(profile_id)
        ledger = result["ledgers"][profile_id]
        assert ledger["run_id"] == f"batch-001:{strategy_id}:{profile_id}"
        assert ledger["profile_id"] == profile_id
        assert ledger["strategy_id"] == strategy_id
        assert ledger["summary"]["orders"] == 1
        order = ledger["orders"][0]
        assert order["run_id"] == ledger["run_id"]
        assert order["strategy_id"] == strategy_id
        assert order["profile_id"] == profile_id
        assert order["paper_only"] is True
        assert order["live_order_allowed"] is False
        assert order["order_type"] == "limit_only_paper"
        assert order["status"] == "filled"


def test_multi_profile_runner_caps_spend_per_profile_and_keeps_live_dry_run_paper_only() -> None:
    result = run_multi_profile_paper_batch(
        _shortlist_payload(),
        profile_ids=["threshold_resolution_harvester"],
        run_id="batch-002",
        mode="live_dry_run",
    )

    ledger = result["ledgers"]["threshold_resolution_harvester"]
    order = ledger["orders"][0]
    assert ledger["mode"] == "live_dry_run"
    assert order["requested_spend_usdc"] == 8.0
    assert order["filled_usdc"] == 8.0
    assert order["paper_only"] is True
    assert order["live_order_allowed"] is False
    assert result["comparison"]["paper_only"] is True
    assert result["comparison"]["live_order_allowed"] is False


def test_multi_profile_runner_rejects_unguarded_live_mode() -> None:
    with pytest.raises(MultiProfilePaperRunnerError, match="mode must be one of"):
        run_multi_profile_paper_batch(_shortlist_payload(), profile_ids=["surface_grid_trader"], mode="live")


def test_multi_profile_paper_runner_cli_writes_comparative_artifacts(tmp_path: Path) -> None:
    shortlist_path = tmp_path / "shortlist.json"
    out_dir = tmp_path / "artifacts"
    shortlist_path.write_text(json.dumps(_shortlist_payload()), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "weather_pm.cli",
            "multi-profile-paper-runner",
            "--shortlist-json",
            str(shortlist_path),
            "--run-id",
            "batch-cli",
            "--profile-id",
            "surface_grid_trader",
            "--profile-id",
            "threshold_resolution_harvester",
            "--mode",
            "shadow",
            "--output-dir",
            str(out_dir),
        ],
        cwd=PROJECT_ROOT,
        env={"PYTHONPATH": "src"},
        check=True,
        text=True,
        capture_output=True,
    )

    payload = json.loads(result.stdout)
    assert payload["mode"] == "shadow"
    assert payload["comparison"]["total_orders"] == 2
    assert Path(payload["artifacts"]["json"]).exists()
    markdown = Path(payload["artifacts"]["markdown"]).read_text(encoding="utf-8")
    assert "Weather multi-profile paper runner" in markdown
    assert "live_order_allowed=false" in markdown
