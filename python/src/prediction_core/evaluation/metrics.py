from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Iterable, Mapping, Sequence


_CANONICAL_METADATA_KEYS = (
    "category",
    "market_category",
    "theme",
    "sector",
    "segment",
    "source",
    "source_kind",
    "retrieval_policy",
    "calibration_version",
)

_CANONICAL_EVALUATION_KEYS = (
    "evaluation_id",
    "question_id",
    "market_id",
    "forecast_probability",
    "resolved_outcome",
    "market_baseline_probability",
    "brier_score",
    "log_loss",
    "ece_bucket",
    "abstain_flag",
    "model_family",
    "market_family",
    "horizon_bucket",
    "market_baseline_delta",
    "market_baseline_delta_bps",
    "cutoff_at",
    "metadata",
)

_TRADE_STATUSES = {"trade", "trade_small", "filled", "partial", "win", "loss"}
_SKIP_STATUSES = {"skip", "skipped", "skipped_price_moved", "cancelled", "watch"}


@dataclass(frozen=True)
class EvaluationReport:
    strategy_id: str
    profile_id: str
    market_id: str
    period_start: str
    period_end: str
    mode: str
    source: str
    gross_pnl_usdc: float
    net_pnl_usdc: float
    execution_cost_usdc: float
    exposure_usdc: float
    turnover_usdc: float
    hit_rate: float | None
    max_drawdown_usdc: float | None
    max_drawdown_fraction: float | None
    sharpe: float | None
    sortino: float | None
    skip_reasons: list[str]
    blockers: list[str]
    gross_edge: float | None
    net_edge: float | None
    all_in_edge: float | None
    paper_only: bool = True
    live_order_allowed: bool = False

    def asdict(self) -> dict[str, Any]:
        return asdict(self)


def _finite_probability(value: float) -> float:
    probability = float(value)
    if not math.isfinite(probability):
        raise ValueError("probability must be finite")
    return probability


def _record_value(record: Any, field: str, default: Any = None) -> Any:
    if isinstance(record, Mapping):
        return record.get(field, default)
    return getattr(record, field, default)


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    return number


def _sum_fields(rows: Sequence[Any], fields: Sequence[str]) -> float:
    total = 0.0
    for row in rows:
        for field in fields:
            value = _float_or_none(_record_value(row, field))
            if value is not None:
                total += value
                break
    return round(total, 6)


def _mean(values: Sequence[float]) -> float | None:
    return round(sum(values) / len(values), 6) if values else None


def _sample_stdev(values: Sequence[float]) -> float | None:
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    return math.sqrt(variance)


def _risk_ratio(values: Sequence[float], downside_only: bool = False) -> float | None:
    series = [float(value) for value in values if math.isfinite(float(value))]
    if len(series) < 2:
        return None
    denominator_values = [value for value in series if value < 0.0] if downside_only else series
    stdev = _sample_stdev(denominator_values)
    if not stdev:
        return None
    return round((sum(series) / len(series)) / stdev, 6)


def _status_matches(status: Any, candidates: set[str]) -> bool:
    normalized = str(status or "").strip().lower()
    return normalized in candidates or any(normalized.startswith(candidate) for candidate in candidates)


def _unique_strings(rows: Sequence[Any], field: str) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for row in rows:
        value = str(_record_value(row, field, "") or "").strip()
        if value and value not in seen:
            values.append(value)
            seen.add(value)
    return values


def _coerce_period(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value or "")


def build_canonical_evaluation_report(
    rows: Iterable[Any],
    *,
    strategy_id: str = "",
    profile_id: str = "",
    market_id: str = "",
    period_start: Any = "",
    period_end: Any = "",
    mode: str = "paper",
    source: str = "analytics",
) -> EvaluationReport:
    """Build a canonical paper-safe evaluation report for strategy/profile/market/period.

    Inputs may be replay rows, paper ledger rows, or analytics events represented as
    mappings or objects. The report intentionally remains analytics-only:
    ``paper_only`` is always true and ``live_order_allowed`` is always false.
    """
    row_list = list(rows)
    if row_list:
        strategy_id = strategy_id or str(_record_value(row_list[0], "strategy_id", "") or "")
        profile_id = profile_id or str(_record_value(row_list[0], "profile_id", "") or "")
        market_id = market_id or str(_record_value(row_list[0], "market_id", "") or "")
        mode = mode or str(_record_value(row_list[0], "mode", "paper") or "paper")

    gross_pnl = _sum_fields(row_list, ("gross_pnl_usdc", "pnl_usdc", "mtm_bid_usdc"))
    net_pnl = _sum_fields(row_list, ("net_pnl_usdc", "pnl_net_usdc", "mtm_bid_usdc"))
    execution_cost = _sum_fields(row_list, ("execution_cost_usdc", "costs_usdc", "opening_fee_usdc"))
    execution_cost += _sum_fields(row_list, ("opening_slippage_usdc",))
    execution_cost += _sum_fields(row_list, ("estimated_exit_cost_usdc",))
    execution_cost = round(execution_cost, 6)
    exposure = _sum_fields(row_list, ("exposure_usdc",))
    turnover = _sum_fields(row_list, ("turnover_usdc", "spend_usdc", "capped_spend_usdc", "requested_spend_usdc"))

    pnl_series = [value for row in row_list if (value := _float_or_none(_record_value(row, "net_pnl_usdc"))) is not None]
    if not pnl_series:
        pnl_series = [value for row in row_list if (value := _float_or_none(_record_value(row, "mtm_bid_usdc"))) is not None]
    wins = sum(1 for value in pnl_series if value > 0)
    losses = sum(1 for value in pnl_series if value <= 0)
    hit_rate = round(wins / (wins + losses), 6) if wins + losses else None

    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for value in pnl_series:
        equity += value
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
    max_drawdown = round(max_drawdown, 6) if pnl_series else None
    max_drawdown_fraction = round(max_drawdown / peak, 6) if max_drawdown is not None and peak > 0 else None

    gross_edges = [value for row in row_list if (value := _float_or_none(_record_value(row, "gross_edge", _record_value(row, "edge")))) is not None]
    net_edges = [value for row in row_list if (value := _float_or_none(_record_value(row, "net_edge"))) is not None]
    all_in_edges = [value for row in row_list if (value := _float_or_none(_record_value(row, "all_in_edge"))) is not None]

    return EvaluationReport(
        strategy_id=strategy_id,
        profile_id=profile_id,
        market_id=market_id,
        period_start=_coerce_period(period_start),
        period_end=_coerce_period(period_end),
        mode=mode,
        source=source,
        gross_pnl_usdc=gross_pnl,
        net_pnl_usdc=net_pnl,
        execution_cost_usdc=execution_cost,
        exposure_usdc=exposure,
        turnover_usdc=turnover,
        hit_rate=hit_rate,
        max_drawdown_usdc=max_drawdown,
        max_drawdown_fraction=max_drawdown_fraction,
        sharpe=_risk_ratio(pnl_series),
        sortino=_risk_ratio(pnl_series, downside_only=True),
        skip_reasons=_unique_strings(
            [row for row in row_list if _status_matches(_record_value(row, "status", _record_value(row, "decision_status")), _SKIP_STATUSES)],
            "skip_reason",
        ),
        blockers=_unique_strings(row_list, "blocker"),
        gross_edge=_mean(gross_edges),
        net_edge=_mean(net_edges),
        all_in_edge=_mean(all_in_edges),
        paper_only=True,
        live_order_allowed=False,
    )


