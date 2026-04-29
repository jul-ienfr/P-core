import json
from datetime import UTC, datetime

import pytest

from panoptique.live_observer_storage import LiveObserverStorageResult
from weather_pm.live_observer_snapshots import (
    CompactMarketSnapshot,
    ForecastSourceSnapshot,
    FollowedAccountTradeTrigger,
    WeatherBinSurfaceSnapshot,
    assert_paper_only_storage_result,
)


OBSERVED_AT = datetime(2026, 4, 28, 12, 30, 45, tzinfo=UTC)


def test_compact_market_snapshot_serializes_datetime_and_core_fields():
    snapshot = CompactMarketSnapshot(
        observed_at=OBSERVED_AT,
        market_id="pm-nyc-high-2026-04-28",
        event_id="event-1",
        slug="nyc-high-temp",
        question="NYC high temp?",
        city="New York",
        metric="high_temp_f",
        target_date="2026-04-28",
        best_bid=0.42,
        best_ask=0.45,
        last_trade_price=0.44,
        volume=1234.5,
        liquidity=678.9,
        open_interest=11.0,
        active=True,
        closed=False,
        paper_only=True,
    )

    payload = snapshot.to_dict()

    assert payload["snapshot_type"] == "compact_market_snapshot"
    assert payload["observed_at"] == "2026-04-28T12:30:45+00:00"
    assert payload["market_id"] == "pm-nyc-high-2026-04-28"
    assert payload["paper_only"] is True
    json.dumps(payload)


def test_weather_bin_surface_snapshot_serializes_bins_as_json_compatible_values():
    snapshot = WeatherBinSurfaceSnapshot(
        observed_at=OBSERVED_AT,
        market_id="event-1",
        event_id="event-1",
        city="Austin",
        metric="rain_inches",
        target_date="2026-04-28",
        bins=[
            {"label": "0-1", "probability": 0.25, "best_bid": 0.24, "best_ask": 0.27},
            {"label": "1-2", "probability": 0.75, "best_bid": 0.73, "best_ask": 0.78},
        ],
        source_market_ids=["m1", "m2"],
    )

    payload = snapshot.to_dict()

    assert payload["snapshot_type"] == "weather_bin_surface_snapshot"
    assert payload["bins"][0]["label"] == "0-1"
    assert payload["source_market_ids"] == ["m1", "m2"]
    assert payload["paper_only"] is True
    json.dumps(payload)


def test_forecast_source_snapshot_serializes_source_payload_without_mutating_datetime():
    issued_at = datetime(2026, 4, 28, 11, 0, tzinfo=UTC)
    snapshot = ForecastSourceSnapshot(
        observed_at=OBSERVED_AT,
        source="noaa",
        source_uri="https://example.invalid/forecast",
        city="Miami",
        metric="high_temp_f",
        target_date="2026-04-29",
        forecast_value=86.2,
        forecast_units="F",
        issued_at=issued_at,
        raw_payload={"model_run": issued_at, "confidence": 0.8},
    )

    payload = snapshot.to_dict()

    assert payload["snapshot_type"] == "forecast_source_snapshot"
    assert payload["issued_at"] == "2026-04-28T11:00:00+00:00"
    assert payload["raw_payload"]["model_run"] == "2026-04-28T11:00:00+00:00"
    assert payload["paper_only"] is True
    json.dumps(payload)


def test_followed_account_trade_trigger_is_a_paper_only_capture_trigger_not_live_order():
    trigger = FollowedAccountTradeTrigger(
        observed_at=OBSERVED_AT,
        account="ColdMath",
        profile_id="shadow_coldmath_v0",
        transaction_hash="0xabc",
        market_id="m1",
        side="BUY",
        price=0.51,
        size=42.0,
        paper_decision="capture_rich_snapshot",
    )

    payload = trigger.to_dict()

    assert payload["snapshot_type"] == "followed_account_trade_trigger"
    assert payload["paper_only"] is True
    assert payload["live_order_allowed"] is False
    assert payload["paper_decision"] == "capture_rich_snapshot"
    json.dumps(payload)


def test_snapshot_contracts_reject_live_order_semantics():
    with pytest.raises(ValueError, match="paper_only"):
        CompactMarketSnapshot(
            observed_at=OBSERVED_AT,
            market_id="m1",
            event_id="e1",
            slug="slug",
            question="question",
            city="Paris",
            metric="high_temp_f",
            target_date="2026-04-28",
            paper_only=False,
        )

    with pytest.raises(ValueError, match="live_order_allowed"):
        FollowedAccountTradeTrigger(
            observed_at=OBSERVED_AT,
            account="acct",
            profile_id="profile",
            transaction_hash="0xabc",
            market_id="m1",
            side="BUY",
            price=0.4,
            size=1.0,
            live_order_allowed=True,
        )


def test_storage_result_enforcement_requires_paper_only_no_live_orders():
    assert_paper_only_storage_result(
        LiveObserverStorageResult(
            backend="local_jsonl",
            status="written",
            path_or_uri="/tmp/snapshots.jsonl",
            row_count=1,
            paper_only=True,
        )
    )

    with pytest.raises(ValueError, match="paper_only"):
        assert_paper_only_storage_result(
            {"backend": "local_jsonl", "status": "written", "row_count": 1, "paper_only": False}
        )
