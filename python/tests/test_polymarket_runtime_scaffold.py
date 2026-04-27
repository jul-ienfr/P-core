import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from prediction_core.polymarket_runtime import (
    ExecutionDisabledError,
    LiveExecutionPermit,
    build_polymarket_runtime_scaffold,
    evaluate_cached_market_decisions,
    plan_disabled_execution_actions,
    preflight_polymarket_live_readiness,
    run_polymarket_runtime_cycle,
)
from prediction_core.polymarket_execution import (
    DryRunPolymarketExecutor,
    ClobRestExecutorConfig,
    ClobRestPolymarketExecutor,
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


def test_live_preflight_reports_missing_env_without_secrets_or_executor():
    result = preflight_polymarket_live_readiness(env={"POLYMARKET_PRIVATE_KEY": "secret"})

    assert result["ready"] is False
    assert result["not_ready"] is True
    assert result["checks"]["executor_constructed"] is False
    assert result["checks"]["orders_submitted"] == 0
    assert result["checks"]["cancel_submitted"] is False
    assert result["checks"]["clob_env"]["configured"] == ["POLYMARKET_PRIVATE_KEY"]
    assert "open_orders_not_confirmed" in result["readiness_blockers"]
    assert "secret" not in json.dumps(result)


def test_live_preflight_reports_ready_without_secret_values():
    result = preflight_polymarket_live_readiness(
        env={
            "POLYMARKET_PRIVATE_KEY": "secret-key",
            "POLYMARKET_FUNDER_ADDRESS": "0xabc",
            "POLYMARKET_CHAIN_ID": "137",
            "POLYMARKET_LIVE_ENABLED": "1",
            "POLYMARKET_LIVE_ACK": "I_UNDERSTAND_THIS_SUBMITS_REAL_POLYMARKET_ORDERS",
            "POLYMARKET_MAX_ORDER_NOTIONAL_USDC": "10",
        }
    )

    assert result["ready"] is False
    assert result["not_ready"] is True
    assert result["credentials_ready"] is True
    assert result["live_submission_wired"] is False
    assert result["execution_available"] is False
    assert result["checks"]["clob_env"]["missing"] == []
    assert "secret-key" not in json.dumps(result)
    assert "0xabc" not in json.dumps(result)


def test_live_preflight_blocks_when_open_orders_source_reports_orders():
    executor = DryRunPolymarketExecutor(open_orders=[{"id": "ord-1", "status": "open", "token_id": "yes-token"}])

    result = preflight_polymarket_live_readiness(
        env={
            "POLYMARKET_PRIVATE_KEY": "secret-key",
            "POLYMARKET_FUNDER_ADDRESS": "0xabc",
            "POLYMARKET_CHAIN_ID": "137",
            "POLYMARKET_LIVE_ENABLED": "1",
            "POLYMARKET_LIVE_ACK": "I_UNDERSTAND_THIS_SUBMITS_REAL_POLYMARKET_ORDERS",
            "POLYMARKET_MAX_ORDER_NOTIONAL_USDC": "10",
        },
        order_management=executor,
        local_orders=[],
        positions_confirmed=True,
    )

    assert result["ready"] is False
    assert result["open_orders_confirmed"] is False
    assert result["checks"]["open_orders"]["source_injected"] is True
    assert result["checks"]["open_orders"]["count"] == 1
    assert result["checks"]["reconciliation"]["unexpected_on_exchange"] == ["ord-1"]
    assert result["checks"]["cancel_submitted"] is False
    assert executor.cancel_requests == []


def test_live_preflight_can_confirm_empty_read_only_sources_but_still_blocks_submit():
    result = preflight_polymarket_live_readiness(
        env={
            "POLYMARKET_PRIVATE_KEY": "secret-key",
            "POLYMARKET_FUNDER_ADDRESS": "0xabc",
            "POLYMARKET_CHAIN_ID": "137",
            "POLYMARKET_LIVE_ENABLED": "1",
            "POLYMARKET_LIVE_ACK": "I_UNDERSTAND_THIS_SUBMITS_REAL_POLYMARKET_ORDERS",
            "POLYMARKET_MAX_ORDER_NOTIONAL_USDC": "10",
        },
        order_management=DryRunPolymarketExecutor(),
        positions_confirmed=True,
    )

    assert result["ready"] is False
    assert result["open_orders_confirmed"] is True
    assert result["positions_confirmed"] is True
    assert result["checks"]["reconciliation"]["status"] == "ok"
    assert result["readiness_blockers"] == ["live_submission_unavailable"]


def test_live_preflight_can_be_ready_with_live_executor_and_clean_read_only_sources():
    executor = ClobRestPolymarketExecutor(
        config=ClobRestExecutorConfig(
            private_key="secret-key",
            funder_address="0xabc",
            chain_id=137,
            live_enabled=True,
            live_ack="I_UNDERSTAND_THIS_SUBMITS_REAL_POLYMARKET_ORDERS",
            allow_order_submission=True,
            max_order_notional_usdc=10,
        ),
        client=DryRunPolymarketExecutor(),
    )

    result = preflight_polymarket_live_readiness(
        env={
            "POLYMARKET_PRIVATE_KEY": "secret-key",
            "POLYMARKET_FUNDER_ADDRESS": "0xabc",
            "POLYMARKET_CHAIN_ID": "137",
            "POLYMARKET_LIVE_ENABLED": "1",
            "POLYMARKET_LIVE_ACK": "I_UNDERSTAND_THIS_SUBMITS_REAL_POLYMARKET_ORDERS",
            "POLYMARKET_MAX_ORDER_NOTIONAL_USDC": "10",
        },
        order_management=executor,
        positions_confirmed=True,
    )

    assert result["ready"] is True
    assert result["execution_available"] is True
    assert result["readiness_blockers"] == []
    assert "secret-key" not in json.dumps(result)


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


def test_evaluate_cached_market_decisions_blocks_stale_and_invalid_snapshots(sample_markets):
    result = evaluate_cached_market_decisions(
        markets=sample_markets,
        snapshots={
            "yes-token": {
                "token_id": "yes-token",
                "best_bid": 0.41,
                "best_ask": 0.44,
                "spread": 0.03,
                "received_at": "2000-01-01T00:00:00Z",
                "valid": True,
            },
            "no-token": {
                "token_id": "no-token",
                "best_bid": 0.6,
                "best_ask": 0.55,
                "spread": -0.05,
                "received_at": "2999-01-01T00:00:00Z",
                "valid": False,
                "invalid_reason": "crossed_book",
            },
        },
        probabilities={"yes-token": 0.9, "no-token": 0.9},
        min_edge=0.01,
        max_snapshot_age_seconds=5,
    )

    assert [decision["wait_reason"] for decision in result["decisions"]] == ["stale_snapshot", "crossed_book"]
    assert result["summary"]["stale_snapshot_count"] == 1
    assert result["summary"]["invalid_snapshot_count"] == 1


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


def test_disabled_execution_planner_rejects_invalid_paper_notional():
    decisions = [
        {
            "market_id": "m1",
            "token_id": "yes-token",
            "outcome": "Yes",
            "action": "PAPER_SIGNAL_ONLY",
            "best_ask": 0.44,
        }
    ]

    with pytest.raises(ValueError, match="notional_usdc must be finite and positive"):
        plan_disabled_execution_actions(decisions, notional_usdc=float("nan"))


def test_disabled_execution_planner_refuses_real_order_submission():
    with pytest.raises(ExecutionDisabledError, match="real Polymarket execution is disabled"):
        plan_disabled_execution_actions([], execution_enabled=True)


def test_live_preflight_catches_and_sanitizes_open_order_errors():
    class ExplodingOrderManagement:
        def list_open_orders(self):
            raise RuntimeError("cannot list with secret-key or 0xabc")

        def cancel_order(self, exchange_order_id):
            raise AssertionError("cancel must not be called")

    result = preflight_polymarket_live_readiness(
        env={
            "POLYMARKET_PRIVATE_KEY": "secret-key",
            "POLYMARKET_FUNDER_ADDRESS": "0xabc",
            "POLYMARKET_CHAIN_ID": "137",
            "POLYMARKET_LIVE_ENABLED": "1",
            "POLYMARKET_LIVE_ACK": "I_UNDERSTAND_THIS_SUBMITS_REAL_POLYMARKET_ORDERS",
            "POLYMARKET_MAX_ORDER_NOTIONAL_USDC": "10",
        },
        order_management=ExplodingOrderManagement(),
        positions_confirmed=True,
    )

    assert result["ready"] is False
    assert result["open_orders_confirmed"] is False
    assert "open_orders_check_failed" in result["readiness_blockers"]
    assert result["checks"]["open_orders"]["error"]["type"] == "RuntimeError"
    assert "[redacted]" in result["checks"]["open_orders"]["error"]["message"]
    assert "secret-key" not in json.dumps(result)
    assert "0xabc" not in json.dumps(result)


def test_execution_mode_live_is_blocked_without_executor():
    decisions = [
        {
            "market_id": "m1",
            "token_id": "yes-token",
            "outcome": "Yes",
            "action": "PAPER_SIGNAL_ONLY",
            "best_ask": 0.44,
        }
    ]

    with pytest.raises(ExecutionDisabledError, match="explicit executor"):
        plan_disabled_execution_actions(decisions, execution_mode="live")


def test_execution_mode_live_refuses_injected_executor_without_permit(tmp_path):
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

    with pytest.raises(ExecutionDisabledError, match="ready preflight permit"):
        plan_disabled_execution_actions(
            decisions,
            notional_usdc=7.5,
            execution_mode="live",
            order_executor=executor,
            risk_limits=ExecutionRiskLimits(max_order_notional_usdc=10, max_total_exposure_usdc=100, max_daily_loss_usdc=25, max_spread=0.05),
            risk_state=ExecutionRiskState(),
            idempotency_store=JsonlIdempotencyStore(tmp_path / "ids.jsonl"),
            audit_log=JsonlExecutionAuditLog(tmp_path / "audit.jsonl"),
        )

    assert executor.orders == []


def test_execution_mode_live_submits_with_fake_executor_and_permit(tmp_path):
    decisions = [{"market_id": "m1", "token_id": "yes-token", "outcome": "Yes", "action": "PAPER_SIGNAL_ONLY", "best_ask": 0.44, "spread": 0.03}]
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
        live_permit=LiveExecutionPermit(preflight_ready=True, operator_ack="I_UNDERSTAND_THIS_SUBMITS_REAL_POLYMARKET_ORDERS", positions_confirmed=True),
        max_orders_per_cycle=1,
    )

    assert len(plan["orders_submitted"]) == 1
    assert executor.orders[0].token_id == "yes-token"
    assert plan["summary"]["submitted_count"] == 1


