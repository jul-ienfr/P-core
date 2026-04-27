import json

from prediction_core.polymarket_execution import JsonlIdempotencyStore


def test_idempotency_store_claims_key_once(tmp_path):
    store = JsonlIdempotencyStore(tmp_path / "ids.jsonl")

    assert store.claim("k1", metadata={"market_id": "m1"}) is True
    assert store.claim("k1", metadata={"market_id": "m1"}) is False
    assert store.seen("k1") is True


def test_idempotency_store_survives_reopen(tmp_path):
    path = tmp_path / "ids.jsonl"
    assert JsonlIdempotencyStore(path).claim("k1") is True
    assert JsonlIdempotencyStore(path).claim("k1") is False


def test_idempotency_store_tracks_pending_then_submitted(tmp_path):
    path = tmp_path / "ids.jsonl"
    store = JsonlIdempotencyStore(path)

    assert store.claim("k1", metadata={"market_id": "m1"}, status="pending") is True
    assert store.mark_submitted("k1", metadata={"status": "dry_run_accepted"}) is True
    assert store.claim("k1") is False
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert [row["status"] for row in rows] == ["pending", "submitted"]


def test_idempotency_store_tracks_pending_then_rejected(tmp_path):
    path = tmp_path / "ids.jsonl"
    store = JsonlIdempotencyStore(path)

    assert store.claim("k1", metadata={"market_id": "m1"}, status="pending") is True
    assert store.mark_rejected("k1", metadata={"status": "rejected_by_exchange"}) is True
    assert store.claim("k1") is False
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert [row["status"] for row in rows] == ["pending", "rejected"]


def test_idempotency_store_rejects_empty_key(tmp_path):
    store = JsonlIdempotencyStore(tmp_path / "ids.jsonl")

    try:
        store.claim(" ")
    except ValueError as exc:
        assert "key is required" in str(exc)
    else:
        raise AssertionError("empty key should fail closed")
