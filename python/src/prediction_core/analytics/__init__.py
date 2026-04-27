"""Analytics domain for prediction_core Python research stack."""

from .entities import canonicalize_entity_type
from .events import (
    DebugDecisionEvent,
    PaperOrderEvent,
    PaperPositionEvent,
    ProfileDecisionEvent,
    ProfileMetricEvent,
    StrategyMetricEvent,
    serialize_event,
)
from .metrics import build_profile_metric_events, build_strategy_metric_events
from .scoring import build_finding_analytics, clamp_score, normalize_stance, score_freshness
from .text import chunk_text, extract_key_sentences
from .trade_density import TradeDensity, TradeDensitySummary, summarize_trade_density

__all__ = [
    "DebugDecisionEvent",
    "PaperOrderEvent",
    "PaperPositionEvent",
    "ProfileDecisionEvent",
    "ProfileMetricEvent",
    "StrategyMetricEvent",
    "TradeDensity",
    "TradeDensitySummary",
    "build_finding_analytics",
    "build_profile_metric_events",
    "build_strategy_metric_events",
    "canonicalize_entity_type",
    "chunk_text",
    "clamp_score",
    "extract_key_sentences",
    "normalize_stance",
    "score_freshness",
    "serialize_event",
    "summarize_trade_density",
]
