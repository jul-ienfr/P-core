from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping
import json

from .artifacts import JsonlArtifactWriter, read_jsonl
from .contracts import CrowdFlowObservation, MarketSnapshot, ShadowPrediction, SCHEMA_VERSION
from .crowd_flow import compute_crowd_flow_observation
from .gates import GateDecision, decide_measurement_gate
from .repositories import PanoptiqueRepository

WINDOW_SECONDS = {"5m": 300, "15m": 900, "30m": 1800, "60m": 3600, "24h": 86400}
DEFAULT_OUTPUT_DIR = Path("/home/jul/prediction_core/data/panoptique/measurements")


def parse_window(window: str) -> int:
    if window not in WINDOW_SECONDS:
        raise ValueError(f"unsupported measurement window {window!r}; expected one of {sorted(WINDOW_SECONDS)}")
    return WINDOW_SECONDS[window]


def confidence_bucket(confidence: float) -> str:
    value = float(confidence)
    if value >= 0.75:
        return "high"
    if value >= 0.50:
        return "medium"
    if value > 0.0:
        return "low"
    return "none"


@dataclass(frozen=True, kw_only=True)
class MeasurementSummary:
    total_predictions: int
    matched_observations: int
    hit_rate_by_agent: dict[str, float] = field(default_factory=dict)
    mean_price_delta_by_confidence_bucket: dict[str, float] = field(default_factory=dict)
    volume_response_by_window: dict[int, float] = field(default_factory=dict)
    false_positive_rate: float = 0.0
    insufficient_liquidity_count: int = 0
    categories: set[str] = field(default_factory=set)
    measurement_separation: dict[str, str] = field(default_factory=dict)
    gate_decision: GateDecision | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_predictions": self.total_predictions,
            "matched_observations": self.matched_observations,
            "hit_rate_by_agent": self.hit_rate_by_agent,
            "mean_price_delta_by_confidence_bucket": self.mean_price_delta_by_confidence_bucket,
            "volume_response_by_window": {str(k): v for k, v in self.volume_response_by_window.items()},
            "false_positive_rate": self.false_positive_rate,
            "insufficient_liquidity_count": self.insufficient_liquidity_count,
            "categories": sorted(self.categories),
            "measurement_separation": self.measurement_separation,
            "gate_decision": self.gate_decision.to_dict() if self.gate_decision else None,
        }


@dataclass(frozen=True)
class MeasurementRunResult:
    command: str
    source: str
    status: str
    count: int
    artifact_path: Path
    report_path: Path
    db_status: str
    errors: list[str]
    gate_decision: GateDecision


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def aggregate_measurements(observations: Iterable[CrowdFlowObservation], *, total_predictions: int) -> MeasurementSummary:
    rows = list(observations)
    by_agent: dict[str, list[bool]] = {}
    by_bucket: dict[str, list[float]] = {}
    by_window_volume: dict[int, list[float]] = {}
    categories: set[str] = set()
    false_positive_count = 0
    insufficient_liquidity_count = 0

    for row in rows:
        agent_id = str(row.metrics.get("agent_id") or "unknown")
        conf = float(row.metrics.get("confidence") or 0.0)
        bucket = str(row.metrics.get("confidence_bucket") or confidence_bucket(conf))
        by_agent.setdefault(agent_id, []).append(bool(row.direction_hit))
        by_bucket.setdefault(bucket, []).append(float(row.price_delta))
        by_window_volume.setdefault(int(row.window_seconds), []).append(float(row.volume_delta))
        category = row.metrics.get("category")
        if category:
            categories.add(str(category))
        if row.liquidity_caveat:
            insufficient_liquidity_count += 1
        if not row.direction_hit:
            false_positive_count += 1

    hit_rate_by_agent = {agent: _mean([1.0 if hit else 0.0 for hit in hits]) for agent, hits in by_agent.items()}
    overall_hit_rate = _mean([1.0 if row.direction_hit else 0.0 for row in rows]) if rows else None
    liquidity_rate = insufficient_liquidity_count / len(rows) if rows else None
    gate = decide_measurement_gate(
        total_predictions=total_predictions,
        matched_observations=len(rows),
        hit_rate=overall_hit_rate,
        categories=categories,
        liquidity_caveat_rate=liquidity_rate,
        out_of_sample_positive=None,
    )
    return MeasurementSummary(
        total_predictions=total_predictions,
        matched_observations=len(rows),
        hit_rate_by_agent=hit_rate_by_agent,
        mean_price_delta_by_confidence_bucket={bucket: _mean(values) for bucket, values in by_bucket.items()},
        volume_response_by_window={window: _mean(values) for window, values in by_window_volume.items()},
        false_positive_rate=false_positive_count / len(rows) if rows else 0.0,
        insufficient_liquidity_count=insufficient_liquidity_count,
        categories=categories,
        measurement_separation={
            "event_accuracy": "not_measured",
            "crowd_flow_prediction_accuracy": "measured" if rows else "not_measured",
            "execution_feasibility": "liquidity_caveat_only",
        },
        gate_decision=gate,
    )


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    raise TypeError(f"expected datetime string, got {type(value).__name__}")


