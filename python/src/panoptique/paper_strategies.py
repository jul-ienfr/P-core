from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from prediction_core.execution import (
    BookLevel,
    OrderBookSnapshot,
    TradingFeeSchedule,
    TransferFeeSchedule,
    build_execution_cost_breakdown,
    estimate_execution_costs,
    estimate_fill_from_book,
)
from prediction_core.execution.models import ExecutionCostBreakdown

from .artifacts import JsonlArtifactWriter, read_jsonl
from .contracts import SCHEMA_VERSION

DEFAULT_OUTPUT_DIR = Path("/home/jul/prediction_core/data/panoptique/paper_strategies")


@dataclass(frozen=True, kw_only=True)
class PaperStrategyConfig:
    min_confidence: float = 0.70
    fade_min_observed_move: float = 0.05
    min_expected_move: float = 0.03
    min_net_edge: float = 0.005
    max_spread: float = 0.05
    paper_quantity: float = 50.0
    min_fill_ratio: float = 0.80
    taker_fee_bps: float = 25.0
    conservative_slippage_buffer: float = 0.01
    liquidity_role: str = "taker"

    def trading_fees(self) -> TradingFeeSchedule:
        return TradingFeeSchedule(maker_bps=0.0, taker_bps=self.taker_fee_bps, min_fee=0.0)

    def transfer_fees(self) -> TransferFeeSchedule:
        return TransferFeeSchedule()

    def friction_assumptions(self) -> dict[str, Any]:
        return {
            "liquidity_role": self.liquidity_role,
            "paper_quantity": self.paper_quantity,
            "max_spread": self.max_spread,
            "min_fill_ratio": self.min_fill_ratio,
            "taker_fee_bps": self.taker_fee_bps,
            "conservative_slippage_buffer": self.conservative_slippage_buffer,
            "cost_model": "prediction_core.execution.build_execution_cost_breakdown",
            "transfer_fees": asdict(self.transfer_fees()),
            "real_orders": False,
        }


@dataclass(frozen=True, kw_only=True)
class PaperStrategyInput:
    observation_id: str
    prediction_id: str
    market_id: str
    observed_at: datetime
    predicted_crowd_direction: str
    confidence: float
    expected_crowd_move: float
    observed_crowd_move: float = 0.0
    book: OrderBookSnapshot
    archetype: str = "crowd_flow"
    split: str = "all"


@dataclass(frozen=True, kw_only=True)
class PaperStrategyDecision:
    decision_id: str
    market_id: str
    prediction_id: str
    observation_id: str
    evaluated_at: datetime
    mode: str
    status: str
    paper_side: str | None
    predicted_crowd_move: float
    confidence: float
    gross_edge: float
    net_edge_after_costs: float
    friction_assumptions: dict[str, Any]
    entry_assumption: str
    exit_assumption: str
    failure_modes: list[str]
    reasons: list[str] = field(default_factory=list)
    cost_breakdown: ExecutionCostBreakdown | None = None
    split: str = "all"
    paper_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "decision_id": self.decision_id,
            "market_id": self.market_id,
            "prediction_id": self.prediction_id,
            "observation_id": self.observation_id,
            "evaluated_at": self.evaluated_at.isoformat(),
            "mode": self.mode,
            "status": self.status,
            "paper_side": self.paper_side,
            "predicted_crowd_move": self.predicted_crowd_move,
            "confidence": self.confidence,
            "gross_edge": self.gross_edge,
            "net_edge_after_costs": self.net_edge_after_costs,
            "friction_assumptions": self.friction_assumptions,
            "cost_breakdown": self.cost_breakdown.to_dict() if self.cost_breakdown else None,
            "entry_assumption": self.entry_assumption,
            "exit_assumption": self.exit_assumption,
            "failure_modes": self.failure_modes,
            "reasons": self.reasons,
            "split": self.split,
            "paper_only": self.paper_only,
            "trading_action": "none",
            "result_language": "research_only_not_return_claim",
        }


@dataclass(frozen=True)
class PaperStrategyRunResult:
    command: str
    source: str
    status: str
    count: int
    artifact_path: Path
    report_path: Path
    db_status: str
    errors: list[str]


