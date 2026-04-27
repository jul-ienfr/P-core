import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from prediction_core.polymarket_runtime import (
    ExecutionDisabledError,
    build_polymarket_runtime_scaffold,
    evaluate_cached_market_decisions,
    plan_disabled_execution_actions,
    run_polymarket_runtime_cycle,
)
from prediction_core.polymarket_execution import (
    DryRunPolymarketExecutor,
    ExecutionRiskLimits,
    ExecutionRiskState,
    JsonlExecutionAuditLog,
    JsonlIdempotencyStore,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "prediction-core"


def _pythonpath_env():
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT / "src")
    return env


@pytest.fixture
def sample_markets():
    return [
        {
            "id": "m1",
            "question": "Will test market resolve Yes?",
            "clobTokenIds": json.dumps(["yes-token", "no-token"]),
            "outcomes": json.dumps(["Yes", "No"]),
            "liquidity": 2500,
            "closed": False,
        },
        {
            "id": "m2",
            "question": "Closed market",
            "clobTokenIds": ["closed-yes", "closed-no"],
            "liquidity": 9999,
            "closed": True,
        },
    ]


def test_runtime_scaffold_declares_all_workers_and_execution_disabled():
    scaffold = build_polymarket_runtime_scaffold()

    assert scaffold["mode"] == "paper/read-only polymarket runtime scaffold"
    assert scaffold["execution_enabled"] is False
    assert scaffold["workers"]["discovery_worker"]["status"] == "configured"
    assert scaffold["workers"]["marketdata_worker"]["status"] == "configured"
    assert scaffold["workers"]["decision_worker"]["status"] == "configured"
    assert scaffold["workers"]["execution_worker"]["status"] == "disabled"
    assert scaffold["workers"]["analytics_worker"]["status"] == "configured"
    assert scaffold["guardrails"]["no_real_orders"] is True


def test_evaluate_cached_market_decisions_scores_edges_without_execution(sample_markets):
    snapshots = {
        "yes-token": {"token_id": "yes-token", "best_bid": 0.41, "best_ask": 0.44, "spread": 0.03, "bid_depth": 5.0, "ask_depth": 2.0},
        "no-token": {"token_id": "no-token", "best_bid": 0.55, "best_ask": 0.58, "spread": 0.03, "bid_depth": 4.0, "ask_depth": 3.0},
    }

    result = evaluate_cached_market_decisions(
        markets=sample_markets,
        snapshots=snapshots,
        probabilities={"yes-token": 0.52, "no-token": 0.47},
        min_edge=0.05,
    )

    assert result["mode"] == "paper/read-only local decision scaffold"
    assert len(result["decisions"]) == 2
    yes_decision = result["decisions"][0]
    assert yes_decision["market_id"] == "m1"
    assert yes_decision["outcome"] == "Yes"
    assert yes_decision["edge_vs_ask"] == pytest.approx(0.08)
    assert yes_decision["action"] == "PAPER_SIGNAL_ONLY"
    assert yes_decision["execution_enabled"] is False
    assert result["summary"]["paper_signal_count"] == 1
    assert result["summary"]["missing_snapshot_count"] == 0


def test_evaluate_cached_market_decisions_marks_missing_marketdata_as_wait(sample_markets):
    result = evaluate_cached_market_decisions(
        markets=sample_markets,
        snapshots={},
        probabilities={"yes-token": 0.9},
        min_edge=0.01,
    )

    assert {decision["action"] for decision in result["decisions"]} == {"WAIT_MARKETDATA"}
    assert result["summary"]["missing_snapshot_count"] == 2


def test_disabled_execution_planner_returns_audit_records_not_orders():
    decisions = [
        {
            "market_id": "m1",
            "token_id": "yes-token",
            "outcome": "Yes",
            "action": "PAPER_SIGNAL_ONLY",
            "best_ask": 0.44,
            "model_probability": 0.52,
            "edge_vs_ask": 0.08,
        }
    ]

    plan = plan_disabled_execution_actions(decisions, notional_usdc=7.5)

    assert plan["execution_enabled"] is False
    assert plan["orders_submitted"] == []
    assert plan["paper_intents"] == [
        {
            "market_id": "m1",
            "token_id": "yes-token",
            "outcome": "Yes",
            "side": "BUY",
            "limit_price": 0.44,
            "notional_usdc": 7.5,
            "reason": "execution disabled; paper intent only",
        }
    ]


