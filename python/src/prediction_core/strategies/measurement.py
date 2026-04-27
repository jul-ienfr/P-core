from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

from prediction_core.evaluation import safe_mean

from .contracts import StrategyMode, StrategySignal, StrategyTarget


@dataclass(frozen=True, kw_only=True)
class StrategyMetricSnapshot:
    strategy_id: str
    target: StrategyTarget | str
    mode: StrategyMode | str
    gate_status: str
    signal_count: int
    probability_count: int
    average_confidence: float
    average_expected_move: float | None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "target", self.target if isinstance(self.target, StrategyTarget) else StrategyTarget(str(self.target)))
        object.__setattr__(self, "mode", self.mode if isinstance(self.mode, StrategyMode) else StrategyMode(str(self.mode)))

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["target"] = self.target.value
        payload["mode"] = self.mode.value
        return payload


def project_strategy_metrics(signals: Iterable[StrategySignal], *, min_samples: int = 2) -> list[StrategyMetricSnapshot]:
    groups: dict[tuple[str, StrategyTarget, StrategyMode, str], list[StrategySignal]] = {}
    for signal in signals:
        key = (signal.strategy_id, signal.target, signal.mode, signal.gate_status)
        groups.setdefault(key, []).append(signal)
    snapshots: list[StrategyMetricSnapshot] = []
    for (strategy_id, target, mode, gate_status), rows in sorted(groups.items(), key=lambda item: (item[0][0], item[0][1].value, item[0][3])):
        moves = [abs(float(row.expected_move)) for row in rows if row.expected_move is not None]
        resolved_gate = gate_status if len(rows) >= min_samples and gate_status != "unknown" else "not_enough_data"
        snapshots.append(
            StrategyMetricSnapshot(
                strategy_id=strategy_id,
                target=target,
                mode=mode,
                gate_status=resolved_gate,
                signal_count=len(rows),
                probability_count=sum(1 for row in rows if row.probability is not None),
                average_confidence=safe_mean([row.confidence for row in rows]),
                average_expected_move=safe_mean(moves) if moves else None,
                metadata={
                    "measurement_target": target.value,
                    "sample_state": "enough_data" if len(rows) >= min_samples else "not_enough_data",
                    "execution_edge_reported_separately": target == StrategyTarget.EXECUTABLE_EDGE_AFTER_COSTS,
                },
            )
        )
    return snapshots


def group_signals_for_read_model(signals: Iterable[StrategySignal]) -> dict[str, Any]:
    snapshots = project_strategy_metrics(signals)
    return {
        "snapshots": [snapshot.to_dict() for snapshot in snapshots],
        "targets": sorted({snapshot.target.value for snapshot in snapshots}),
        "strategy_count": len({snapshot.strategy_id for snapshot in snapshots}),
    }