def _canonical_metadata(record: Any) -> dict[str, Any]:
    metadata = _record_value(record, "metadata", {})
    if not isinstance(metadata, Mapping):
        return {}
    return {key: metadata[key] for key in _CANONICAL_METADATA_KEYS if key in metadata}


def clamp_probability(value: float) -> float:
    probability = _finite_probability(value)
    return max(0.0, min(1.0, probability))


def log_loss(probability_yes: float, outcome_yes: bool) -> float:
    probability_yes = _finite_probability(probability_yes)
    probability_yes = max(1e-9, min(1.0 - 1e-9, probability_yes))
    return -math.log(probability_yes if outcome_yes else 1.0 - probability_yes)


def ece_bucket(probability: float, bins: int = 10) -> str:
    bins = max(1, int(bins))
    clamped = clamp_probability(probability)
    index = min(bins - 1, int(clamped * bins))
    lower = index / bins
    upper = (index + 1) / bins

    reduced = bins
    factor_two = 0
    factor_five = 0
    while reduced % 2 == 0:
        reduced //= 2
        factor_two += 1
    while reduced % 5 == 0:
        reduced //= 5
        factor_five += 1
    precision = max(factor_two, factor_five) if reduced == 1 else 6

    return f"{lower:.{precision}f}-{upper:.{precision}f}"


def safe_mean(values: Sequence[float], default: float = 0.0) -> float:
    if not values:
        return default
    return round(sum(float(value) for value in values) / len(values), 12)


def weighted_mean(values: Sequence[tuple[float, int]], default: float = 0.0) -> float:
    total_weight = sum(max(0, int(weight)) for _, weight in values)
    if total_weight <= 0:
        return default
    total = sum(float(value) * max(0, int(weight)) for value, weight in values)
    return round(float(total / total_weight), 12)


def evaluation_record_canonical(record: Any | None) -> dict[str, Any] | None:
    if record is None:
        return None

    forecast_probability = clamp_probability(_record_value(record, "forecast_probability", 0.5))
    resolved_outcome = bool(_record_value(record, "resolved_outcome", False))
    market_baseline_probability = clamp_probability(_record_value(record, "market_baseline_probability", forecast_probability))

    payload: dict[str, Any] = {
        "evaluation_id": _record_value(record, "evaluation_id", ""),
        "question_id": _record_value(record, "question_id", ""),
        "market_id": _record_value(record, "market_id", ""),
        "forecast_probability": forecast_probability,
        "resolved_outcome": resolved_outcome,
        "market_baseline_probability": market_baseline_probability,
        "brier_score": round(float(_record_value(record, "brier_score", (forecast_probability - float(resolved_outcome)) ** 2)), 6),
        "log_loss": round(float(_record_value(record, "log_loss", log_loss(forecast_probability, resolved_outcome))), 12),
        "ece_bucket": _record_value(record, "ece_bucket", ece_bucket(forecast_probability)),
        "abstain_flag": bool(_record_value(record, "abstain_flag", False)),
        "model_family": str(_record_value(record, "model_family", "unknown")).strip() or "unknown",
        "market_family": str(_record_value(record, "market_family", "unknown")).strip() or "unknown",
        "horizon_bucket": str(_record_value(record, "horizon_bucket", "unknown")).strip() or "unknown",
        "market_baseline_delta": round(float(_record_value(record, "market_baseline_delta", forecast_probability - market_baseline_probability)), 6),
        "market_baseline_delta_bps": round(float(_record_value(record, "market_baseline_delta_bps", (forecast_probability - market_baseline_probability) * 10000.0)), 2),
    }

    cutoff_at = _record_value(record, "cutoff_at")
    if cutoff_at is not None:
        payload["cutoff_at"] = cutoff_at

    metadata = _canonical_metadata(record)
    if metadata:
        payload["metadata"] = metadata

    return {key: payload[key] for key in _CANONICAL_EVALUATION_KEYS if key in payload}