def test_execution_mode_live_requires_risk_idempotency_and_audit(tmp_path):
    decisions = [{"market_id": "m1", "token_id": "yes-token", "outcome": "Yes", "action": "PAPER_SIGNAL_ONLY", "best_ask": 0.44, "spread": 0.03}]
    executor = DryRunPolymarketExecutor()

    with pytest.raises(ExecutionDisabledError, match="risk limits and risk state"):
        plan_disabled_execution_actions(decisions, execution_mode="dry_run", order_executor=executor)

    with pytest.raises(ExecutionDisabledError, match="idempotency store and audit log"):
        plan_disabled_execution_actions(
            decisions,
            execution_mode="dry_run",
            order_executor=executor,
            risk_limits=ExecutionRiskLimits(max_order_notional_usdc=10, max_total_exposure_usdc=100, max_daily_loss_usdc=25, max_spread=0.05),
            risk_state=ExecutionRiskState(),
        )


class RejectingExecutor:
    def submit_order(self, order):
        return OrderResult(
            accepted=False,
            status="rejected_by_exchange",
            idempotency_key=order.idempotency_key,
            raw_response={"reason": "insufficient balance"},
        )


class FakeRealSubmittingExecutor:
    def __init__(self):
        self.called = False

    def submit_order(self, order):
        self.called = True
        raise AssertionError("real executor must not be called in dry_run")


