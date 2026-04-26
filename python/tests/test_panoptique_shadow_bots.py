from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from panoptique.artifacts import read_jsonl
from panoptique.contracts import MarketSnapshot, OrderbookSnapshot, ShadowPrediction
from panoptique.repositories import PanoptiqueRepository, connect_sqlite_memory
from panoptique.shadow_bots import (
    ShadowContext,
    copy_wallet_placeholder,
    edge_8pct_bot,
    evaluate_all_bots,
    momentum_naive_bot,
    render_shadow_report,
    round_number_price_bot,
    run_shadow_evaluate_db,
    run_shadow_evaluate_fixture,
    weather_naive_threshold,
)

OBSERVED_AT = datetime(2026, 4, 26, 12, 0, tzinfo=UTC)


def market(price: float = 0.65, market_id: str = "pm-weather-1") -> MarketSnapshot:
    return MarketSnapshot(
        snapshot_id=f"market-{market_id}-20260426T120000Z",
        market_id=market_id,
        slug="nyc-rain-apr-26",
        question="Will it rain in NYC on Apr 26?",
        source="fixture",
        observed_at=OBSERVED_AT,
        yes_price=price,
        best_bid=price - 0.01,
        best_ask=price + 0.01,
        volume=1000.0,
        liquidity=500.0,
        token_ids=["yes-token", "no-token"],
    )


def orderbook(market_id: str = "pm-weather-1") -> OrderbookSnapshot:
    return OrderbookSnapshot(
        snapshot_id=f"orderbook-{market_id}-yes-token-20260426T120000Z",
        market_id=market_id,
        token_id="yes-token",
        observed_at=OBSERVED_AT,
        bids=[{"price": 0.64, "size": 100.0}],
        asks=[{"price": 0.66, "size": 90.0}],
    )


def assert_crowd_not_truth(prediction: ShadowPrediction) -> None:
    assert prediction.schema_version == "1.0"
    assert prediction.prediction_id
    assert prediction.features["prediction_target"] == "crowd_behavior_not_event_truth"
    assert "crowd behavior" in prediction.rationale
    assert "event truth" in prediction.rationale
    assert prediction.features["paper_only"] is True
    assert prediction.features["trading_action"] == "none"


def test_weather_naive_threshold_uses_fixture_weather_score_and_stable_id() -> None:
    context = ShadowContext(market_snapshot=market(0.52), orderbook_snapshot=orderbook(), weather_score=0.72)

    prediction = weather_naive_threshold().predict(context)

    assert prediction.agent_id == "weather_naive_threshold"
    assert prediction.prediction_id == "shadow-weather_naive_threshold-pm-weather-1-20260426T120000Z-v1"
    assert prediction.predicted_crowd_direction == "up"
    assert prediction.confidence == 0.72
    assert prediction.features["weather_score"] == 0.72
    assert prediction.features["thresholds"] == {"low": 0.4, "high": 0.6}
    assert_crowd_not_truth(prediction)


def test_weather_naive_threshold_insufficient_data_without_score() -> None:
    prediction = weather_naive_threshold().predict(ShadowContext(market_snapshot=market(), orderbook_snapshot=orderbook()))

    assert prediction.predicted_crowd_direction == "insufficient_data"
    assert prediction.confidence == 0.0
    assert "missing weather_score" in prediction.rationale
    assert_crowd_not_truth(prediction)


def test_round_number_price_bot_detects_explicit_magic_levels() -> None:
    prediction = round_number_price_bot().predict(ShadowContext(market_snapshot=market(0.649), orderbook_snapshot=orderbook()))

    assert prediction.agent_id == "round_number_price_bot"
    assert prediction.predicted_crowd_direction == "up"
    assert prediction.features["matched_level"] == 0.65
    assert prediction.features["magic_levels"] == [0.5, 0.6, 0.65, 0.7, 0.75, 0.8]
    assert prediction.features["price"] == 0.649
    assert_crowd_not_truth(prediction)


def test_edge_8pct_bot_uses_configurable_edge_threshold_default() -> None:
    context = ShadowContext(market_snapshot=market(0.62), orderbook_snapshot=orderbook(), weather_score=0.71)

    prediction = edge_8pct_bot().predict(context)

    assert prediction.agent_id == "edge_8pct_bot"
    assert prediction.predicted_crowd_direction == "up"
    assert prediction.features["edge"] == 0.09
    assert prediction.features["edge_threshold"] == 0.08
    assert prediction.confidence == 0.59
    assert_crowd_not_truth(prediction)


def test_edge_bot_can_emit_down_for_negative_edge() -> None:
    context = ShadowContext(market_snapshot=market(0.72), orderbook_snapshot=orderbook(), weather_score=0.6)

    prediction = edge_8pct_bot(edge_threshold=0.10).predict(context)

    assert prediction.predicted_crowd_direction == "down"
    assert prediction.features["edge"] == -0.12
    assert prediction.features["edge_threshold"] == 0.1
    assert_crowd_not_truth(prediction)


def test_momentum_naive_bot_follows_recent_price_delta() -> None:
    context = ShadowContext(market_snapshot=market(0.56), orderbook_snapshot=orderbook(), recent_prices=[0.50, 0.52, 0.56])

    prediction = momentum_naive_bot().predict(context)

    assert prediction.agent_id == "momentum_naive_bot"
    assert prediction.predicted_crowd_direction == "up"
    assert prediction.features["price_delta"] == 0.06
    assert prediction.features["recent_prices"] == [0.5, 0.52, 0.56]
    assert_crowd_not_truth(prediction)


