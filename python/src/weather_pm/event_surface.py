from __future__ import annotations

from collections import defaultdict
from typing import Any

from weather_pm.market_parser import parse_market_question


def build_weather_event_surface(markets: list[dict[str, Any]], *, exact_mass_tolerance: float = 1.0) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for market in markets:
        question = str(market.get("question") or "")
        try:
            structure = parse_market_question(question)
        except ValueError:
            continue
        if not structure.date_local:
            continue
        enriched = dict(market)
        enriched["structure"] = structure
        grouped[_event_key(structure)].append(enriched)

    events = [_build_event(key, group, exact_mass_tolerance=exact_mass_tolerance) for key, group in grouped.items()]
    events.sort(key=lambda event: (-len(event["inconsistencies"]), -event["market_count"], event["event_key"]))
    return {"event_count": len(events), "events": events}


def _build_event(event_key: str, markets: list[dict[str, Any]], *, exact_mass_tolerance: float) -> dict[str, Any]:
    exact_bins = [market for market in markets if market["structure"].is_exact_bin]
    thresholds = [market for market in markets if market["structure"].is_threshold]
    inconsistencies = []
    inconsistencies.extend(_threshold_inconsistencies(thresholds))
    exact_mass = round(sum(_price(market) for market in exact_bins), 2)
    if exact_bins and exact_mass > exact_mass_tolerance:
        inconsistencies.append(
            {
                "type": "exact_bin_mass_overround",
                "price_mass": exact_mass,
                "tolerance": float(exact_mass_tolerance),
                "severity": round(exact_mass - exact_mass_tolerance, 2),
            }
        )
    return {
        "event_key": event_key,
        "market_count": len(markets),
        "exact_bin_count": len(exact_bins),
        "threshold_count": len(thresholds),
        "exact_bin_price_mass": exact_mass,
        "inconsistencies": inconsistencies,
        "markets": [_market_payload(market) for market in markets],
    }


def _threshold_inconsistencies(thresholds: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    by_direction: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for market in thresholds:
        direction = market["structure"].threshold_direction or "unknown"
        by_direction[direction].append(market)

    for direction, items in by_direction.items():
        sorted_items = sorted(items, key=lambda market: float(market["structure"].target_value or 0.0))
        for lower, higher in zip(sorted_items, sorted_items[1:]):
            lower_price = _price(lower)
            higher_price = _price(higher)
            lower_target = float(lower["structure"].target_value or 0.0)
            higher_target = float(higher["structure"].target_value or 0.0)
            if direction == "higher" and higher_price > lower_price:
                findings.append(_threshold_violation(direction, lower, higher, lower_target, higher_target, lower_price, higher_price))
            if direction == "below" and lower_price > higher_price:
                findings.append(_threshold_violation(direction, lower, higher, lower_target, higher_target, lower_price, higher_price))
    return findings


def _threshold_violation(
    direction: str,
    lower: dict[str, Any],
    higher: dict[str, Any],
    lower_target: float,
    higher_target: float,
    lower_price: float,
    higher_price: float,
) -> dict[str, Any]:
    return {
        "type": "threshold_monotonicity_violation",
        "direction": direction,
        "lower_market_id": str(lower.get("id") or ""),
        "higher_market_id": str(higher.get("id") or ""),
        "lower_target": lower_target,
        "higher_target": higher_target,
        "lower_price": lower_price,
        "higher_price": higher_price,
        "severity": round(abs(higher_price - lower_price), 2),
    }


def _event_key(structure: Any) -> str:
    return f"{structure.city}|{structure.measurement_kind}|{structure.unit}|{structure.date_local}"


def _price(market: dict[str, Any]) -> float:
    return round(float(market.get("yes_price") or 0.0), 2)


def _market_payload(market: dict[str, Any]) -> dict[str, Any]:
    structure = market["structure"]
    return {
        "id": str(market.get("id") or ""),
        "question": str(market.get("question") or ""),
        "yes_price": _price(market),
        "market_type": "threshold" if structure.is_threshold else "exact_bin" if structure.is_exact_bin else "other",
        "target": structure.target_value,
        "range_low": structure.range_low,
        "range_high": structure.range_high,
        "threshold_direction": structure.threshold_direction,
    }