def _prediction_from_record(record: Mapping[str, Any]) -> ShadowPrediction:
    data = dict(record)
    data["observed_at"] = _parse_datetime(data["observed_at"])
    return ShadowPrediction(**data)


def _snapshot_from_record(record: Mapping[str, Any]) -> MarketSnapshot:
    data = dict(record)
    data["observed_at"] = _parse_datetime(data["observed_at"])
    return MarketSnapshot(**data)


def _extract_prediction(row: Mapping[str, Any]) -> ShadowPrediction | None:
    value = row.get("prediction") if "prediction" in row else row
    if not isinstance(value, Mapping):
        return None
    return _prediction_from_record(value)


def _extract_snapshot(row: Mapping[str, Any]) -> MarketSnapshot | None:
    value = row.get("snapshot") if "snapshot" in row else row.get("market_snapshot") if "market_snapshot" in row else row
    if not isinstance(value, Mapping):
        return None
    if "observed_at" not in value or "market_id" not in value:
        return None
    return _snapshot_from_record(value)


def load_predictions_jsonl(path: str | Path) -> list[ShadowPrediction]:
    return [p for p in (_extract_prediction(row) for row in read_jsonl(path)) if p is not None]


def load_snapshots_dir(path: str | Path) -> list[MarketSnapshot]:
    snapshots: list[MarketSnapshot] = []
    for file_path in sorted(Path(path).glob("*.jsonl")):
        snapshots.extend(s for s in (_extract_snapshot(row) for row in read_jsonl(file_path)) if s is not None)
    return snapshots


def _latest_before(prediction: ShadowPrediction, candidates: list[MarketSnapshot]) -> MarketSnapshot | None:
    eligible = [s for s in candidates if s.market_id == prediction.market_id and s.observed_at <= prediction.observed_at]
    return max(eligible, key=lambda s: s.observed_at) if eligible else None


def _first_at_or_after(target: datetime, market_id: str, candidates: list[MarketSnapshot]) -> MarketSnapshot | None:
    eligible = [s for s in candidates if s.market_id == market_id and s.observed_at >= target]
    return min(eligible, key=lambda s: s.observed_at) if eligible else None


def match_predictions_to_snapshots(
    predictions: Iterable[ShadowPrediction],
    snapshots: Iterable[MarketSnapshot],
    *,
    window_seconds: int,
    min_liquidity: float = 100.0,
) -> list[CrowdFlowObservation]:
    snapshot_list = sorted(list(snapshots), key=lambda s: s.observed_at)
    observations: list[CrowdFlowObservation] = []
    for prediction in predictions:
        before = _latest_before(prediction, snapshot_list)
        after = _first_at_or_after(prediction.observed_at + timedelta(seconds=window_seconds), prediction.market_id, snapshot_list)
        if before is None or after is None:
            continue
        observation = compute_crowd_flow_observation(prediction, before, after, window_seconds=window_seconds, min_liquidity=min_liquidity)
        metrics = dict(observation.metrics)
        metrics["confidence_bucket"] = confidence_bucket(prediction.confidence)
        observation = CrowdFlowObservation(**{**observation.to_record(), "observed_at": observation.observed_at, "metrics": metrics})
        observations.append(observation)
    return observations


def _timestamp_id(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def _write_measurement_artifact(path: Path, *, source: str, status: str, db_status: str, observations: list[CrowdFlowObservation], summary: MeasurementSummary, errors: list[str]) -> None:
    metadata = {"source": source, "status": status, "db_status": db_status, "schema_version": SCHEMA_VERSION, "paper_only": True, "trading_action": "none"}
    if observations:
        rows = [{"metadata": metadata, "observation": observation.to_record(), "summary": summary.to_dict()} for observation in observations]
    else:
        rows = [{"metadata": metadata, "observation": None, "summary": summary.to_dict(), "errors": errors}]
    JsonlArtifactWriter(path, source=source, artifact_type="panoptique_crowd_flow_measurements").write_many(rows)


def _write_report(path: Path, *, summary: MeasurementSummary, status: str, db_status: str, artifact_path: Path, errors: list[str]) -> None:
    from .reports import render_measurement_report

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_measurement_report(summary=summary, gate_decision=summary.gate_decision, status=status, db_status=db_status, artifact_path=artifact_path, errors=errors), encoding="utf-8")


