import json

import pytest

from prediction_core.polymarket_execution import (
    ExecutionRiskLimits,
    ExecutionRiskState,
    JsonlExecutionAuditLog,
    JsonlIdempotencyStore,
)
from prediction_core.polymarket_runtime import run_polymarket_runtime_cycle


@pytest.mark.asyncio
async def test_runtime_cycle_dry_run_rehearsal_submits_via_canonical_executor(tmp_path, monkeypatch):
    monkeypatch.delenv("PREDICTION_CORE_SYNC_DATABASE_URL", raising=False)
    monkeypatch.delenv("PANOPTIQUE_SYNC_DATABASE_URL", raising=False)
    monkeypatch.delenv("PREDICTION_CORE_DATABASE_URL", raising=False)
    monkeypatch.delenv("PANOPTIQUE_DATABASE_URL", raising=False)

    idempotency_path = tmp_path / "ids.jsonl"
    audit_path = tmp_path / "audit.jsonl"

    async def fake_stream_factory(url, subscribe_message):
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
        markets=[
            {
                "id": "m1",
                "question": "Will test market resolve Yes?",
                "clobTokenIds": ["yes-token", "no-token"],
                "outcomes": ["Yes", "No"],
                "liquidity": 2500,
                "closed": False,
            }
        ],
        probabilities={"yes-token": 0.52, "no-token": 0.47},
        stream_factory=fake_stream_factory,
        max_events=2,
        min_edge=0.05,
        paper_notional_usdc=6.0,
        execution_mode="dry_run",
        risk_limits=ExecutionRiskLimits(
            max_order_notional_usdc=10,
            max_total_exposure_usdc=100,
            max_daily_loss_usdc=25,
            max_spread=0.05,
        ),
        risk_state=ExecutionRiskState(total_exposure_usdc=0, daily_realized_pnl_usdc=0),
        idempotency_store=JsonlIdempotencyStore(idempotency_path),
        audit_log=JsonlExecutionAuditLog(audit_path),
    )

    assert result["execution"]["paper_intents"] == []
    assert len(result["execution"]["orders_submitted"]) == 1
    submitted = result["execution"]["orders_submitted"][0]
    assert submitted["executor_result"]["status"] == "dry_run_accepted"
    assert submitted["executor_result"]["exchange_order_id"].startswith("dry-run:")
    assert submitted["order"]["token_id"] == "yes-token"

    id_rows = [json.loads(line) for line in idempotency_path.read_text().splitlines()]
    assert {row["key"] for row in id_rows} == {submitted["order"]["idempotency_key"]}
    assert [row["status"] for row in id_rows] == ["pending", "submitted"]

    audit_rows = [json.loads(line) for line in audit_path.read_text().splitlines()]
    assert [row["event_type"] for row in audit_rows] == [
        "execution_decision_seen",
        "execution_order_submitted",
    ]
    assert audit_rows[1]["payload"]["executor_result"]["status"] == "dry_run_accepted"
