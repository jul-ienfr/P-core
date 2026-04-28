import json

import pytest

from prediction_core.polymarket_daemon import PolymarketDaemonConfig, polymarket_daemon_ops_status, run_polymarket_daemon_once
from prediction_core.polymarket_execution import DryRunPolymarketExecutor, OrderResult
from prediction_core.polymarket_runtime import LIVE_ACK_PHRASE


MARKETS = [
    {
        "id": "m1",
        "question": "Will it rain?",
        "clobTokenIds": ["yes-token"],
        "outcomes": ["Yes"],
        "liquidity": 1000,
        "closed": False,
    }
]
PROBABILITIES = {"yes-token": 0.7}
EVENT = {
    "event_type": "book",
    "asset_id": "yes-token",
    "bids": [{"price": "0.44", "size": "5"}],
    "asks": [{"price": "0.48", "size": "3"}],
    "sequence": 1,
}


def write_events(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_text(json.dumps(EVENT) + "\n")
    return str(path)


def test_polymarket_daemon_ops_status_contract():
    status = polymarket_daemon_ops_status()

    assert status["daemon"] == "configured"
    assert status["risk"] == "configured"
    assert status["provider"] == "polymarket_clob_read_path"
    assert status["settlement"] == "not_configured"
    assert status["notification"] == "not_configured"
    assert status["analytics"] == "configured_off_hot_path"


@pytest.mark.asyncio
async def test_polymarket_daemon_paper_once(tmp_path):
    config = PolymarketDaemonConfig(
        mode="paper",
        once=True,
        markets=MARKETS,
        probabilities=PROBABILITIES,
        dry_run_events_jsonl=write_events(tmp_path),
        max_events=1,
        min_edge=0.01,
        paper_notional_usdc=5.0,
    )

    result = await run_polymarket_daemon_once(config)

    assert result.status == "completed"
    assert result.cycles_completed == 1
    assert result.result["execution"]["paper_intents"][0]["token_id"] == "yes-token"
    assert result.result["live_order_allowed"] is False
    assert result.result["ops_status"]["daemon"] == "configured"


@pytest.mark.asyncio
async def test_polymarket_daemon_dry_run_once(tmp_path):
    executor = DryRunPolymarketExecutor()
    config = PolymarketDaemonConfig(
        mode="dry_run",
        once=True,
        markets=MARKETS,
        probabilities=PROBABILITIES,
        dry_run_events_jsonl=write_events(tmp_path),
        max_events=1,
        min_edge=0.01,
        paper_notional_usdc=5.0,
        idempotency_jsonl=str(tmp_path / "idem.jsonl"),
        audit_jsonl=str(tmp_path / "audit.jsonl"),
        max_order_notional_usdc=10.0,
        max_total_exposure_usdc=100.0,
        max_daily_loss_usdc=50.0,
        max_spread=0.1,
    )

    result = await run_polymarket_daemon_once(config, order_executor=executor)

    assert result.status == "completed"
    assert result.result["execution"]["summary"]["submitted_count"] == 1
    assert len(executor.orders) == 1


@pytest.mark.asyncio
async def test_polymarket_daemon_live_refuses_without_postgres_primary_preflight(tmp_path):
    executor = DryRunPolymarketExecutor()
    config = PolymarketDaemonConfig(
        mode="live",
        once=True,
        markets=MARKETS,
        probabilities=PROBABILITIES,
        dry_run_events_jsonl=write_events(tmp_path),
        max_events=1,
        min_edge=0.01,
        idempotency_jsonl=str(tmp_path / "idem.jsonl"),
        audit_jsonl=str(tmp_path / "audit.jsonl"),
        max_order_notional_usdc=10.0,
        max_total_exposure_usdc=100.0,
        max_daily_loss_usdc=50.0,
        max_spread=0.1,
        positions_confirmed=True,
        postgres_primary_confirmed=False,
        operator_ack=LIVE_ACK_PHRASE,
    )

    result = await run_polymarket_daemon_once(config, order_executor=executor)

    assert result.status == "refused"
    assert "Postgres primary" in result.error
    assert executor.orders == []


@pytest.mark.asyncio
async def test_polymarket_daemon_live_refuses_postgres_primary_flag_without_repository(tmp_path, monkeypatch):
    monkeypatch.setenv("POLYMARKET_LIVE_ENABLED", "1")
    monkeypatch.setenv("POLYMARKET_LIVE_ACK", LIVE_ACK_PHRASE)
    monkeypatch.setenv("POLYMARKET_PRIVATE_KEY", "x")
    monkeypatch.setenv("POLYMARKET_FUNDER_ADDRESS", "0xabc")
    monkeypatch.setenv("POLYMARKET_CHAIN_ID", "137")
    executor = DryRunPolymarketExecutor()
    config = PolymarketDaemonConfig(
        mode="live",
        once=True,
        markets=MARKETS,
        probabilities=PROBABILITIES,
        dry_run_events_jsonl=write_events(tmp_path),
        max_events=1,
        min_edge=0.01,
        idempotency_jsonl=str(tmp_path / "idem.jsonl"),
        audit_jsonl=str(tmp_path / "audit.jsonl"),
        max_order_notional_usdc=10.0,
        max_total_exposure_usdc=100.0,
        max_daily_loss_usdc=50.0,
        max_spread=0.1,
        positions_confirmed=True,
        postgres_primary_confirmed=True,
        operator_ack=LIVE_ACK_PHRASE,
    )

    result = await run_polymarket_daemon_once(config, order_executor=executor)

    assert result.status == "refused"
    assert "configured Postgres primary durability" in result.error
    assert executor.orders == []


class FakeLiveExecutor(DryRunPolymarketExecutor):
    live_submission_available = True

    def __init__(self, open_orders=None):
        super().__init__()
        self.open_orders = open_orders or []

    def list_open_orders(self):
        return self.open_orders

    def cancel_order(self, exchange_order_id: str) -> OrderResult:
        raise AssertionError("cancel should not be called")


class FakeRepository:
    def __init__(self, orders):
        self.orders = orders
        self.completed = []
        self.runs = []
        self.claims = []
        self.status_updates = []
        self.audit_events = []

    def upsert_run(self, **kwargs):
        self.runs.append(kwargs)

    def complete_run(self, **kwargs):
        self.completed.append(kwargs)

    def list_live_submitted_orders(self):
        return self.orders

    def claim_idempotency_key(self, **kwargs):
        self.claims.append(kwargs)
        return True

    def update_idempotency_key_status(self, **kwargs):
        self.status_updates.append(kwargs)
        return True

    def append_execution_audit_event(self, **kwargs):
        self.audit_events.append(kwargs)
        return kwargs


@pytest.mark.asyncio
async def test_polymarket_daemon_live_passes_local_orders_to_preflight_and_stays_blocked_on_open_order(tmp_path, monkeypatch):
    monkeypatch.setenv("POLYMARKET_LIVE_ENABLED", "1")
    monkeypatch.setenv("POLYMARKET_LIVE_ACK", LIVE_ACK_PHRASE)
    monkeypatch.setenv("POLYMARKET_PRIVATE_KEY", "x")
    monkeypatch.setenv("POLYMARKET_FUNDER_ADDRESS", "0xabc")
    monkeypatch.setenv("POLYMARKET_CHAIN_ID", "137")
    local_order = {"exchange_order_id": "ord-1", "token_id": "yes-token", "status": "submitted"}
    executor = FakeLiveExecutor(open_orders=[{"id": "ord-1", "token_id": "yes-token", "status": "open"}])
    repository = FakeRepository([local_order])
    config = PolymarketDaemonConfig(
        mode="live",
        once=True,
        markets=MARKETS,
        probabilities=PROBABILITIES,
        dry_run_events_jsonl=write_events(tmp_path),
        max_events=1,
        min_edge=0.01,
        idempotency_jsonl=str(tmp_path / "idem.jsonl"),
        audit_jsonl=str(tmp_path / "audit.jsonl"),
        max_order_notional_usdc=10.0,
        max_total_exposure_usdc=100.0,
        max_daily_loss_usdc=50.0,
        max_spread=0.1,
        positions_confirmed=True,
        postgres_primary_confirmed=True,
        operator_ack=LIVE_ACK_PHRASE,
    )

    result = await run_polymarket_daemon_once(config, repository=repository, order_executor=executor)

    assert result.status == "refused"
    assert "clean order reconciliation" in result.error
    assert executor.orders == []
    assert repository.completed[-1]["status"] == "refused"


@pytest.mark.asyncio
async def test_polymarket_daemon_no_live_cancel(tmp_path, monkeypatch):
    monkeypatch.setenv("POLYMARKET_LIVE_ENABLED", "1")
    monkeypatch.setenv("POLYMARKET_LIVE_ACK", LIVE_ACK_PHRASE)
    monkeypatch.setenv("POLYMARKET_PRIVATE_KEY", "x")
    monkeypatch.setenv("POLYMARKET_FUNDER_ADDRESS", "0xabc")
    monkeypatch.setenv("POLYMARKET_CHAIN_ID", "137")
    monkeypatch.setenv("POLYMARKET_MAX_ORDER_NOTIONAL_USDC", "10")
    executor = FakeLiveExecutor()
    config = PolymarketDaemonConfig(
        mode="live",
        once=True,
        markets=MARKETS,
        probabilities=PROBABILITIES,
        dry_run_events_jsonl=write_events(tmp_path),
        max_events=1,
        min_edge=0.01,
        idempotency_jsonl=str(tmp_path / "idem.jsonl"),
        audit_jsonl=str(tmp_path / "audit.jsonl"),
        max_order_notional_usdc=10.0,
        max_total_exposure_usdc=100.0,
        max_daily_loss_usdc=50.0,
        max_spread=0.1,
        positions_confirmed=True,
        postgres_primary_confirmed=True,
        operator_ack=LIVE_ACK_PHRASE,
    )
    repository = FakeRepository([])

    result = await run_polymarket_daemon_once(config, repository=repository, order_executor=executor)

    assert result.status == "completed"
    assert executor.cancel_requests == []
    assert result.result["live_order_allowed"] is True
