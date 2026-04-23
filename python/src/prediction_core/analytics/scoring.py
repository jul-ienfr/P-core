from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _coerce_utc_timestamp(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _isoformat_z(value: datetime | None) -> str | None:
    timestamp = _coerce_utc_timestamp(value)
    if timestamp is None:
        return None
    return timestamp.isoformat().replace("+00:00", "Z")


def _summary_preview(summary: str, *, limit: int = 80) -> str:
    normalized = " ".join(summary.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


def clamp_score(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def normalize_stance(value: str | None) -> str:
    if not value:
        return "neutral"
    lowered = value.strip().lower()
    bullish_tokens = {
        "bullish",
        "support",
        "positive",
        "yes",
        "long",
        "up",
        "higher",
        "increase",
        "likely yes",
        "likely",
    }
    bearish_tokens = {
        "bearish",
        "oppose",
        "negative",
        "no",
        "short",
        "down",
        "lower",
        "decrease",
        "likely no",
        "unlikely",
    }
    neutral_tokens = {"neutral", "mixed", "unclear", "unknown", "uncertain", "hold", "wait"}
    if lowered in bullish_tokens or any(token in lowered for token in ("bullish", "support", "yes", "long", "higher", "increase")):
        return "bullish"
    if lowered in bearish_tokens or any(token in lowered for token in ("bearish", "oppose", "no", "short", "lower", "decrease")):
        return "bearish"
    if lowered in neutral_tokens:
        return "neutral"
    return "neutral"


def score_freshness(finding, *, reference_time: datetime | None = None, half_life_hours: float = 24.0) -> float:
    reference = _coerce_utc_timestamp(reference_time) or _utc_now()
    timestamp = _coerce_utc_timestamp(getattr(finding, 'published_at', None) or getattr(finding, 'observed_at', None))
    if timestamp is None:
        base = 0.55
    else:
        delta = max(0.0, (reference - timestamp).total_seconds() / 3600.0)
        base = math.exp(-delta / max(0.1, float(half_life_hours)))
    source_bonus = {
        'official': 0.08,
        'market': 0.06,
        'news': 0.05,
        'social': 0.02,
        'model': 0.0,
        'manual': 0.0,
        'other': 0.0,
    }.get((getattr(finding, 'source_kind', 'other') or 'other').strip().lower(), 0.0)
    recency_bonus = 0.03 if getattr(finding, 'summary', '') else 0.0
    provenance_bonus = 0.02 if getattr(finding, 'source_url', None) else 0.0
    return clamp_score(base + source_bonus + recency_bonus + provenance_bonus)


def build_finding_analytics(
    finding: Any,
    *,
    reference_time: datetime | None = None,
    half_life_hours: float = 24.0,
) -> dict[str, Any]:
    summary = " ".join(str(getattr(finding, 'summary', '') or '').split())
    source_kind = (str(getattr(finding, 'source_kind', '') or '').strip().lower() or 'other')
    timestamp = _coerce_utc_timestamp(getattr(finding, 'published_at', None) or getattr(finding, 'observed_at', None))
    source_url = getattr(finding, 'source_url', None)
    return {
        'stance': normalize_stance(summary),
        'freshness_score': score_freshness(
            finding,
            reference_time=reference_time,
            half_life_hours=half_life_hours,
        ),
        'source_kind': source_kind,
        'has_summary': bool(summary),
        'has_source_url': bool(source_url),
        'timestamp': _isoformat_z(timestamp),
        'summary_preview': _summary_preview(summary),
    }
