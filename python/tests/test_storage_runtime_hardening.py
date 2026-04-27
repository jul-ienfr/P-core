from __future__ import annotations

import pytest

from prediction_core.polymarket_execution import CompositeExecutionAuditLog, CompositeIdempotencyStore, JsonlExecutionAuditLog, JsonlIdempotencyStore, PostgresIdempotencyStore
from prediction_core.polymarket_runtime import plan_disabled_execution_actions
from prediction_core.storage.config import mask_url, redact_mapping
from prediction_core.storage.health import storage_health_summary


class FailingIdempotencyStore:
    def seen(self, key: str) -> bool:
        return False

    def claim(self, key: str, metadata: dict | None = None, status: str = "pending") -> bool:
        raise RuntimeError("secondary failed")

    def mark_submitted(self, key: str, metadata: dict | None = None) -> bool:
        raise RuntimeError("secondary failed")

    def mark_rejected(self, key: str, metadata: dict | None = None) -> bool:
        raise RuntimeError("secondary failed")


class FailingAuditLog:
    def append(self, event_type: str, payload: dict) -> dict:
        raise RuntimeError("secondary failed")


class Repository:
    def __init__(self) -> None:
        self.updates = []

    def claim_idempotency_key(self, **kwargs):
        return True

    def update_idempotency_key_status(self, **kwargs):
        self.updates.append(kwargs)
        return True


def test_redaction_covers_runtime_secrets_and_url_query() -> None:
    assert mask_url("postgres://user:pass@example/db?api_key=abc&x=1") == "postgres://user:***@example/db?api_key=%2A%2A%2A&x=1"
    redacted = redact_mapping({"POLYMARKET_PRIVATE_KEY": "secret", "nested": {"auth_token": "tok"}})
    assert redacted["POLYMARKET_PRIVATE_KEY"] == "***"
    assert redacted["nested"]["auth_token"] == "***"


def test_storage_health_summary_degrades_live_for_broken_configured_services() -> None:
    summary = storage_health_summary(
        {
            "postgres": {"configured": True, "ok": True},
            "redis": {"configured": True, "ok": False},
            "nats": {"configured": False, "ok": False},
            "s3": {"configured": True, "ok": False},
        }
    )
    assert summary["ready_for_paper"] is True
    assert summary["ready_for_live"] is False
    assert summary["degraded"] is True
    assert summary["degraded_services"] == ["redis", "s3"]


def test_runtime_result_mode_and_guard_flags() -> None:
    result = plan_disabled_execution_actions([], execution_mode="paper")
    assert result["mode"] == "paper polymarket execution planner"
    assert result["paper_only"] is True
    assert result["live_order_allowed"] is False


def test_composite_secondary_writes_default_non_strict(tmp_path) -> None:
    store = CompositeIdempotencyStore(JsonlIdempotencyStore(tmp_path / "ids.jsonl"), FailingIdempotencyStore())
    assert store.claim("k") is True
    audit = CompositeExecutionAuditLog(JsonlExecutionAuditLog(tmp_path / "audit.jsonl"), FailingAuditLog())
    assert audit.append("event", {})["event_type"] == "event"


def test_composite_secondary_writes_strict_raises(tmp_path) -> None:
    store = CompositeIdempotencyStore(JsonlIdempotencyStore(tmp_path / "ids.jsonl"), FailingIdempotencyStore(), strict_secondary_writes=True)
    with pytest.raises(RuntimeError):
        store.claim("k")
    audit = CompositeExecutionAuditLog(JsonlExecutionAuditLog(tmp_path / "audit.jsonl"), FailingAuditLog(), strict_secondary_writes=True)
    with pytest.raises(RuntimeError):
        audit.append("event", {})


def test_postgres_idempotency_store_terminal_updates() -> None:
    repository = Repository()
    store = PostgresIdempotencyStore(repository)
    assert store.mark_submitted("k", {"market_id": "m"}) is True
    assert store.mark_rejected("k", {"market_id": "m"}) is True
    assert repository.updates == [
        {"key": "k", "status": "submitted", "metadata": {"market_id": "m"}},
        {"key": "k", "status": "rejected", "metadata": {"market_id": "m"}},
    ]