def test_copy_wallet_placeholder_is_non_trading_insufficient_data() -> None:
    prediction = copy_wallet_placeholder().predict(ShadowContext(market_snapshot=market(), orderbook_snapshot=orderbook()))

    assert prediction.agent_id == "copy_wallet_placeholder"
    assert prediction.predicted_crowd_direction == "insufficient_data"
    assert prediction.confidence == 0.0
    assert prediction.features["wallet_signal_available"] is False
    assert prediction.features["trading_action"] == "none"
    assert_crowd_not_truth(prediction)


def test_evaluate_all_bots_produces_one_prediction_per_archetype() -> None:
    context = ShadowContext(
        market_snapshot=market(0.65),
        orderbook_snapshot=orderbook(),
        weather_score=0.75,
        recent_prices=[0.61, 0.63, 0.65],
    )

    predictions = evaluate_all_bots(context)

    assert [p.agent_id for p in predictions] == [
        "weather_naive_threshold",
        "round_number_price_bot",
        "edge_8pct_bot",
        "momentum_naive_bot",
        "copy_wallet_placeholder",
    ]
    assert all(p.prediction_id.startswith(f"shadow-{p.agent_id}-pm-weather-1-20260426T120000Z-v1") for p in predictions)
    assert all(p.features["prediction_target"] == "crowd_behavior_not_event_truth" for p in predictions)


def test_fixture_command_reads_json_writes_jsonl_report_and_sqlite_repository(tmp_path: Path) -> None:
    fixture_path = tmp_path / "shadow_fixture.json"
    output_dir = tmp_path / "out"
    sqlite_path = tmp_path / "panoptique.sqlite"
    fixture_path.write_text(
        json.dumps(
            {
                "market_snapshot": market(0.65).to_record(),
                "orderbook_snapshot": orderbook().to_record(),
                "weather_score": 0.75,
                "recent_prices": [0.61, 0.63, 0.65],
            }
        ),
        encoding="utf-8",
    )

    result = run_shadow_evaluate_fixture(fixture_path=fixture_path, output_dir=output_dir, sqlite_db=sqlite_path)

    assert result.command == "shadow-evaluate-fixture"
    assert result.status == "ok"
    assert result.db_status == "inserted"
    assert result.count == 5
    rows = list(read_jsonl(result.artifact_path))
    assert len(rows) == 5
    assert rows[0]["metadata"]["db_status"] == "inserted"
    assert rows[0]["prediction"]["features"]["prediction_target"] == "crowd_behavior_not_event_truth"
    assert "No real orders" in result.report_path.read_text(encoding="utf-8")

    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    repo = PanoptiqueRepository(conn)
    assert len(repo.list_shadow_predictions("pm-weather-1")) == 5


def test_fixture_command_without_db_records_explicit_skipped_status(tmp_path: Path) -> None:
    fixture_path = tmp_path / "shadow_fixture.json"
    fixture_path.write_text(json.dumps({"market_snapshot": market().to_record(), "weather_score": 0.7}), encoding="utf-8")

    result = run_shadow_evaluate_fixture(fixture_path=fixture_path, output_dir=tmp_path / "out")

    assert result.db_status == "skipped_unavailable"
    row = next(read_jsonl(result.artifact_path))
    assert row["metadata"]["db_status"] == "skipped_unavailable"


def test_db_command_reads_recent_sqlite_snapshots_and_persists_predictions(tmp_path: Path) -> None:
    conn = connect_sqlite_memory()
    repo = PanoptiqueRepository(conn)
    repo.create_schema()
    repo.insert_market_snapshot(market(0.65))
    repo.insert_orderbook_snapshot(orderbook())

    result = run_shadow_evaluate_db(repository=repo, output_dir=tmp_path, weather_scores={"pm-weather-1": 0.76}, recent_prices={"pm-weather-1": [0.6, 0.62, 0.65]})

    assert result.command == "shadow-evaluate-db"
    assert result.status == "ok"
    assert result.db_status == "inserted"
    assert result.count == 5
    assert len(repo.list_shadow_predictions("pm-weather-1")) == 5
    assert len(list(read_jsonl(result.artifact_path))) == 5


def test_db_command_without_repository_is_testable_unavailable_status(tmp_path: Path) -> None:
    result = run_shadow_evaluate_db(repository=None, output_dir=tmp_path)

    assert result.command == "shadow-evaluate-db"
    assert result.status == "skipped"
    assert result.db_status == "skipped_unavailable"
    assert result.count == 0
    row = next(read_jsonl(result.artifact_path))
    assert row["metadata"]["db_status"] == "skipped_unavailable"
    assert row["prediction"] is None


def test_render_shadow_report_is_operator_facing_and_paper_only() -> None:
    report = render_shadow_report(
        command="shadow-evaluate-fixture",
        source="fixture",
        evaluated_at=OBSERVED_AT,
        status="ok",
        count=5,
        artifact_path=Path("/tmp/shadow.jsonl"),
        db_status="skipped_unavailable",
        errors=[],
    )

    assert "# Panoptique Shadow Bot Evaluation" in report
    assert "crowd behavior, not event truth" in report
    assert "No real orders" in report
    assert "skipped_unavailable" in report