def test_dry_run_refuses_injected_non_dry_run_executor_without_calling_it(tmp_path):
    decisions = [{"market_id": "m1", "token_id": "yes-token", "outcome": "Yes", "action": "PAPER_SIGNAL_ONLY", "best_ask": 0.44, "spread": 0.03}]
    idempotency_path = tmp_path / "ids.jsonl"
    executor = FakeRealSubmittingExecutor()

    with pytest.raises(ExecutionDisabledError, match="only accepts the built-in DryRunPolymarketExecutor"):
        plan_disabled_execution_actions(
            decisions,
            execution_mode="dry_run",
            order_executor=executor,
            risk_limits=ExecutionRiskLimits(max_order_notional_usdc=10, max_total_exposure_usdc=100, max_daily_loss_usdc=25, max_spread=0.05),
            risk_state=ExecutionRiskState(),
            idempotency_store=JsonlIdempotencyStore(idempotency_path),
            audit_log=JsonlExecutionAuditLog(tmp_path / "audit.jsonl"),
        )

    assert executor.called is False
    assert not idempotency_path.exists()


def test_dry_run_planner_applies_reserved_exposure_within_single_run(tmp_path):
    decisions = [
        {"market_id": "m1", "token_id": "yes-token", "outcome": "Yes", "action": "PAPER_SIGNAL_ONLY", "best_ask": 0.44, "spread": 0.03},
        {"market_id": "m1", "token_id": "no-token", "outcome": "No", "action": "PAPER_SIGNAL_ONLY", "best_ask": 0.44, "spread": 0.03},
    ]
    executor = DryRunPolymarketExecutor()

    plan = plan_disabled_execution_actions(
        decisions,
        notional_usdc=60,
        execution_mode="dry_run",
        order_executor=executor,
        risk_limits=ExecutionRiskLimits(max_order_notional_usdc=100, max_total_exposure_usdc=100, max_daily_loss_usdc=25, max_spread=0.05),
        risk_state=ExecutionRiskState(),
        idempotency_store=JsonlIdempotencyStore(tmp_path / "ids.jsonl"),
        audit_log=JsonlExecutionAuditLog(tmp_path / "audit.jsonl"),
    )

    assert len(plan["orders_submitted"]) == 1
    assert plan["order_attempts"][1]["status"] == "risk_blocked"
    assert plan["order_attempts"][1]["risk"]["blocked_by"] == ["max_total_exposure_usdc"]
    assert plan["summary"]["submitted_count"] == 1
    assert plan["summary"]["risk_blocked_count"] == 1


