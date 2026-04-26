from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .repositories import PanoptiqueRepository


@dataclass(frozen=True)
class PanoptiqueSummary:
    source: str
    readiness_state: str
    snapshot_freshness_seconds: int | None
    shadow_prediction_count: int
    matched_observation_count: int
    current_gate_status: str
    latest_operator_report_path: str | None
    recommendation: None = None
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    errors: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "readiness_state": self.readiness_state,
            "snapshot_freshness_seconds": self.snapshot_freshness_seconds,
            "shadow_prediction_count": self.shadow_prediction_count,
            "matched_observation_count": self.matched_observation_count,
            "current_gate_status": self.current_gate_status,
            "latest_operator_report_path": self.latest_operator_report_path,
            "recommendation": self.recommendation,
            "generated_at": self.generated_at,
            "errors": list(self.errors),
        }


def build_panoptique_summary(
    repository: PanoptiqueRepository | None,
    *,
    report_path: str | Path | None = None,
) -> PanoptiqueSummary:
    """Build the read-only cockpit summary from the local repository.

    The summary intentionally exposes observation health and measurement gate state
    only; it does not produce trading recommendations or touch wallet credentials.
    """

    if repository is None:
        return PanoptiqueSummary(
            source="none",
            readiness_state="empty",
            snapshot_freshness_seconds=None,
            shadow_prediction_count=0,
            matched_observation_count=0,
            current_gate_status="not_enough_data",
            latest_operator_report_path=str(report_path) if report_path else None,
            errors=("SQLite repository not configured.",),
        )

    now = datetime.now(UTC)
    snapshot_rows = repository.conn.execute(
        "SELECT observed_at FROM market_price_snapshots ORDER BY observed_at DESC LIMIT 1"
    ).fetchall()
    prediction_count = int(repository.conn.execute("SELECT COUNT(*) FROM shadow_predictions").fetchone()[0])
    observation_count = int(repository.conn.execute("SELECT COUNT(*) FROM crowd_flow_observations").fetchone()[0])
    measurement_rows = repository.conn.execute(
        "SELECT metrics FROM agent_measurements ORDER BY observed_at DESC, measurement_id DESC LIMIT 1"
    ).fetchall()

    freshness: int | None = None
    if snapshot_rows:
        observed_raw = snapshot_rows[0]["observed_at"]
        try:
            observed_at = datetime.fromisoformat(str(observed_raw).replace("Z", "+00:00"))
            if observed_at.tzinfo is None:
                observed_at = observed_at.replace(tzinfo=UTC)
            freshness = max(0, int((now - observed_at).total_seconds()))
        except ValueError:
            freshness = None

    gate_status = "not_enough_data"
    if measurement_rows:
        import json

        metrics_raw = measurement_rows[0]["metrics"]
        metrics = json.loads(metrics_raw) if isinstance(metrics_raw, str) else metrics_raw
        gate = (metrics or {}).get("summary", {}).get("gate_decision", {})
        gate_status = str(gate.get("status") or gate.get("state") or gate_status)
    elif observation_count > 0:
        gate_status = "measurement_pending"

    readiness = "ready" if snapshot_rows and prediction_count > 0 else "empty"
    return PanoptiqueSummary(
        source="db",
        readiness_state=readiness,
        snapshot_freshness_seconds=freshness,
        shadow_prediction_count=prediction_count,
        matched_observation_count=observation_count,
        current_gate_status=gate_status,
        latest_operator_report_path=str(report_path) if report_path else None,
    )
