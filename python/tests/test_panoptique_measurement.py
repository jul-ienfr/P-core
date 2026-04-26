from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from panoptique.contracts import CrowdFlowObservation, MarketSnapshot, ShadowPrediction
from panoptique.measurement import (
    MeasurementRunResult,
    aggregate_measurements,
    confidence_bucket,
    match_predictions_to_snapshots,
    run_measure_shadow_flow_archive,
    run_measure_shadow_flow_db,
)
from panoptique.repositories import PanoptiqueRepository, connect_sqlite_memory
from panoptique.reports import render_measurement_report
from panoptique.artifacts import JsonlArtifactWriter, read_jsonl


BASE = datetime(2026, 4, 26, 12, 0, tzinfo=UTC)


def pred(pid: str, agent: str, direction: str, confidence: float, market: str = "m1", category: str = "weather") -> ShadowPrediction:
    return ShadowPrediction(
        prediction_id=pid,
        market_id=market,
        agent_id=agent,
        observed_at=BASE,
        horizon_seconds=900,
        predicted_crowd_direction=direction,
        confidence=confidence,
        rationale="paper-only crowd behavior prediction; no real order placed",
        features={"category": category, "prediction_target": "crowd_behavior_not_event_truth"},
    )


def snap(market: str, minutes: int, price: float, volume: float, liquidity: float = 500.0) -> MarketSnapshot:
    at = BASE + timedelta(minutes=minutes)
    return MarketSnapshot(
        snapshot_id=f"snap-{market}-{minutes}",
        market_id=market,
        slug=f"{market}-slug",
        question="fixture?",
        source="fixture",
        observed_at=at,
        yes_price=price,
        volume=volume,
        liquidity=liquidity,
    )


def obs(pid: str, market: str, agent: str, hit: bool, delta: float, volume_delta: float, confidence: float, window: int = 900, caveat: str | None = None) -> CrowdFlowObservation:
    return CrowdFlowObservation(
        observation_id=f"obs-{pid}",
        prediction_id=pid,
        market_id=market,
        observed_at=BASE + timedelta(seconds=window),
        window_seconds=window,
        price_delta=delta,
        volume_delta=volume_delta,
        direction_hit=hit,
        liquidity_caveat=caveat,
        metrics={"agent_id": agent, "confidence": confidence, "confidence_bucket": confidence_bucket(confidence), "category": "weather"},
    )


def test_aggregate_metrics_edge_cases_and_safety_labels() -> None:
    observations = [
        obs("p1", "m1", "bot_a", True, 0.03, 20.0, 0.82),
        obs("p2", "m2", "bot_a", False, -0.01, 10.0, 0.64, caveat="insufficient_liquidity"),
        obs("p3", "m3", "bot_b", True, 0.02, 50.0, 0.41),
    ]

    summary = aggregate_measurements(observations, total_predictions=120)

    assert summary.total_predictions == 120
    assert summary.matched_observations == 3
    assert summary.hit_rate_by_agent["bot_a"] == 0.5
    assert summary.hit_rate_by_agent["bot_b"] == 1.0
    assert summary.mean_price_delta_by_confidence_bucket["high"] == 0.03
    assert summary.volume_response_by_window[900] == 80.0 / 3.0
    assert summary.false_positive_rate == 1 / 3
    assert summary.insufficient_liquidity_count == 1
    assert summary.measurement_separation["event_accuracy"] == "not_measured"
    assert summary.measurement_separation["crowd_flow_prediction_accuracy"] == "measured"
    assert summary.measurement_separation["execution_feasibility"] == "liquidity_caveat_only"


def test_match_predictions_to_synthetic_snapshots_by_after_window() -> None:
    predictions = [pred("p1", "bot_a", "up", 0.8)]
    snapshots = [snap("m1", 0, 0.50, 100.0), snap("m1", 4, 0.51, 110.0), snap("m1", 5, 0.54, 140.0)]

    observations = match_predictions_to_snapshots(predictions, snapshots, window_seconds=300)

    assert len(observations) == 1
    assert observations[0].prediction_id == "p1"
    assert observations[0].price_delta == 0.04
    assert observations[0].direction_hit is True


def test_archive_replay_writes_observation_summary_and_report_without_profit_claims(tmp_path: Path) -> None:
    predictions_path = tmp_path / "predictions.jsonl"
    snapshots_dir = tmp_path / "snapshots"
    snapshots_dir.mkdir()
    JsonlArtifactWriter(predictions_path, source="test").write_many([{"prediction": pred("p1", "bot_a", "up", 0.8).to_record()}])
    JsonlArtifactWriter(snapshots_dir / "snaps.jsonl", source="test").write_many([
        {"snapshot": snap("m1", 0, 0.50, 100.0).to_record()},
        {"snapshot": snap("m1", 15, 0.55, 150.0).to_record()},
    ])

    result = run_measure_shadow_flow_archive(predictions_jsonl=predictions_path, snapshots_dir=snapshots_dir, output_dir=tmp_path / "out", window="15m")

    assert isinstance(result, MeasurementRunResult)
    assert result.status == "ok"
    assert result.count == 1
    assert result.db_status == "skipped_unavailable"
    rows = list(read_jsonl(result.artifact_path))
    assert rows[0]["observation"]["direction_hit"] is True
    report = result.report_path.read_text(encoding="utf-8").lower()
    assert "no real orders were placed" in report
    assert "profit" not in report


def test_db_measurement_degrades_when_repository_unavailable(tmp_path: Path) -> None:
    result = run_measure_shadow_flow_db(repository=None, output_dir=tmp_path, window="5m")

    assert result.status == "skipped"
    assert result.db_status == "skipped_unavailable"
    assert result.gate_decision.status == "not_enough_data"
    assert result.artifact_path.exists()
    assert "skipped_unavailable" in result.report_path.read_text(encoding="utf-8")


def test_db_measurement_persists_observations_and_agent_measurements(tmp_path: Path) -> None:
    conn = connect_sqlite_memory()
    repo = PanoptiqueRepository(conn)
    repo.create_schema()
    repo.insert_shadow_prediction(pred("p1", "bot_a", "up", 0.8))
    repo.insert_market_snapshot(snap("m1", 0, 0.50, 100.0))
    repo.insert_market_snapshot(snap("m1", 5, 0.53, 130.0))

    result = run_measure_shadow_flow_db(repository=repo, output_dir=tmp_path, window="5m")

    assert result.status == "ok"
    assert result.db_status == "inserted"
    assert repo.list_crowd_flow_observations("m1")[0]["prediction_id"] == "p1"
    aggregate_rows = repo.list_agent_measurements("bot_a")
    assert aggregate_rows
    assert aggregate_rows[0]["metrics"]["measurement_target"] == "crowd_flow_prediction_accuracy"


def test_render_report_separates_metrics_and_avoids_money_language() -> None:
    summary = aggregate_measurements([obs("p1", "m1", "bot_a", True, 0.02, 10.0, 0.9)], total_predictions=1)
    report = render_measurement_report(summary=summary, gate_decision=summary.gate_decision, status="ok", db_status="skipped_unavailable", artifact_path=Path("artifact.jsonl"))

    assert "Event accuracy: not measured" in report
    assert "Crowd-flow prediction accuracy: measured" in report
    assert "Execution feasibility: liquidity caveat only" in report
    assert "No real orders were placed" in report
    assert "profit" not in report.lower()
