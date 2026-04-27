import json

from prediction_core.polymarket_execution import JsonlExecutionAuditLog


def test_audit_log_appends_decision_order_and_result(tmp_path):
    path = tmp_path / "audit.jsonl"
    log = JsonlExecutionAuditLog(path)

    first = log.append("decision", {"market_id": "m1", "action": "PAPER_SIGNAL_ONLY"})
    second = log.append("order_submitted", {"idempotency_key": "k1", "status": "dry_run_accepted"})

    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert [row["event_type"] for row in rows] == ["decision", "order_submitted"]
    assert rows[0]["payload"]["market_id"] == "m1"
    assert "recorded_at" in rows[0]
    assert first == rows[0]
    assert second == rows[1]


def test_audit_log_rejects_empty_event_type(tmp_path):
    log = JsonlExecutionAuditLog(tmp_path / "audit.jsonl")

    try:
        log.append(" ", {})
    except ValueError as exc:
        assert "event_type is required" in str(exc)
    else:
        raise AssertionError("empty event_type should fail closed")