def _timestamp_id(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    raise TypeError(f"expected datetime string, got {type(value).__name__}")


def _levels(rows: Iterable[Mapping[str, Any]]) -> list[BookLevel]:
    return [BookLevel(price=float(row["price"]), quantity=float(row.get("quantity", row.get("size", 0.0)))) for row in rows]


def _book_from_mapping(value: Mapping[str, Any]) -> OrderBookSnapshot:
    return OrderBookSnapshot(
        bids=_levels(value.get("bids", [])),
        asks=_levels(value.get("asks", [])),
        timestamp=_parse_datetime(value["timestamp"]) if value.get("timestamp") else None,
        venue=str(value.get("venue")) if value.get("venue") else None,
    )


def _signal_from_record(record: Mapping[str, Any]) -> PaperStrategyInput:
    row = record.get("signal") if isinstance(record.get("signal"), Mapping) else record
    metrics = row.get("metrics", {}) if isinstance(row.get("metrics"), Mapping) else {}
    prediction = row.get("prediction", {}) if isinstance(row.get("prediction"), Mapping) else {}
    observation = row.get("observation", {}) if isinstance(row.get("observation"), Mapping) else {}
    direction = row.get("predicted_crowd_direction") or prediction.get("predicted_crowd_direction") or metrics.get("predicted_crowd_direction") or "unknown"
    expected_move = row.get("expected_crowd_move", metrics.get("expected_crowd_move", observation.get("price_delta", 0.0)))
    observed_move = row.get("observed_crowd_move", observation.get("price_delta", 0.0))
    book_value = row.get("book") or row.get("order_book") or {}
    if not isinstance(book_value, Mapping):
        book_value = {}
    return PaperStrategyInput(
        observation_id=str(row.get("observation_id") or observation.get("observation_id") or "unknown"),
        prediction_id=str(row.get("prediction_id") or prediction.get("prediction_id") or observation.get("prediction_id") or "unknown"),
        market_id=str(row.get("market_id") or prediction.get("market_id") or observation.get("market_id") or "unknown"),
        observed_at=_parse_datetime(row.get("observed_at") or prediction.get("observed_at") or observation.get("observed_at")),
        predicted_crowd_direction=str(direction).lower(),
        confidence=float(row.get("confidence", prediction.get("confidence", metrics.get("confidence", 0.0))) or 0.0),
        expected_crowd_move=float(expected_move or 0.0),
        observed_crowd_move=float(observed_move or 0.0),
        book=_book_from_mapping(book_value),
        archetype=str(row.get("archetype") or metrics.get("archetype") or "crowd_flow"),
    )


def load_paper_strategy_signals(path: str | Path) -> list[PaperStrategyInput]:
    return [_signal_from_record(row) for row in read_jsonl(path)]


def _paper_side_for_front_run(direction: str) -> str | None:
    if direction in {"up", "yes", "buy", "long"}:
        return "buy"
    if direction in {"down", "no", "sell", "short"}:
        return "sell"
    return None


def _opposite(side: str | None) -> str | None:
    if side == "buy":
        return "sell"
    if side == "sell":
        return "buy"
    return None


def _fair_probability(signal: PaperStrategyInput, side: str, config: PaperStrategyConfig) -> float:
    mid = signal.book.mid_price
    if mid is None:
        mid = signal.book.best_ask if side == "buy" else signal.book.best_bid
    if mid is None:
        return 0.0
    move = abs(signal.expected_crowd_move or signal.observed_crowd_move)
    conservative_move = max(0.0, move - config.conservative_slippage_buffer)
    if side == "buy":
        return max(0.0, min(1.0, mid + conservative_move))
    return max(0.0, min(1.0, mid - conservative_move))


def _cost_breakdown(signal: PaperStrategyInput, side: str, config: PaperStrategyConfig) -> ExecutionCostBreakdown:
    if side == "buy":
        return build_execution_cost_breakdown(
            book=signal.book,
            requested_quantity=config.paper_quantity,
            side=side,
            fair_probability=_fair_probability(signal, side, config),
            trading_fees=config.trading_fees(),
            liquidity_role=config.liquidity_role,
            transfer_fees=config.transfer_fees(),
        )
    fill = estimate_fill_from_book(book=signal.book, side=side, requested_quantity=config.paper_quantity)
    edge_gross = 0.0
    if fill.filled_quantity > 0:
        conservative_move = max(0.0, abs(signal.expected_crowd_move or signal.observed_crowd_move) - config.conservative_slippage_buffer)
        edge_gross = conservative_move * fill.filled_quantity
    return estimate_execution_costs(
        book=signal.book,
        side=side,
        requested_quantity=config.paper_quantity,
        trading_fee_schedule=config.trading_fees(),
        transfer_fee_schedule=config.transfer_fees(),
        is_maker=config.liquidity_role == "maker",
        edge_gross=edge_gross,
        fill_estimate=fill,
    )


def _base_failures() -> list[str]:
    return [
        "crowd-flow forecast may be wrong out-of-sample",
        "spread, depth, or slippage may be worse than conservative paper assumptions",
        "source leakage or lookahead would invalidate research conclusions",
        "paper simulation omits real venue latency and fill uncertainty",
    ]


def decide_paper_strategy(signal: PaperStrategyInput, *, config: PaperStrategyConfig | None = None, evaluated_at: datetime | None = None) -> PaperStrategyDecision:
    cfg = config or PaperStrategyConfig()
    now = evaluated_at or datetime.now(UTC)
    reasons: list[str] = []
    front_side = _paper_side_for_front_run(signal.predicted_crowd_direction)
    mode = "skip"
    side: str | None = None
    if signal.confidence >= cfg.min_confidence and abs(signal.expected_crowd_move) >= cfg.min_expected_move and front_side is not None:
        mode = "front_run_paper"
        side = front_side
    elif abs(signal.observed_crowd_move) >= cfg.fade_min_observed_move and front_side is not None:
        mode = "fade_paper"
        side = _opposite(front_side)
    else:
        if signal.confidence < cfg.min_confidence:
            reasons.append("confidence below paper threshold")
        if abs(signal.expected_crowd_move) < cfg.min_expected_move and abs(signal.observed_crowd_move) < cfg.fade_min_observed_move:
            reasons.append("expected crowd move too small for conservative paper threshold")
        if front_side is None:
            reasons.append("unknown predicted crowd direction")

    breakdown: ExecutionCostBreakdown | None = None
    gross_edge = 0.0
    net_edge = 0.0
    if side is not None:
        breakdown = _cost_breakdown(signal, side, cfg)
        gross_edge = breakdown.edge_gross
        net_edge = breakdown.edge_net_execution
        fill_ratio = breakdown.estimated_filled_quantity / cfg.paper_quantity if cfg.paper_quantity > 0 else 0.0
        if fill_ratio < cfg.min_fill_ratio:
            reasons.append("depth insufficient for requested paper quantity")
        if signal.book.spread is None:
            reasons.append("missing two-sided book spread")
        elif signal.book.spread > cfg.max_spread:
            reasons.append("spread wider than conservative paper threshold")
        if net_edge < cfg.min_net_edge:
            reasons.append("net edge after spread/slippage/fees below paper threshold")
    else:
        fallback_side = front_side or "buy"
        breakdown = _cost_breakdown(signal, fallback_side, cfg)
        gross_edge = breakdown.edge_gross
        net_edge = breakdown.edge_net_execution

    status = "paper_candidate" if mode != "skip" and not reasons else "skip"
    if status == "skip":
        mode = "skip"
        side = None

    entry = "Simulated taker fill against archived top-of-book/depth only; no order routed."
    exit_assumption = "Simulated exit after crowd-flow horizon at measured/predicted crowd move; no real position opened."
    return PaperStrategyDecision(
        decision_id=f"paper-{signal.prediction_id}-{_timestamp_id(now)}",
        market_id=signal.market_id,
        prediction_id=signal.prediction_id,
        observation_id=signal.observation_id,
        evaluated_at=now,
        mode=mode,
        status=status,
        paper_side=side,
        predicted_crowd_move=round(float(signal.expected_crowd_move), 6),
        confidence=round(float(signal.confidence), 6),
        gross_edge=round(gross_edge, 6),
        net_edge_after_costs=round(net_edge, 6),
        friction_assumptions=cfg.friction_assumptions(),
        cost_breakdown=breakdown,
        entry_assumption=entry,
        exit_assumption=exit_assumption,
        failure_modes=_base_failures(),
        reasons=reasons or ["paper-only candidate after conservative cost checks"],
        split=signal.split,
    )


def apply_out_of_sample_split(signals: list[PaperStrategyInput], *, out_of_sample_fraction: float = 0.0) -> list[PaperStrategyInput]:
    fraction = max(0.0, min(1.0, float(out_of_sample_fraction)))
    if not signals or fraction <= 0.0:
        return signals
    split_start = max(0, min(len(signals), int(round(len(signals) * (1.0 - fraction)))))
    result: list[PaperStrategyInput] = []
    for index, signal in enumerate(signals):
        split = "out_of_sample" if index >= split_start else "train"
        result.append(replace(signal, split=split))
    return result


def _write_artifact(path: Path, *, decisions: list[PaperStrategyDecision], status: str, errors: list[str]) -> None:
    metadata = {"schema_version": SCHEMA_VERSION, "status": status, "paper_only": True, "trading_action": "none", "research_only": True}
    rows = [{"metadata": metadata, "decision": d.to_dict()} for d in decisions]
    if not rows:
        rows = [{"metadata": metadata, "decision": None, "errors": errors or ["not_enough_data"]}]
    JsonlArtifactWriter(path, source="panoptique_paper_strategies", artifact_type="panoptique_paper_strategy_decisions").write_many(rows)


def render_paper_strategy_report(
    decisions: Iterable[PaperStrategyDecision],
    *,
    status: str,
    artifact_path: Path,
    out_of_sample_fraction: float = 0.0,
    errors: list[str] | None = None,
) -> str:
    rows = list(decisions)
    candidates = [d for d in rows if d.status == "paper_candidate"]
    skips = [d for d in rows if d.status == "skip"]
    lines = [
        "# Panoptique Paper Strategy Research Report",
        "",
        "Paper-only research simulation for front-run/fade/skip strategy experiments.",
        "No real orders were placed, no wallet credentials were used, and no live trading is enabled.",
        "Results are research/paper observations only, never monetary-return claims.",
        "",
        "## Run status",
        "",
        f"- Status: `{status}`",
        f"- Artifact: `{artifact_path}`",
        f"- Decisions: `{len(rows)}`",
        f"- Paper candidates: `{len(candidates)}`",
        f"- Skips: `{len(skips)}`",
        f"- Out-of-sample fraction: `{out_of_sample_fraction:.3f}`",
        "",
        "## Simulated entry/exit assumptions",
        "",
        "- Entry: simulated taker interaction with archived order-book depth only.",
        "- Exit: simulated after the crowd-flow horizon using measured or predicted crowd move.",
        "- Safety: no real order language is operational; all actions are `paper_only` / `trading_action=none`.",
        "",
        "## Failure modes",
        "",
    ]
    for item in _base_failures():
        lines.append(f"- {item}")
    lines.extend(["", "## Decision details", ""])
    if not rows:
        lines.append("- not_enough_data: strategy output is skip/not_enough_data, which is valid.")
    for decision in rows:
        cost = decision.cost_breakdown.to_dict() if decision.cost_breakdown else {}
        lines.extend([
            f"### `{decision.decision_id}`",
            "",
            f"- Mode: `{decision.mode}`",
            f"- Status: `{decision.status}`",
            f"- Split: `{decision.split}`",
            f"- Predicted crowd move: `{decision.predicted_crowd_move:.6f}`",
            f"- Simulated side: `{decision.paper_side or 'none'}`",
            f"- Net edge after costs: `{decision.net_edge_after_costs:.6f}` (paper research metric, not monetary performance or return)",
            f"- Friction assumptions: `{json.dumps(decision.friction_assumptions, sort_keys=True)}`",
            f"- Costs: `{json.dumps(cost, sort_keys=True)}`",
            f"- Reasons: `{'; '.join(decision.reasons)}`",
            "",
        ])
    if errors:
        lines.extend(["## Errors", ""])
        lines.extend(f"- {error}" for error in errors)
    return "\n".join(lines) + "\n"


def run_paper_strategy_fixture(
    *,
    fixture_path: str | Path,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    out_of_sample_fraction: float = 0.0,
    config: PaperStrategyConfig | None = None,
) -> PaperStrategyRunResult:
    evaluated_at = datetime.now(UTC)
    out = Path(output_dir)
    artifact_path = out / f"panoptique-paper-strategies-{_timestamp_id(evaluated_at)}.jsonl"
    report_path = out / f"panoptique-paper-strategies-{_timestamp_id(evaluated_at)}.md"
    errors: list[str] = []
    decisions: list[PaperStrategyDecision] = []
    status = "ok"
    try:
        path = Path(fixture_path)
        if not path.exists():
            raise FileNotFoundError(f"fixture not found: {path}")
        signals = apply_out_of_sample_split(load_paper_strategy_signals(path), out_of_sample_fraction=out_of_sample_fraction)
        if not signals:
            status = "not_enough_data"
            errors.append("no paper strategy signals available")
        else:
            decisions = [decide_paper_strategy(signal, config=config, evaluated_at=evaluated_at) for signal in signals]
    except Exception as exc:
        status = "not_enough_data"
        errors.append(str(exc))
    _write_artifact(artifact_path, decisions=decisions, status=status, errors=errors)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        render_paper_strategy_report(decisions, status=status, artifact_path=artifact_path, out_of_sample_fraction=out_of_sample_fraction, errors=errors),
        encoding="utf-8",
    )
    return PaperStrategyRunResult("panoptique-paper-run", "fixture", status, len(decisions), artifact_path, report_path, "skipped_unavailable", errors)