def _persist_observations(repository: PanoptiqueRepository | None, observations: list[CrowdFlowObservation], summary: MeasurementSummary) -> str:
    if repository is None:
        return "skipped_unavailable"
    for observation in observations:
        repository.insert_crowd_flow_observation(observation)
    repository.insert_agent_measurements_from_summary(summary)
    return "inserted"


def run_measure_shadow_flow_archive(
    *,
    predictions_jsonl: str | Path,
    snapshots_dir: str | Path,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    window: str = "15m",
    repository: PanoptiqueRepository | None = None,
) -> MeasurementRunResult:
    evaluated_at = datetime.now(UTC)
    out = Path(output_dir)
    artifact_path = out / f"measure-shadow-flow-archive-{window}-{_timestamp_id(evaluated_at)}.jsonl"
    report_path = out / f"measure-shadow-flow-archive-{window}-{_timestamp_id(evaluated_at)}.md"
    errors: list[str] = []
    status = "ok"
    observations: list[CrowdFlowObservation] = []
    predictions: list[ShadowPrediction] = []
    try:
        window_seconds = parse_window(window)
        predictions = load_predictions_jsonl(predictions_jsonl)
        snapshots = load_snapshots_dir(snapshots_dir)
        observations = match_predictions_to_snapshots(predictions, snapshots, window_seconds=window_seconds)
    except Exception as exc:
        status = "error"
        errors.append(str(exc))
    summary = aggregate_measurements(observations, total_predictions=len(predictions))
    db_status = _persist_observations(repository, observations, summary) if status == "ok" else "not_inserted_error"
    _write_measurement_artifact(artifact_path, source="archive", status=status, db_status=db_status, observations=observations, summary=summary, errors=errors)
    _write_report(report_path, summary=summary, status=status, db_status=db_status, artifact_path=artifact_path, errors=errors)
    return MeasurementRunResult("measure-shadow-flow", "archive", status, len(observations), artifact_path, report_path, db_status, errors, summary.gate_decision)


def run_measure_shadow_flow_db(
    *,
    repository: PanoptiqueRepository | None,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    window: str = "5m",
) -> MeasurementRunResult:
    evaluated_at = datetime.now(UTC)
    out = Path(output_dir)
    artifact_path = out / f"measure-shadow-flow-db-{window}-{_timestamp_id(evaluated_at)}.jsonl"
    report_path = out / f"measure-shadow-flow-db-{window}-{_timestamp_id(evaluated_at)}.md"
    errors: list[str] = []
    if repository is None:
        summary = aggregate_measurements([], total_predictions=0)
        db_status = "skipped_unavailable"
        status = "skipped"
        errors.append("repository unavailable")
        _write_measurement_artifact(artifact_path, source="db", status=status, db_status=db_status, observations=[], summary=summary, errors=errors)
        _write_report(report_path, summary=summary, status=status, db_status=db_status, artifact_path=artifact_path, errors=errors)
        return MeasurementRunResult("measure-shadow-flow-db", "db", status, 0, artifact_path, report_path, db_status, errors, summary.gate_decision)

    from .repositories import _decode_rows

    window_seconds = parse_window(window)
    pred_rows = _decode_rows(repository.conn.execute("SELECT * FROM shadow_predictions ORDER BY observed_at, prediction_id").fetchall())
    snap_rows = _decode_rows(repository.conn.execute("SELECT * FROM market_price_snapshots ORDER BY observed_at, snapshot_id").fetchall())
    predictions = [_prediction_from_record(row) for row in pred_rows]
    snapshots = [_snapshot_from_record(row) for row in snap_rows]
    observations = match_predictions_to_snapshots(predictions, snapshots, window_seconds=window_seconds)
    summary = aggregate_measurements(observations, total_predictions=len(predictions))
    db_status = _persist_observations(repository, observations, summary)
    _write_measurement_artifact(artifact_path, source="db", status="ok", db_status=db_status, observations=observations, summary=summary, errors=[])
    _write_report(report_path, summary=summary, status="ok", db_status=db_status, artifact_path=artifact_path, errors=[])
    return MeasurementRunResult("measure-shadow-flow-db", "db", "ok", len(observations), artifact_path, report_path, db_status, [], summary.gate_decision)