def test_dry_run_planner_blocks_wide_spread_without_calling_executor(tmp_path):
    decisions = [{"market_id": "m1", "token_id": "yes-token", "outcome": "Yes", "action": "PAPER_SIGNAL_ONLY", "best_bid": 0.30, "best_ask": 0.44, "spread": 0.14}]
    executor = DryRunPolymarketExecutor()

    plan = plan_disabled_execution_actions(
        decisions,
        execution_mode="dry_run",
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
    assert plan["summary"]["risk_blocked_count"] == 1
    assert plan["summary"]["submitted_count"] == 0


def test_dry_run_planner_skips_duplicate_idempotency_key_and_audits(tmp_path):
    decisions = [{"market_id": "m1", "token_id": "yes-token", "outcome": "Yes", "action": "PAPER_SIGNAL_ONLY", "best_ask": 0.44, "spread": 0.03}]
    store = JsonlIdempotencyStore(tmp_path / "ids.jsonl")
    duplicate_key = "m1:yes-token:BUY:0.44:5.0"
    assert store.claim(duplicate_key) is True
    audit_path = tmp_path / "audit.jsonl"

    plan = plan_disabled_execution_actions(
        decisions,
        execution_mode="dry_run",
        order_executor=DryRunPolymarketExecutor(),
        risk_limits=ExecutionRiskLimits(max_order_notional_usdc=10, max_total_exposure_usdc=100, max_daily_loss_usdc=25, max_spread=0.05),
        risk_state=ExecutionRiskState(),
        idempotency_store=store,
        audit_log=JsonlExecutionAuditLog(audit_path),
    )

    assert plan["orders_submitted"] == []
    assert plan["order_attempts"][0]["status"] == "duplicate_skipped"
    assert plan["order_attempts"][0]["idempotency_key"] == duplicate_key
    assert plan["summary"]["duplicate_skipped_count"] == 1
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
    assert result["execution"]["summary"]["submitted_count"] == 0


def test_live_preflight_cli_outputs_json_without_env_secret_values():
    env = _pythonpath_env()
    env["POLYMARKET_PRIVATE_KEY"] = "secret-key"
    env["POLYMARKET_FUNDER_ADDRESS"] = "0xabc"
    env["POLYMARKET_CHAIN_ID"] = "137"
    result = subprocess.run(
        [str(SCRIPT), "polymarket-live-preflight"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["ready"] is False
    assert payload["credentials_ready"] is True
    assert payload["live_submission_wired"] is False
    assert payload["checks"]["executor_constructed"] is False
    assert "secret-key" not in result.stdout
    assert "0xabc" not in result.stdout


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


def test_runtime_cycle_cli_uses_postgres_secondary_when_sync_url_configured(monkeypatch, tmp_path, capsys):
    from prediction_core import app
    from prediction_core.polymarket_execution import CompositeExecutionAuditLog, CompositeIdempotencyStore

    markets_path = tmp_path / "markets.json"
    events_path = tmp_path / "events.jsonl"
    probabilities_path = tmp_path / "probabilities.json"
    idempotency_path = tmp_path / "ids.jsonl"
    audit_path = tmp_path / "audit.jsonl"
    markets_path.write_text("[]", encoding="utf-8")
    events_path.write_text("", encoding="utf-8")
    probabilities_path.write_text("{}", encoding="utf-8")
    repository = object()
    captured = {}

    async def fake_run_polymarket_runtime_cycle(**kwargs):
        captured.update(kwargs)
        return {"ok": True}

    monkeypatch.setenv("PREDICTION_CORE_SYNC_DATABASE_URL", "postgresql+psycopg://user:pass@localhost/db")
    monkeypatch.delenv("PANOPTIQUE_SYNC_DATABASE_URL", raising=False)
    with patch.object(sys, "argv", [
        "prediction-core",
        "polymarket-runtime-cycle",
        "--markets-json", str(markets_path),
        "--dry-run-events-jsonl", str(events_path),
        "--probabilities-json", str(probabilities_path),
        "--max-events", "1",
        "--execution-mode", "dry_run",
        "--idempotency-jsonl", str(idempotency_path),
        "--audit-jsonl", str(audit_path),
        "--max-order-notional-usdc", "10",
        "--max-total-exposure-usdc", "100",
        "--max-daily-loss-usdc", "25",
        "--max-spread", "0.05",
    ]), patch.object(app, "run_polymarket_runtime_cycle", fake_run_polymarket_runtime_cycle), patch(
        "prediction_core.storage.postgres.create_prediction_core_sync_engine_from_env", return_value="engine"
    ), patch("prediction_core.storage.postgres.OperationalStateRepository", return_value=repository):
        assert app.main() == 0

    assert json.loads(capsys.readouterr().out) == {"ok": True}
    assert isinstance(captured["idempotency_store"], CompositeIdempotencyStore)
    assert isinstance(captured["audit_log"], CompositeExecutionAuditLog)
    assert captured["idempotency_store"].primary.path == idempotency_path
    assert captured["idempotency_store"].secondary.repository is repository
    assert captured["audit_log"].primary.path == audit_path
    assert captured["audit_log"].secondary.repository is repository


def test_runtime_cycle_cli_keeps_jsonl_only_when_postgres_wiring_fails(monkeypatch, tmp_path, capsys):
    from prediction_core import app

    markets_path = tmp_path / "markets.json"
    events_path = tmp_path / "events.jsonl"
    probabilities_path = tmp_path / "probabilities.json"
    idempotency_path = tmp_path / "ids.jsonl"
    audit_path = tmp_path / "audit.jsonl"
    markets_path.write_text("[]", encoding="utf-8")
    events_path.write_text("", encoding="utf-8")
    probabilities_path.write_text("{}", encoding="utf-8")
    captured = {}

    async def fake_run_polymarket_runtime_cycle(**kwargs):
        captured.update(kwargs)
        return {"ok": True}

    monkeypatch.setenv("PREDICTION_CORE_SYNC_DATABASE_URL", "postgresql+psycopg://user:pass@localhost/db")
    with pytest.warns(RuntimeWarning, match="Postgres dual-write setup failed; continuing with JSONL primary behavior: RuntimeError"):
        with patch.object(sys, "argv", [
            "prediction-core",
            "polymarket-runtime-cycle",
            "--markets-json", str(markets_path),
            "--dry-run-events-jsonl", str(events_path),
            "--probabilities-json", str(probabilities_path),
            "--max-events", "1",
            "--execution-mode", "dry_run",
            "--idempotency-jsonl", str(idempotency_path),
            "--audit-jsonl", str(audit_path),
            "--max-order-notional-usdc", "10",
            "--max-total-exposure-usdc", "100",
            "--max-daily-loss-usdc", "25",
            "--max-spread", "0.05",
        ]), patch.object(app, "run_polymarket_runtime_cycle", fake_run_polymarket_runtime_cycle), patch(
            "prediction_core.storage.postgres.create_prediction_core_sync_engine_from_env", side_effect=RuntimeError("unavailable")
        ):
            assert app.main() == 0

    assert json.loads(capsys.readouterr().out) == {"ok": True}
    assert isinstance(captured["idempotency_store"], JsonlIdempotencyStore)
    assert isinstance(captured["audit_log"], JsonlExecutionAuditLog)
    assert captured["idempotency_store"].path == idempotency_path
    assert captured["audit_log"].path == audit_path


def test_runtime_cycle_cli_offers_live_execution_mode_with_guardrails():
    result = subprocess.run(
        [str(SCRIPT), "polymarket-runtime-cycle", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "--execution-mode {paper,dry_run,live}" in result.stdout
    assert "--i-understand-live-orders" in result.stdout


def test_runtime_cycle_cli_rejects_live_execution_mode(tmp_path):
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

    assert result.returncode == 2
    assert "--execution-mode live requires --i-understand-live-orders" in result.stderr


def test_runtime_cycle_cli_rejects_non_finite_paper_notional(tmp_path):
    markets_path = tmp_path / "markets.json"
    events_path = tmp_path / "events.jsonl"
    probabilities_path = tmp_path / "probabilities.json"
    markets_path.write_text("[]", encoding="utf-8")
    events_path.write_text("", encoding="utf-8")
    probabilities_path.write_text("{}", encoding="utf-8")

    result = subprocess.run(
        [
            str(SCRIPT),
            "polymarket-runtime-cycle",
            "--markets-json", str(markets_path),
            "--dry-run-events-jsonl", str(events_path),
            "--probabilities-json", str(probabilities_path),
            "--max-events", "1",
            "--paper-notional-usdc", "nan",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "--paper-notional-usdc must be finite and positive" in result.stderr


def test_runtime_cycle_cli_rejects_non_finite_risk_limits(tmp_path):
    markets_path = tmp_path / "markets.json"
    events_path = tmp_path / "events.jsonl"
    probabilities_path = tmp_path / "probabilities.json"
    markets_path.write_text("[]", encoding="utf-8")
    events_path.write_text("", encoding="utf-8")
    probabilities_path.write_text("{}", encoding="utf-8")

    result = subprocess.run(
        [
            str(SCRIPT),
            "polymarket-runtime-cycle",
            "--markets-json", str(markets_path),
            "--dry-run-events-jsonl", str(events_path),
            "--probabilities-json", str(probabilities_path),
            "--max-events", "1",
            "--execution-mode", "dry_run",
            "--idempotency-jsonl", str(tmp_path / "ids.jsonl"),
            "--audit-jsonl", str(tmp_path / "audit.jsonl"),
            "--max-order-notional-usdc", "nan",
            "--max-total-exposure-usdc", "100",
            "--max-daily-loss-usdc", "25",
            "--max-spread", "0.05",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "max_order_notional_usdc must be finite and positive" in result.stderr
