from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from weather_pm.paper_autopilot_bridge import (
    PaperAutopilotBridgeError,
    build_paper_autopilot_ledger,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _operator_artifact() -> dict[str, object]:
    return {
        "report_type": "live_readiness_operator",
        "top_current_candidates": [
            {
                "market_id": "m-seoul-no-20",
                "token_id": "tok-no-20",
                "question": "Will Seoul be below 20C?",
                "side": "NO",
                "candidate_side": "NO",
                "autopilot_gate": "PAPER_STRICT",
                "strict_next_action": "paper_limit_only_after_source_recheck",
                "strict_limit": 0.30,
                "paper_notional_usdc": 5.0,
                "probability_edge": 0.16,
                "source_status": "source_confirmed",
                "station_status": "station_confirmed",
                "station": "RKSI",
                "source_url": "https://example.test/station/RKSI",
                "account_consensus": {"unique_accounts": 3, "dominant_side": "NO"},
                "source_metadata": {"station_provider": "official", "refresh_age_seconds": 30},
                "gate_payload": {"gate": "PAPER_STRICT", "checks": ["source_confirmed", "risk_approved"]},
                "portfolio_risk": {"cap_status": "approved", "approved_size_usdc": 5.0, "recommendation": "paper_small_capped"},
                "orderbook": {"no_asks": [{"price": 0.28, "size": 100.0}], "no_bids": [{"price": 0.27, "size": 100.0}]},
                "actual_refresh_price": 0.28,
            },
            {
                "market_id": "m-lima-yes-30",
                "token_id": "tok-yes-30",
                "side": "YES",
                "autopilot_gate": "PAPER_MICRO",
                "strict_limit": 0.42,
                "paper_notional_usdc": 5.0,
                "source_status": "source_confirmed",
                "portfolio_risk": {"cap_status": "approved", "approved_size_usdc": 5.0},
                "orderbook": {"yes_ask_levels": [{"price": 0.41, "size": 100.0}]},
            },
            {
                "market_id": "m-blocked-live",
                "token_id": "tok-live",
                "side": "YES",
                "autopilot_gate": "LIVE_ALLOWED",
                "strict_limit": 0.22,
                "paper_notional_usdc": 10.0,
                "orderbook": {"yes_ask_levels": [{"price": 0.21, "size": 100.0}]},
                "portfolio_risk": {"cap_status": "approved", "approved_size_usdc": 10.0},
            },
            {
                "market_id": "m-risk-blocked",
                "token_id": "tok-risk",
                "side": "YES",
                "autopilot_gate": "PAPER_STRICT",
                "strict_limit": 0.22,
                "paper_notional_usdc": 5.0,
                "orderbook": {"yes_ask_levels": [{"price": 0.21, "size": 100.0}]},
                "portfolio_risk": {"cap_status": "blocked", "approved_size_usdc": 0.0},
            },
        ],
    }


def test_paper_autopilot_bridge_converts_only_paper_strict_and_micro_rows_to_append_only_ledger() -> None:
    existing = {"orders": [{"order_id": "existing", "status": "filled", "filled_usdc": 1.0, "paper_only": True, "live_order_allowed": False}]}

    ledger = build_paper_autopilot_ledger(_operator_artifact(), ledger=existing, run_id="autopilot-smoke")

    assert [order["order_id"] for order in ledger["orders"]][:1] == ["existing"]
    assert ledger["summary"]["orders"] == 3
    assert ledger["paper_autopilot_summary"] == {
        "source_rows": 4,
        "eligible_rows": 2,
        "appended_orders": 2,
        "skipped_rows": 2,
        "gates": {"PAPER_MICRO": 1, "PAPER_STRICT": 1},
        "paper_only": True,
        "live_order_allowed": False,
    }

    strict, micro = ledger["orders"][1:]
    assert strict["run_id"] == "autopilot-smoke"
    assert strict["source"] == "paper_autopilot_strict_limit_bridge"
    assert strict["append_only"] is True
    assert strict["would_place_order"] is True
    assert strict["idempotency_key"]
    assert strict["can_micro_live"] is False
    assert strict["micro_live_allowed"] is False
    assert strict["order_type"] == "limit_only_paper"
    assert strict["paper_only"] is True
    assert strict["live_order_allowed"] is False
    assert strict["status"] == "filled"
    assert strict["market_id"] == "m-seoul-no-20"
    assert strict["token_id"] == "tok-no-20"
    assert strict["strict_limit"] == 0.30
    assert strict["requested_spend_usdc"] == 5.0
    assert strict["source_orderbook"] == {"no_asks": [{"price": 0.28, "size": 100.0}], "no_bids": [{"price": 0.27, "size": 100.0}]}
    assert strict["source_autopilot_gate"] == "PAPER_STRICT"
    assert strict["source_metadata"] == {"station_provider": "official", "refresh_age_seconds": 30}
    assert strict["source_gate_payload"] == {"gate": "PAPER_STRICT", "checks": ["source_confirmed", "risk_approved"]}
    assert strict["portfolio_risk"]["cap_status"] == "approved"
    assert strict["live_execution_payload"] is None

    assert micro["source_autopilot_gate"] == "PAPER_MICRO"
    assert micro["requested_spend_usdc"] == 1.0


def test_paper_autopilot_bridge_refuses_live_or_real_order_gate() -> None:
    artifact = {"live_rows": [{"market_id": "m", "token_id": "t", "autopilot_gate": "LIVE", "strict_limit": 0.2, "orderbook": {"asks": [{"price": 0.2, "size": 1}]}}]}

    with pytest.raises(PaperAutopilotBridgeError, match="refuses non-paper autopilot gate"):
        build_paper_autopilot_ledger(artifact, allow_unknown_gate=False)


def test_paper_autopilot_bridge_always_refuses_live_order_markers_even_on_paper_gate() -> None:
    artifact = {
        "live_rows": [
            {
                "market_id": "m",
                "token_id": "t",
                "autopilot_gate": "PAPER_MICRO",
                "strict_limit": 0.2,
                "paper_notional_usdc": 1.0,
                "live_order_allowed": True,
                "orderbook": {"asks": [{"price": 0.2, "size": 10}]},
            }
        ]
    }

    with pytest.raises(PaperAutopilotBridgeError, match="refuses live/real-order marker"):
        build_paper_autopilot_ledger(artifact)


def test_paper_autopilot_bridge_requires_refresh_orderbook_and_strict_limit() -> None:
    artifact = {"live_rows": [{"market_id": "m", "token_id": "t", "autopilot_gate": "PAPER_STRICT", "strict_limit": 0.2, "paper_notional_usdc": 2.0}]}

    ledger = build_paper_autopilot_ledger(artifact)

    assert ledger["summary"]["orders"] == 0
    assert ledger["paper_autopilot_skipped"] == [{"market_id": "m", "token_id": "t", "gate": "PAPER_STRICT", "reason": "missing_orderbook"}]


def _run_weather_pm(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT / "src")
    return subprocess.run(
        [sys.executable, "-m", "weather_pm.cli", *args],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        env=env,
        check=False,
    )


def test_paper_autopilot_bridge_cli_appends_to_derived_ledger(tmp_path: Path) -> None:
    operator_path = tmp_path / "operator.json"
    ledger_path = tmp_path / "derived" / "paper_autopilot_ledger.json"
    out_dir = tmp_path / "artifacts"
    operator_path.write_text(json.dumps(_operator_artifact()), encoding="utf-8")

    first = _run_weather_pm(
        "paper-autopilot-bridge",
        "--operator-json",
        str(operator_path),
        "--ledger-json",
        str(ledger_path),
        "--run-id",
        "cli-smoke",
        "--output-dir",
        str(out_dir),
    )
    assert first.returncode == 0, first.stderr
    first_payload = json.loads(first.stdout)
    assert first_payload["paper_autopilot_summary"]["appended_orders"] == 2
    assert ledger_path.exists()
    assert len(json.loads(ledger_path.read_text(encoding="utf-8"))["orders"]) == 2

    second = _run_weather_pm(
        "paper-autopilot-bridge",
        "--operator-json",
        str(operator_path),
        "--ledger-json",
        str(ledger_path),
        "--run-id",
        "cli-smoke-2",
        "--output-dir",
        str(out_dir),
    )
    assert second.returncode == 0, second.stderr
    second_payload = json.loads(second.stdout)
    assert second_payload["summary"]["orders"] == 4
    assert second_payload["paper_autopilot_summary"]["appended_orders"] == 2
    assert Path(second_payload["artifacts"]["json"]).exists()
