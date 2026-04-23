from __future__ import annotations

from typing import Any

from weather_pm.market_parser import parse_market_question
from weather_pm.models import MarketStructure, NeighborContext


def build_neighbor_context(structure: MarketStructure, markets: list[dict[str, Any]]) -> NeighborContext:
    related: list[tuple[dict[str, Any], MarketStructure]] = []
    for market in markets:
        question = str(market.get("question", ""))
        try:
            other = parse_market_question(question)
        except ValueError:
            continue
        if other.city.lower() != structure.city.lower():
            continue
        if other.measurement_kind != structure.measurement_kind:
            continue
        if question.strip().lower() == _question_key(structure):
            continue
        related.append((market, other))

    neighbor_inconsistency = _neighbor_inconsistency(structure, related)
    threshold_bin_inconsistency = _threshold_bin_inconsistency(structure, related)
    return NeighborContext(
        neighbor_market_count=len(related),
        neighbor_inconsistency=neighbor_inconsistency,
        threshold_bin_inconsistency=threshold_bin_inconsistency,
    )


def _neighbor_inconsistency(structure: MarketStructure, related: list[tuple[dict[str, Any], MarketStructure]]) -> float:
    if not related:
        return 0.0
    target = _anchor_value(structure)
    if target is None:
        return 0.0

    score = 0.0
    for market, other in related:
        other_target = _anchor_value(other)
        if other_target is None:
            continue
        yes_price = float(market.get("yes_price", 0.0))
        if other.is_threshold and _is_same_or_more_extreme_threshold(other, structure, other_target, target) and yes_price > 0.55:
            score += 0.35
        elif other.is_exact_bin and abs(other_target - target) <= 1.0 and yes_price > 0.10:
            score += 0.25
    return round(min(score, 1.0), 2)


def _threshold_bin_inconsistency(structure: MarketStructure, related: list[tuple[dict[str, Any], MarketStructure]]) -> float:
    target = _anchor_value(structure)
    if target is None:
        return 0.0

    has_threshold = structure.is_threshold
    has_bin = structure.is_exact_bin
    score = 0.0
    for market, other in related:
        other_target = _anchor_value(other)
        if other_target is None:
            continue
        if other.is_threshold and abs(other_target - target) <= 1.0:
            has_threshold = True
        if other.is_exact_bin and abs(other_target - target) <= 1.0:
            has_bin = True
            if float(market.get("yes_price", 0.0)) > 0.10:
                score += 0.4
    if has_threshold and has_bin:
        score = max(score, 0.4)
    return round(min(score, 1.0), 2)


def _anchor_value(structure: MarketStructure) -> float | None:
    if structure.target_value is not None:
        return structure.target_value
    if structure.range_low is not None and structure.range_high is not None:
        return (structure.range_low + structure.range_high) / 2
    return None


def _is_same_or_more_extreme_threshold(
    other: MarketStructure,
    structure: MarketStructure,
    other_target: float,
    target: float,
) -> bool:
    if other.threshold_direction != structure.threshold_direction:
        return False
    if structure.threshold_direction == "below":
        return other_target <= target
    return other_target >= target


def _question_key(structure: MarketStructure) -> str:
    if structure.is_threshold and structure.target_value is not None:
        direction = structure.threshold_direction or "higher"
        return f"will the {'highest' if structure.measurement_kind == 'high' else 'lowest'} temperature in {structure.city.lower()} be {int(structure.target_value) if structure.target_value.is_integer() else structure.target_value}{structure.unit.upper()} or {direction}?"
    if structure.is_exact_bin and structure.range_low is not None and structure.range_high is not None:
        low = int(structure.range_low) if structure.range_low.is_integer() else structure.range_low
        high = int(structure.range_high) if structure.range_high.is_integer() else structure.range_high
        if structure.target_value is not None and structure.range_low == structure.range_high:
            return f"will the {'highest' if structure.measurement_kind == 'high' else 'lowest'} temperature in {structure.city.lower()} be exactly {low}{structure.unit.upper()}?"
        return f"will the {'highest' if structure.measurement_kind == 'high' else 'lowest'} temperature in {structure.city.lower()} be between {low}{structure.unit.upper()} and {high}{structure.unit.upper()}?"
    return ""
