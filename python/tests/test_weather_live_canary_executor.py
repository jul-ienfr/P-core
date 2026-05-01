from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from weather_pm.live_canary_executor import execute_live_canary_preflight
from weather_pm.live_canary_gate import LiveCanaryConfig, build_live_canary_preflight
from weather_pm.polymarket_live_order_client import PolymarketLiveOrderClientConfig, build_order_client_config_from_env

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class RecordingClient:
    def __init__(self) -> None:
        self.orders: list[dict[str, object]] = []

    def submit_limit_order(self, payload: dict[str, object]) -> dict[str, object]:
        self.orders.append(dict(payload))
        return {"order_id": "ord-1", "status": "submitted", "client_order_id": payload["client_order_id"]}


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
        "execution_snapshot": {"best_bid_yes": 0.41, "best_ask_yes": 0.43, "spread_yes": 0.02, "yes_ask_depth_usd": 250.0},
        "portfolio_risk": {"cap_status": "approved", "approved_size_usdc": 1.0},
    }


def _armed_preflight() -> dict[str, object]:
    return build_live_canary_preflight(
        {"live_rows": [_eligible_row()]},
        config=LiveCanaryConfig(
            mode="live",
            allowlist_market_ids={"m-canary"},
            max_order_usdc=1.0,
            max_daily_usdc=1.0,
            min_live_quality_score=80.0,
            run_id="armed-run",
            confirmation_phrase="I_ACCEPT_MICRO_LIVE_WEATHER_RISK",
        ),
    )


def test_executor_is_noop_by_default_even_with_armed_preflight() -> None:
    client = RecordingClient()

    result = execute_live_canary_preflight(_armed_preflight(), config=LiveCanaryConfig(mode="shadow"), client=client)

    assert result["mode"] == "LIVE_CANARY_EXECUTOR"
    assert result["execution_mode"] == "shadow"
    assert result["live_order_submitted"] is False
    assert result["submitted_count"] == 0
    assert result["skipped_count"] == 1
    assert result["orders_allowed"] is False
    assert result["no_real_order_placed"] is True
    assert result["results"][0]["status"] == "skipped_shadow_mode"
    assert client.orders == []


def test_executor_submits_only_when_single_mode_config_is_live_and_client_is_ready() -> None:
    client = RecordingClient()

    result = execute_live_canary_preflight(_armed_preflight(), config=LiveCanaryConfig(mode="live"), client=client)

    assert result["execution_mode"] == "live"
    assert result["orders_allowed"] is True
    assert result["live_order_submitted"] is True
    assert result["submitted_count"] == 1
    assert result["skipped_count"] == 0
    assert result["no_real_order_placed"] is False
    assert result["results"][0]["status"] == "submitted"
    assert client.orders == [_armed_preflight()["decisions"][0]["live_execution_payload"]]


def test_executor_live_mode_without_client_is_pre_cabled_but_does_not_submit() -> None:
    result = execute_live_canary_preflight(_armed_preflight(), config=LiveCanaryConfig(mode="live"), client=None)

    assert result["execution_mode"] == "live"
    assert result["orders_allowed"] is True
    assert result["live_order_submitted"] is False
    assert result["submitted_count"] == 0
    assert result["results"][0]["status"] == "skipped_client_not_configured"
    assert result["no_real_order_placed"] is True


def test_order_client_env_config_is_redacted_and_controlled_by_one_mode_variable(monkeypatch) -> None:
    monkeypatch.setenv("WEATHER_LIVE_CANARY_MODE", "shadow")
    monkeypatch.setenv("POLYMARKET_PRIVATE_KEY", "secret-private-key")
    monkeypatch.setenv("POLYMARKET_FUNDER", "0x123")
    monkeypatch.setenv("POLYMARKET_HOST", "https://clob.polymarket.com")

    config = build_order_client_config_from_env()

    assert config.mode == "shadow"
    assert config.configured is True
    assert config.redacted() == {
        "mode": "shadow",
        "configured": True,
        "host": "https://clob.polymarket.com",
        "chain_id": 137,
        "funder": "[REDACTED]",
        "private_key": "[REDACTED]",
        "signature_type": 1,
    }


def test_live_canary_execute_cli_defaults_to_noop(tmp_path: Path) -> None:
    preflight_path = tmp_path / "preflight.json"
    output_path = tmp_path / "execute.json"
    preflight_path.write_text(json.dumps(_armed_preflight()), encoding="utf-8")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT / "src")
    env.pop("WEATHER_LIVE_CANARY_MODE", None)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "weather_pm.cli",
            "live-canary-execute",
            "--preflight-json",
            str(preflight_path),
            "--output-json",
            str(output_path),
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
    assert compact["execution_mode"] == "shadow"
    assert compact["live_order_submitted"] is False
    assert compact["submitted_count"] == 0
    assert artifact["results"][0]["status"] == "skipped_shadow_mode"
