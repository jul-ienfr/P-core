from __future__ import annotations

from datetime import UTC, datetime
import json

from panoptique.contracts import (
    ArtifactMetadata,
    CrowdFlowObservation,
    IngestionHealth,
    Market,
    OrderbookSnapshot,
    ShadowPrediction,
    TradeEvent,
)


def test_contracts_serialize_to_json_safe_dicts() -> None:
    observed_at = datetime(2026, 4, 26, 12, 0, tzinfo=UTC)
    contracts = [
        Market(
            market_id="pm-1",
            slug="weather-nyc",
            question="Will it rain in NYC?",
            source="polymarket",
            active=True,
            closed=False,
            raw={"gamma_id": "1"},
        ),
        OrderbookSnapshot(
            snapshot_id="ob-1",
            market_id="pm-1",
            token_id="tok-yes",
            observed_at=observed_at,
            bids=[{"price": 0.49, "size": 100.0}],
            asks=[{"price": 0.51, "size": 120.0}],
            raw={"book": True},
        ),
        TradeEvent(
            trade_id="tr-1",
            market_id="pm-1",
            token_id="tok-yes",
            observed_at=observed_at,
            price=0.5,
            size=10.0,
            side="buy",
            raw={},
        ),
        ShadowPrediction(
            prediction_id="sp-1",
            market_id="pm-1",
            agent_id="round_number_price_bot",
            observed_at=observed_at,
            horizon_seconds=900,
            predicted_crowd_direction="up",
            confidence=0.67,
            rationale="crowd behavior only; no real order placed",
            features={"mid": 0.5},
        ),
        CrowdFlowObservation(
            observation_id="cf-1",
            prediction_id="sp-1",
            market_id="pm-1",
            observed_at=observed_at,
            window_seconds=900,
            price_delta=0.03,
            volume_delta=100.0,
            direction_hit=True,
            liquidity_caveat=None,
            metrics={"after_mid": 0.53},
        ),
        IngestionHealth(
            health_id="ih-1",
            source="gamma",
            checked_at=observed_at,
            status="ok",
            detail="sample",
            metrics={"rows": 1},
        ),
        ArtifactMetadata(
            artifact_id="art-1",
            artifact_type="jsonl",
            path="data/panoptique/snapshots/sample.jsonl",
            created_at=observed_at,
            schema_version="1.0",
            source="test",
            row_count=1,
            sha256="abc",
        ),
    ]

    for contract in contracts:
        payload = contract.to_dict()
        encoded = contract.to_json()
        assert json.loads(encoded) == payload
        assert payload["schema_version"] == "1.0"


def test_market_maps_to_db_row_without_raw_mutation() -> None:
    market = Market(
        market_id="pm-1",
        slug="weather-nyc",
        question="Will it rain in NYC?",
        source="polymarket",
        raw={"nested": {"ok": True}},
    )

    row = market.to_record()

    assert row["market_id"] == "pm-1"
    assert row["raw"] == {"nested": {"ok": True}}
    row["raw"]["nested"]["ok"] = False
    assert market.raw["nested"]["ok"] is True