def test_disabled_execution_planner_refuses_real_order_submission():
    with pytest.raises(ExecutionDisabledError, match="real Polymarket execution is disabled"):
        plan_disabled_execution_actions([], execution_enabled=True)


def test_execution_mode_live_requires_explicit_order_executor():
    decisions = [
        {
            "market_id": "m1",
            "token_id": "yes-token",
            "outcome": "Yes",
            "action": "PAPER_SIGNAL_ONLY",
            "best_ask": 0.44,
        }
    ]

    with pytest.raises(ExecutionDisabledError, match="live execution requires an explicit order executor"):
        plan_disabled_execution_actions(decisions, execution_mode="live")


def test_execution_mode_live_routes_orders_only_through_injected_executor(tmp_path):
    decisions = [
        {
            "market_id": "m1",
            "token_id": "yes-token",
            "outcome": "Yes",
            "action": "PAPER_SIGNAL_ONLY",
            "best_ask": 0.44,
            "spread": 0.03,
        }
    ]
    executor = DryRunPolymarketExecutor()

    plan = plan_disabled_execution_actions(
        decisions,
        notional_usdc=7.5,
        execution_mode="live",
        order_executor=executor,
        risk_limits=ExecutionRiskLimits(max_order_notional_usdc=10, max_total_exposure_usdc=100, max_daily_loss_usdc=25, max_spread=0.05),
        risk_state=ExecutionRiskState(),
        idempotency_store=JsonlIdempotencyStore(tmp_path / "ids.jsonl"),
        audit_log=JsonlExecutionAuditLog(tmp_path / "audit.jsonl"),
    )

    assert plan["execution_enabled"] is True
    assert plan["paper_intents"] == []
    assert len(executor.orders) == 1
    assert executor.orders[0].token_id == "yes-token"
    assert plan["orders_submitted"][0]["executor_result"]["status"] == "dry_run_accepted"
    assert plan["orders_submitted"][0]["order"]["side"] == "buy"


def test_execution_mode_live_requires_risk_idempotency_and_audit(tmp_path):
    decisions = [{"market_id": "m1", "token_id": "yes-token", "outcome": "Yes", "action": "PAPER_SIGNAL_ONLY", "best_ask": 0.44, "spread": 0.03}]
    executor = DryRunPolymarketExecutor()

    with pytest.raises(ExecutionDisabledError, match="risk limits and risk state"):
        plan_disabled_execution_actions(decisions, execution_mode="live", order_executor=executor)

    with pytest.raises(ExecutionDisabledError, match="idempotency store and audit log"):
        plan_disabled_execution_actions(
            decisions,
            execution_mode="live",
            order_executor=executor,
            risk_limits=ExecutionRiskLimits(max_order_notional_usdc=10, max_total_exposure_usdc=100, max_daily_loss_usdc=25, max_spread=0.05),
            risk_state=ExecutionRiskState(),
        )


def test_live_planner_blocks_wide_spread_without_calling_executor(tmp_path):
    decisions = [{"market_id": "m1", "token_id": "yes-token", "outcome": "Yes", "action": "PAPER_SIGNAL_ONLY", "best_bid": 0.30, "best_ask": 0.44, "spread": 0.14}]
    executor = DryRunPolymarketExecutor()

    plan = plan_disabled_execution_actions(
        decisions,
        execution_mode="live",
        order_executor=executor,
        risk_limits=ExecutionRiskLimits(max_order_notional_usdc=10, max_total_exposure_usdc=100, max_daily_loss_usdc=25, max_spread=0.05),
        risk_state=ExecutionRiskState(),
        idempotency_store=JsonlIdempotencyStore(tmp_path / "ids.jsonl"),
        audit_log=JsonlExecutionAuditLog(tmp_path / "audit.jsonl"),
    )

    assert executor.orders == []
    assert plan["orders_submitted"] == []
    assert plan["order_attempts"][0]["status"] == "risk_blocked"
    assert plan["order_attempts"][0]["risk"]["blocked_by"] == ["max_spread"]


