import json

from prediction_core.storage.postgres import OperationalStateRepository


class FakeResult:
    rowcount = 1


class FakeConnection:
    def __init__(self):
        self.calls = []

    def execute(self, sql, params):
        self.calls.append((str(sql), params))
        return FakeResult()


class FakeBegin:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self.connection

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeEngine:
    def __init__(self):
        self.connection = FakeConnection()

    def begin(self):
        return FakeBegin(self.connection)


def test_claim_idempotency_key_uses_insert_conflict_do_nothing():
    engine = FakeEngine()
    repo = OperationalStateRepository(engine)

    assert repo.claim_idempotency_key(key="k1", mode="paper", metadata={"run_id": "r1"}) is True

    sql, params = engine.connection.calls[0]
    assert "ON CONFLICT (key) DO NOTHING" in sql
    assert params["key"] == "k1"
    assert params["paper_only"] is True


def test_append_execution_audit_event_keeps_live_disabled():
    engine = FakeEngine()
    repo = OperationalStateRepository(engine)

    row = repo.append_execution_audit_event(event_type="accepted", payload={"run_id": "r1"})

    assert row["paper_only"] is True
    assert row["live_order_allowed"] is False


def test_jsonb_params_are_serialized_and_cast_for_driver_compatibility():
    engine = FakeEngine()
    repo = OperationalStateRepository(engine)

    repo.upsert_run(run_id="run-1", mode="paper", status="started", config={"b": 2}, summary={"a": 1}, artifact_ids=["art-1"])

    sql, params = engine.connection.calls[0]
    assert "CAST(:config AS jsonb)" in sql
    assert "CAST(:summary AS jsonb)" in sql
    assert "CAST(:artifact_ids AS jsonb)" in sql
    assert params["config"] == json.dumps({"b": 2}, sort_keys=True, separators=(",", ":"))
    assert params["summary"] == json.dumps({"a": 1}, sort_keys=True, separators=(",", ":"))
    assert params["artifact_ids"] == json.dumps(["art-1"], sort_keys=True, separators=(",", ":"))


def test_audit_event_payload_is_serialized_and_cast():
    engine = FakeEngine()
    repo = OperationalStateRepository(engine)

    repo.append_execution_audit_event(event_type="accepted", payload={"run_id": "r1"})

    sql, params = engine.connection.calls[0]
    assert "CAST(:payload AS jsonb)" in sql
    assert params["payload"] == json.dumps({"run_id": "r1"}, sort_keys=True, separators=(",", ":"))
