from __future__ import annotations

from weather_pm.market_parser import parse_market_question
from weather_pm.neighbor_context import build_neighbor_context
from weather_pm.polymarket_client import list_fixture_weather_markets


def test_build_neighbor_context_detects_related_markets_for_threshold_market() -> None:
    structure = parse_market_question("Will the highest temperature in Denver be 64F or higher?")
    context = build_neighbor_context(structure, list_fixture_weather_markets())

    assert context.neighbor_market_count >= 2
    assert context.neighbor_inconsistency > 0.0
    assert context.threshold_bin_inconsistency > 0.0


def test_build_neighbor_context_is_lower_for_unmatched_city() -> None:
    structure = parse_market_question("Will the highest temperature in NYC be 64F or higher?")
    context = build_neighbor_context(structure, list_fixture_weather_markets())

    assert context.neighbor_market_count == 0
    assert context.neighbor_inconsistency == 0.0
    assert context.threshold_bin_inconsistency == 0.0