def test_live_planner_skips_duplicate_idempotency_key_and_audits(tmp_path):
    decisions = [{"market_id": "m1", "token_id": "yes-token", "outcome": "Yes", "action": "PAPER_SIGNAL_ONLY", "best_ask": 0.44, "spread": 0.03}]
    store = JsonlIdempotencyStore(tmp_path / "ids.jsonl")
    duplicate_key = "m1:yes-token:BUY:0.44:5.0"
    assert store.claim(duplicate_key) is True
    audit_path = tmp_path / "audit.jsonl"

    plan = plan_disabled_execution_actions(
        decisions,
        execution_mode="live",
        order_executor=DryRunPolymarketExecutor(),
        risk_limits=ExecutionRiskLimits(max_order_notional_usdc=10, max_total_exposure_usdc=100, max_daily_loss_usdc=25, max_spread=0.05),
        risk_state=ExecutionRiskState(),
        idempotency_store=store,
        audit_log=JsonlExecutionAuditLog(audit_path),
    )

    assert plan["orders_submitted"] == []
    assert plan["order_attempts"][0]["status"] == "duplicate_skipped"
    assert plan["order_attempts"][0]["idempotency_key"] == duplicate_key
    audit_events = [json.loads(line)["event_type"] for line in audit_path.read_text().splitlines()]
    assert audit_events == ["execution_decision_seen", "execution_order_blocked"]


@pytest.mark.asyncio
async def test_runtime_cycle_wires_discovery_stream_decision_and_disabled_execution(sample_markets):
    async def fake_stream_factory(url, subscribe_message):
        assert subscribe_message == {"type": "market", "assets_ids": ["yes-token", "no-token"]}
        yield {
            "event_type": "book",
            "asset_id": "yes-token",
            "bids": [{"price": "0.41", "size": "5"}],
            "asks": [{"price": "0.44", "size": "2"}],
            "sequence": 20,
        }
        yield {
            "event_type": "book",
            "asset_id": "no-token",
            "bids": [{"price": "0.55", "size": "4"}],
            "asks": [{"price": "0.58", "size": "3"}],
            "sequence": 21,
        }

    result = await run_polymarket_runtime_cycle(
        markets=sample_markets,
        probabilities={"yes-token": 0.52, "no-token": 0.47},
        stream_factory=fake_stream_factory,
        max_events=2,
        min_liquidity=100,
        min_edge=0.05,
        paper_notional_usdc=6.0,
    )

    assert result["mode"] == "paper/read-only polymarket runtime cycle"
    assert result["marketdata"]["processed_events"] == 2
    assert result["decisions"]["summary"]["paper_signal_count"] == 1
    assert result["execution"]["orders_submitted"] == []
    assert result["execution"]["paper_intents"][0]["notional_usdc"] == 6.0


