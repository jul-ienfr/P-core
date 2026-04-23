from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def clamp_confidence(value: float) -> float:
    return max(1e-9, min(1.0 - 1e-9, float(value)))


def calibration_mean(values: list[float], default: float = 0.0) -> float:
    if not values:
        return default
    return round(sum(values) / len(values), 12)


def calibration_bucket(probability: float, buckets: int = 10) -> str:
    clamped = max(0.0, min(1.0 - 1e-9, float(probability)))
    index = min(max(0, int(clamped * buckets)), max(0, buckets - 1))
    lower = index / buckets
    upper = (index + 1) / buckets
    return f"{lower:.1f}-{upper:.1f}"


def score_metadata(score: Any) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    manifest = getattr(score, 'manifest', None)
    forecast = getattr(score, 'forecast', None)
    score_level_metadata = getattr(score, 'metadata', {})
    metadata.update(dict(getattr(manifest, 'metadata', {})) if manifest is not None else {})
    metadata.update(dict(getattr(manifest, 'inputs', {})) if manifest is not None else {})
    if forecast is not None:
        metadata.update(dict(getattr(forecast, 'metadata', {})))
    metadata.update(dict(score_level_metadata))
    return metadata


def score_market_family(score: Any) -> str:
    metadata = score_metadata(score)
    for key in ('market_family', 'category', 'market_category', 'theme', 'sector', 'segment'):
        value = metadata.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    venue = getattr(score, 'venue', 'unknown')
    return str(getattr(venue, 'value', venue)).strip() or 'unknown'


def score_category(score: Any) -> str:
    metadata = score_metadata(score)
    for key in ('category', 'market_category', 'theme', 'sector', 'segment'):
        value = metadata.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return score_market_family(score)


def score_horizon_bucket(score: Any) -> str:
    metadata = score_metadata(score)
    for key in ('horizon_bucket', 'horizon', 'time_horizon', 'window_bucket'):
        value = metadata.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return 'unknown'


def score_model_family(score: Any) -> str:
    metadata = score_metadata(score)
    forecast = getattr(score, 'forecast', None)
    for key in ('model_family', 'engine_used', 'model_used'):
        value = metadata.get(key)
        if value is None and forecast is not None:
            value = getattr(forecast, key, None)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    if forecast is not None:
        text = str(getattr(forecast, 'model_used', '')).strip()
        if text:
            return text
    return 'unknown'


def is_abstention(score: Any) -> bool:
    forecast = getattr(score, 'forecast', None)
    if forecast is None:
        return False
    return getattr(forecast, 'recommendation_action', None) in {'no_trade', 'wait', 'manual_review'}


def score_record_payload(score: Any) -> dict[str, Any]:
    probability_yes = clamp_confidence(getattr(score, 'probability_yes'))
    outcome_yes = bool(getattr(score, 'outcome_yes'))
    metadata = score_metadata(score)
    forecast = getattr(score, 'forecast', None)
    manifest = getattr(score, 'manifest', None)
    forecast_market_implied = getattr(forecast, 'market_implied_probability', probability_yes) if forecast is not None else probability_yes
    forecast_market_implied = clamp_confidence(forecast_market_implied)
    cutoff_at = getattr(forecast, 'forecast_ts', None) if forecast is not None else None
    if cutoff_at is None and manifest is not None:
        cutoff_at = getattr(manifest, 'updated_at', None)
    if cutoff_at is None:
        cutoff_at = datetime.now(timezone.utc)
    return {
        'evaluation_id': getattr(score, 'run_id'),
        'question_id': getattr(score, 'market_id'),
        'market_id': getattr(score, 'market_id'),
        'forecast_probability': probability_yes,
        'market_baseline_probability': forecast_market_implied,
        'resolved_outcome': outcome_yes,
        'brier_score': round(float(getattr(score, 'brier_score')), 6),
        'log_loss': round(float(getattr(score, 'log_loss')), 6),
        'ece_bucket': calibration_bucket(probability_yes),
        'abstain_flag': is_abstention(score),
        'model_family': score_model_family(score),
        'market_family': score_market_family(score),
        'horizon_bucket': score_horizon_bucket(score),
        'market_baseline_delta': round(probability_yes - forecast_market_implied, 6),
        'market_baseline_delta_bps': round((probability_yes - forecast_market_implied) * 10000.0, 2),
        'cutoff_at': cutoff_at,
        'metadata': metadata,
    }
