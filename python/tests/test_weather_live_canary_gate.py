from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from weather_pm.live_canary_gate import (
    LiveCanaryConfig,
    LiveCanaryGateError,
    build_live_canary_preflight,
    evaluate_live_canary_row,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _eligible_row() -> dict[str, object]:
    return {
        "market_id": "m-canary",
        "token_id": "tok-canary",
        "side": "YES",
        "strict_limit": 0.44,
        "requested_notional_usdc": 1.0,
        "autopilot_gate": "PAPER_MICRO",
        "live_quality": {"live_quality_score": 92.0},
        "normal_size_gate": {"live_ready": True, "reasons": []},
        "execution_snapshot": {
            "best_bid_yes": 0.41,
            "best_ask_yes": 0.43,
            "spread_yes": 0.02,
            "yes_ask_depth_usd": 250.0,
        },
        "resolution_status": {"official_daily_extract": {"available": True}},
        "portfolio_risk": {"cap_status": "approved", "approved_size_usdc": 1.0},
    }


def test_live_canary_gate_stays_disabled_by_default_even_for_eligible_row() -> None:
    decision = evaluate_live_canary_row(_eligible_row(), config=LiveCanaryConfig(run_id="run-1"))

    assert decision["mode"] == "LIVE_CANARY"
    assert decision["eligible"] is False
    assert decision["canary_action"] == "DRY_RUN_ONLY"
    assert decision["live_order_allowed"] is False
    assert decision["paper_only"] is True
    assert decision["orders_allowed"] is False
    assert decision["kill_switch_active"] is True
    assert decision["live_execution_payload"] is None
    assert "canary_disabled" in decision["blockers"]
    assert "kill_switch_active" in decision["blockers"]
    assert decision["idempotency_key"]


def test_live_canary_gate_can_only_arm_micro_order_after_all_guards_are_explicit() -> None:
    config = LiveCanaryConfig(
        enabled=True,
        kill_switch=False,
        dry_run=False,
        allowlist_market_ids={"m-canary"},
        max_order_usdc=1.0,
        max_daily_usdc=1.0,
        min_live_quality_score=80.0,
        run_id="run-armed",
    )

    decision = evaluate_live_canary_row(_eligible_row(), config=config)

    assert decision["eligible"] is True
    assert decision["canary_action"] == "MICRO_LIVE_LIMIT_ORDER_ALLOWED"
    assert decision["live_order_allowed"] is True
    assert decision["paper_only"] is False
    assert decision["orders_allowed"] is True
    assert decision["kill_switch_active"] is False
    assert decision["blockers"] == []
    payload = decision["live_execution_payload"]
    assert payload == {
        "market_id": "m-canary",
        "token_id": "tok-canary",
        "side": "YES",
        "order_type": "limit",
        "limit_price": 0.44,
        "notional_usdc": 1.0,
        "time_in_force": "IOC",
        "client_order_id": decision["idempotency_key"],
        "dry_run": False,
    }


def test_live_canary_gate_blocks_unallowlisted_wide_or_oversized_rows() -> None:
    row = _eligible_row()
    row["market_id"] = "m-other"
    row["requested_notional_usdc"] = 5.0
    row["execution_snapshot"] = {
        "best_bid_yes": 0.20,
        "best_ask_yes": 0.35,
        "spread_yes": 0.15,
        "yes_ask_depth_usd": 0.0,
    }
    config = LiveCanaryConfig(
        enabled=True,
        kill_switch=False,
        dry_run=False,
        allowlist_market_ids={"m-canary"},
        max_order_usdc=1.0,
        max_daily_usdc=1.0,
        run_id="run-blocked",
    )

    decision = evaluate_live_canary_row(row, config=config)

    assert decision["eligible"] is False
    assert decision["live_order_allowed"] is False
    assert decision["live_execution_payload"] is None
    assert "market_not_allowlisted" in decision["blockers"]
    assert "wide_spread" in decision["blockers"]
    assert "insufficient_depth" in decision["blockers"]
    assert "order_cap_exceeded" in decision["blockers"]
    assert "daily_cap_exceeded" in decision["blockers"]


def test_live_canary_preflight_refuses_live_execution_unless_confirmed_phrase_is_present() -> None:
    with pytest.raises(LiveCanaryGateError, match="confirmation phrase"):
        build_live_canary_preflight(
            {"live_rows": [_eligible_row()]},
            config=LiveCanaryConfig(enabled=True, kill_switch=False, dry_run=False, allowlist_market_ids={"m-canary"}),
        )


def test_live_canary_preflight_cli_writes_disabled_dry_run_artifact(tmp_path: Path) -> None:
    operator_path = tmp_path / "operator.json"
    output_path = tmp_path / "preflight.json"
    operator_path.write_text(json.dumps({"live_rows": [_eligible_row()]}), encoding="utf-8")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT / "src")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "weather_pm.cli",
            "live-canary-preflight",
            "--operator-json",
            str(operator_path),
            "--output-json",
            str(output_path),
            "--run-id",
            "cli-dry-run",
        ],
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    compact = json.loads(result.stdout)
    artifact = json.loads(output_path.read_text(encoding="utf-8"))
    assert compact["live_order_allowed"] is False
    assert compact["eligible_count"] == 0
    assert artifact["paper_only"] is True
    assert artifact["live_order_allowed"] is False
    assert artifact["orders_allowed"] is False
    assert artifact["decisions"][0]["canary_action"] == "DRY_RUN_ONLY"