def test_runtime_plan_cli_outputs_complete_scaffold():
    result = subprocess.run(
        [str(SCRIPT), "polymarket-runtime-plan"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["execution_enabled"] is False
    assert payload["workers"]["execution_worker"]["status"] == "disabled"


def test_runtime_cycle_cli_runs_dry_run_fixture_without_real_orders(tmp_path):
    markets_path = tmp_path / "markets.json"
    events_path = tmp_path / "events.jsonl"
    probabilities_path = tmp_path / "probabilities.json"
    markets_path.write_text(
        json.dumps(
            [
                {
                    "id": "m1",
                    "question": "Will test market resolve Yes?",
                    "clobTokenIds": ["yes-token", "no-token"],
                    "outcomes": ["Yes", "No"],
                    "liquidity": 2500,
                    "closed": False,
                }
            ]
        ),
        encoding="utf-8",
    )
    events_path.write_text(
        "\n".join(
            [
                json.dumps({"event_type": "book", "asset_id": "yes-token", "bids": [{"price": "0.41", "size": "5"}], "asks": [{"price": "0.44", "size": "2"}]}),
                json.dumps({"event_type": "book", "asset_id": "no-token", "bids": [{"price": "0.55", "size": "4"}], "asks": [{"price": "0.58", "size": "3"}]}),
            ]
        ),
        encoding="utf-8",
    )
    probabilities_path.write_text(json.dumps({"yes-token": 0.52, "no-token": 0.47}), encoding="utf-8")

    result = subprocess.run(
        [
            str(SCRIPT),
            "polymarket-runtime-cycle",
            "--markets-json",
            str(markets_path),
            "--dry-run-events-jsonl",
            str(events_path),
            "--probabilities-json",
            str(probabilities_path),
            "--max-events",
            "2",
            "--paper-notional-usdc",
            "6",
            "--min-edge",
            "0.05",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["execution"]["orders_submitted"] == []
    assert payload["execution"]["paper_intents"][0]["token_id"] == "yes-token"
    assert payload["guardrails"]["no_real_orders"] is True


def test_runtime_cycle_cli_dry_run_submits_with_required_safety_paths(tmp_path):
    markets_path = tmp_path / "markets.json"
    events_path = tmp_path / "events.jsonl"
    probabilities_path = tmp_path / "probabilities.json"
    idempotency_path = tmp_path / "ids.jsonl"
    audit_path = tmp_path / "audit.jsonl"
    markets_path.write_text(
        json.dumps([{"id": "m1", "question": "q", "clobTokenIds": ["yes-token", "no-token"], "outcomes": ["Yes", "No"], "liquidity": 2500, "closed": False}]),
        encoding="utf-8",
    )
    events_path.write_text(
        "\n".join([
            json.dumps({"event_type": "book", "asset_id": "yes-token", "bids": [{"price": "0.41", "size": "5"}], "asks": [{"price": "0.44", "size": "2"}]}),
            json.dumps({"event_type": "book", "asset_id": "no-token", "bids": [{"price": "0.55", "size": "4"}], "asks": [{"price": "0.58", "size": "3"}]}),
        ]),
        encoding="utf-8",
    )
    probabilities_path.write_text(json.dumps({"yes-token": 0.52, "no-token": 0.47}), encoding="utf-8")

    result = subprocess.run(
        [
            str(SCRIPT),
            "polymarket-runtime-cycle",
            "--markets-json", str(markets_path),
            "--dry-run-events-jsonl", str(events_path),
            "--probabilities-json", str(probabilities_path),
            "--max-events", "2",
            "--paper-notional-usdc", "6",
            "--min-edge", "0.05",
            "--execution-mode", "dry_run",
            "--idempotency-jsonl", str(idempotency_path),
            "--audit-jsonl", str(audit_path),
            "--max-order-notional-usdc", "10",
            "--max-total-exposure-usdc", "100",
            "--max-daily-loss-usdc", "25",
            "--max-spread", "0.05",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["execution"]["orders_submitted"][0]["executor_result"]["status"] == "dry_run_accepted"
    assert payload["execution"]["paper_intents"] == []


def test_runtime_cycle_cli_live_fails_closed_without_operator_setup(tmp_path):
    markets_path = tmp_path / "markets.json"
    events_path = tmp_path / "events.jsonl"
    probabilities_path = tmp_path / "probabilities.json"
    markets_path.write_text("[]", encoding="utf-8")
    events_path.write_text("", encoding="utf-8")
    probabilities_path.write_text("{}", encoding="utf-8")

    result = subprocess.run(
        [str(SCRIPT), "polymarket-runtime-cycle", "--markets-json", str(markets_path), "--dry-run-events-jsonl", str(events_path), "--probabilities-json", str(probabilities_path), "--max-events", "1", "--execution-mode", "live"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "live execution requires --idempotency-jsonl, --audit-jsonl, and risk limits" in result.stderr
