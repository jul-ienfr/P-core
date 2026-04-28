import json

from prediction_core.storage.postgres import OperationalStateRepository


class FakeMappings:
    def __init__(self, rows=None):
        self.rows = rows or []

    def all(self):
        return self.rows


class FakeResult:
    rowcount = 1

    def __init__(self, rows=None):
        self.rows = rows or []

    def mappings(self):
        return FakeMappings(self.rows)


class FakeConnection:
    def __init__(self, rows=None):
        self.calls = []
        self.rows = rows or []

    def execute(self, sql, params):
        self.calls.append((str(sql), params))
        return FakeResult(self.rows)


class FakeBegin:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self.connection

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeEngine:
    def __init__(self, rows=None):
        self.connection = FakeConnection(rows)

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


def test_list_live_submitted_orders_reads_exchange_order_id_from_metadata():
    engine = FakeEngine(
        rows=[
            {
                "key": "idem-1",
                "run_id": "run-1",
                "market_id": "market-1",
                "token_id": "token-1",
                "metadata": {"status": "submitted", "exchange_order_id": "ord-1"},
            }
        ]
    )
    repo = OperationalStateRepository(engine)

    orders = repo.list_live_submitted_orders()

    sql, params = engine.connection.calls[0]
    assert "mode = 'live'" in sql
    assert params == {}
    assert orders == [
        {
            "idempotency_key": "idem-1",
            "exchange_order_id": "ord-1",
            "market_id": "market-1",
            "token_id": "token-1",
            "status": "submitted",
        }
    ]


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


def test_operational_summaries_keep_postgres_primary_and_transports_ephemeral():
    repo = OperationalStateRepository(FakeEngine())

    assert repo.job_observability_summary()["source_of_truth"] == "postgres"
    assert repo.audit_observability_summary()["tables"]["execution_audit_events"] == "primary"
    assert repo.postgres_primary_migration_plan()["not_source_of_truth"] == ["redis", "nats"]
    assert repo.postgres_primary_migration_plan()["guards"] == {
        "paper_only": True,
        "live_order_allowed": False,
        "jsonb_driver_casts": True,
    }


def test_repository_builds_job_and_audit_events_with_storage_schema():
    repo = OperationalStateRepository(FakeEngine())

    job_event = repo.build_job_event(event_type="job_requested", job_id="job-1", payload={"kind": "paper"})
    audit_event = repo.build_audit_event(event_type="audit_recorded", payload={"run_id": "r1"})

    assert job_event["source"] == "prediction_core.storage.jobs"
    assert job_event["data"] == {"job_id": "job-1", "kind": "paper"}
    assert job_event["paper_only"] is True
    assert job_event["live_order_allowed"] is False
    assert audit_event["source"] == "prediction_core.storage.audit"
    assert audit_event["data"] == {"run_id": "r1"}
