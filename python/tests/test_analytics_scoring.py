from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from datetime import datetime, timezone

from prediction_core.analytics import build_finding_analytics, clamp_score, normalize_stance, score_freshness


class _Finding:
    def __init__(self, *, source_kind: str, summary: str = "", source_url: str | None = None, published_at=None, observed_at=None):
        self.source_kind = source_kind
        self.summary = summary
        self.source_url = source_url
        self.published_at = published_at
        self.observed_at = observed_at


def test_clamp_score_bounds_values_inside_closed_interval() -> None:
    assert clamp_score(-0.2) == 0.0
    assert clamp_score(0.42) == 0.42
    assert clamp_score(1.5) == 1.0


def test_normalize_stance_maps_common_aliases() -> None:
    assert normalize_stance("bullish") == "bullish"
    assert normalize_stance("likely yes") == "bullish"
    assert normalize_stance("short") == "bearish"
    assert normalize_stance("mixed") == "neutral"
    assert normalize_stance(None) == "neutral"


def test_score_freshness_combines_recency_and_source_bonuses() -> None:
    finding = _Finding(source_kind="official", summary="Fresh update", source_url="https://example.com")
    score = score_freshness(finding)
    assert score == pytest.approx(0.68)
    assert math.isfinite(score)


def test_build_finding_analytics_returns_canonical_payload() -> None:
    published_at = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    reference_time = datetime(2026, 1, 1, 18, 0, tzinfo=timezone.utc)
    finding = _Finding(
        source_kind="official",
        summary="  Agency now leans likely yes on approval.  ",
        source_url="https://example.com/report",
        published_at=published_at,
    )

    payload = build_finding_analytics(finding, reference_time=reference_time, half_life_hours=12.0)

    assert payload == {
        "stance": "bullish",
        "freshness_score": pytest.approx(0.7365306597),
        "source_kind": "official",
        "has_summary": True,
        "has_source_url": True,
        "timestamp": "2026-01-01T12:00:00Z",
        "summary_preview": "Agency now leans likely yes on approval.",
    }


def test_build_finding_analytics_prefers_observed_time_and_defaults_missing_fields() -> None:
    observed_at = datetime(2026, 1, 2, 9, 30, tzinfo=timezone.utc)
    payload = build_finding_analytics(
        _Finding(source_kind="", summary="   ", observed_at=observed_at),
        reference_time=observed_at,
    )

    assert payload == {
        "stance": "neutral",
        "freshness_score": pytest.approx(1.0),
        "source_kind": "other",
        "has_summary": False,
        "has_source_url": False,
        "timestamp": "2026-01-02T09:30:00Z",
        "summary_preview": "",
    }


def test_build_finding_analytics_truncates_preview_to_small_canonical_window() -> None:
    finding = _Finding(
        source_kind="news",
        summary="x" * 90,
        source_url="https://example.com/story",
    )

    payload = build_finding_analytics(finding)

    assert payload["summary_preview"] == ("x" * 77) + "..."
    assert len(payload["summary_preview"]) == 80
