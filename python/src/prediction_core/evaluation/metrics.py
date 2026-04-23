from __future__ import annotations

import math
from typing import Any, Mapping, Sequence


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


def _finite_probability(value: float) -> float:
    probability = float(value)
    if not math.isfinite(probability):
        raise ValueError("probability must be finite")
    return probability


def _record_value(record: Any, field: str, default: Any = None) -> Any:
    if isinstance(record, Mapping):
        return record.get(field, default)
    return getattr(record, field, default)


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
