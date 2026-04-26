from __future__ import annotations

from datetime import UTC, datetime

from panoptique.contracts import CrowdFlowObservation, Market, OrderbookSnapshot, ShadowPrediction
from panoptique.repositories import PanoptiqueRepository, connect_sqlite_memory


def test_repository_insert_and_read_paths_for_phase1_contracts() -> None:
    conn = connect_sqlite_memory()
    repo = PanoptiqueRepository(conn)
    repo.create_schema()
    observed_at = datetime(2026, 4, 26, 12, 0, tzinfo=UTC)

    market = Market(
        market_id="pm-1",
        slug="weather-nyc",
        question="Will it rain in NYC?",
        source="polymarket",
        raw={"gamma_id": "1"},
    )
    orderbook = OrderbookSnapshot(
        snapshot_id="ob-1",
        market_id="pm-1",
        token_id="tok-yes",
        observed_at=observed_at,
        bids=[{"price": 0.49, "size": 100.0}],
        asks=[{"price": 0.51, "size": 100.0}],
        raw={"book": True},
    )
    prediction = ShadowPrediction(
        prediction_id="sp-1",
        market_id="pm-1",
        agent_id="round_number_price_bot",
        observed_at=observed_at,
        horizon_seconds=900,
        predicted_crowd_direction="up",
        confidence=0.72,
        rationale="paper-only crowd-flow forecast; no real order placed",
        features={"mid": 0.5},
    )
    flow = CrowdFlowObservation(
        observation_id="cf-1",
        prediction_id="sp-1",
        market_id="pm-1",
        observed_at=observed_at,
        window_seconds=900,
        price_delta=0.02,
        volume_delta=45.0,
        direction_hit=True,
        liquidity_caveat=None,
        metrics={"after_mid": 0.52},
    )

    repo.upsert_market(market)
    repo.insert_orderbook_snapshot(orderbook)
    repo.insert_shadow_prediction(prediction)
    repo.insert_crowd_flow_observation(flow)

    assert repo.get_market("pm-1")["slug"] == "weather-nyc"
    assert repo.list_orderbook_snapshots("pm-1")[0]["bids"][0]["price"] == 0.49
    assert repo.list_shadow_predictions("pm-1")[0]["predicted_crowd_direction"] == "up"
    assert repo.list_crowd_flow_observations("pm-1")[0]["direction_hit"] is True
