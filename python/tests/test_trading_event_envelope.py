import math

import pytest

from prediction_core.storage.events import (
    build_trading_event_envelope,
    validate_trading_event_envelope,
)


BASE_KWARGS = {
    "stream_id": "orders:btc-usd",
    "event_seq": 1,
    "event_type": "signal_recorded",
    "source": "prediction_core.trading",
    "market_id": "BTC-USD",
    "occurred_at": "2026-04-27T00:00:00+00:00",
    "recorded_at": "2026-04-27T00:00:01+00:00",
    "payload": {"side": "buy", "price": 100},
}


def test_same_inputs_produce_identical_event_id_and_payload_hash():
    first = build_trading_event_envelope(**BASE_KWARGS)
    second = build_trading_event_envelope(**BASE_KWARGS)

    assert first["event_id"] == second["event_id"]
    assert first["payload_hash"] == second["payload_hash"]


def test_changing_payload_changes_payload_hash_and_event_id():
    first = build_trading_event_envelope(**BASE_KWARGS)
    second = build_trading_event_envelope(
        **{**BASE_KWARGS, "payload": {"side": "buy", "price": 101}}
    )

    assert first["payload_hash"] != second["payload_hash"]
    assert first["event_id"] != second["event_id"]


def test_previous_hash_is_preserved():
    envelope = build_trading_event_envelope(**BASE_KWARGS, previous_hash="abc123")

    assert envelope["previous_hash"] == "abc123"


def test_rejects_live_order_allowed_true():
    with pytest.raises(ValueError, match="must not enable live orders"):
        build_trading_event_envelope(**BASE_KWARGS, live_order_allowed=True)


def test_rejects_missing_payload():
    envelope = build_trading_event_envelope(**BASE_KWARGS)
    del envelope["payload"]

    with pytest.raises(ValueError, match="missing required fields: payload"):
        validate_trading_event_envelope(envelope)


def test_rejects_non_dict_payload():
    with pytest.raises(ValueError, match="payload must be an object"):
        build_trading_event_envelope(**{**BASE_KWARGS, "payload": "not-an-object"})


def test_rejects_nan_payload_values():
    with pytest.raises(ValueError):
        build_trading_event_envelope(**{**BASE_KWARGS, "payload": {"price": math.nan}})
