from __future__ import annotations

from collections import defaultdict
from typing import Any


def detect_surface_inconsistencies(
    *,
    exact_bins: list[dict[str, Any]],
    thresholds: list[dict[str, Any]],
    exact_mass_tolerance: float = 1.0,
) -> list[dict[str, Any]]:
    """Detect cross-market weather surface inconsistencies.

    The detector intentionally uses simple, deterministic rules suitable for fixture-backed
    production contracts: threshold monotonicity, exact-bin mass, neighbor spikes, and
    explicit YES/NO side inversion from quoted side prices.
    """
    findings: list[dict[str, Any]] = []
    findings.extend(_threshold_inconsistencies(thresholds))
    findings.extend(_exact_bin_mass_anomalies(exact_bins, exact_mass_tolerance=exact_mass_tolerance))
    findings.extend(_neighboring_exact_bin_mispricing(exact_bins))
    findings.extend(_side_specific_inversions([*exact_bins, *thresholds]))
    return findings


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
    candidate_market = higher if direction == "higher" else lower
    return {
        "type": "threshold_monotonicity_violation",
        "direction": direction,
        "lower_market_id": str(lower.get("id") or ""),
        "higher_market_id": str(higher.get("id") or ""),
        "market_id": str(candidate_market.get("id") or ""),
        "lower_target": lower_target,
        "higher_target": higher_target,
        "lower_price": lower_price,
        "higher_price": higher_price,
        "candidate_side": "YES",
        "raw_edge_reason": "threshold_monotonicity_violation",
        "severity": round(abs(higher_price - lower_price), 2),
    }


def _exact_bin_mass_anomalies(exact_bins: list[dict[str, Any]], *, exact_mass_tolerance: float) -> list[dict[str, Any]]:
    if not exact_bins:
        return []
    exact_mass = round(sum(_price(market) for market in exact_bins), 2)
    if exact_mass > exact_mass_tolerance:
        return [
            {
                "type": "exact_bin_mass_overround",
                "price_mass": exact_mass,
                "tolerance": float(exact_mass_tolerance),
                "candidate_side": "NO",
                "raw_edge_reason": "exact-bin YES price mass exceeds 100%",
                "severity": round(exact_mass - exact_mass_tolerance, 2),
            }
        ]
    # A sparse exact-bin surface far below 100% can imply missing/cheap YES mass.
    underround_floor = max(0.0, exact_mass_tolerance - 0.50)
    if len(exact_bins) >= 3 and exact_mass < underround_floor:
        return [
            {
                "type": "exact_bin_mass_underround",
                "price_mass": exact_mass,
                "tolerance": float(exact_mass_tolerance),
                "candidate_side": "YES",
                "raw_edge_reason": "exact-bin YES price mass is materially below 100%",
                "severity": round(exact_mass_tolerance - exact_mass, 2),
            }
        ]
    return []


def _neighboring_exact_bin_mispricing(exact_bins: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    sorted_bins = sorted(exact_bins, key=lambda market: float(market["structure"].target_value or 0.0))
    for left, middle, right in zip(sorted_bins, sorted_bins[1:], sorted_bins[2:]):
        left_target = float(left["structure"].target_value or 0.0)
        middle_target = float(middle["structure"].target_value or 0.0)
        right_target = float(right["structure"].target_value or 0.0)
        if round(middle_target - left_target, 6) != round(right_target - middle_target, 6):
            continue
        neighbor_avg = round((_price(left) + _price(right)) / 2.0, 4)
        middle_price = _price(middle)
        severity = round(middle_price - neighbor_avg, 2)
        if severity >= 0.20:
            findings.append(
                {
                    "type": "neighboring_exact_bin_mispricing",
                    "market_id": str(middle.get("id") or ""),
                    "target": middle_target,
                    "yes_price": middle_price,
                    "neighbor_avg_yes_price": neighbor_avg,
                    "candidate_side": "NO",
                    "raw_edge_reason": "middle exact-bin YES price is rich versus neighbor exact-bin prices",
                    "severity": severity,
                }
            )
    return findings


def _side_specific_inversions(markets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for market in markets:
        if market.get("no_price") is None:
            continue
        yes_price = _price(market)
        no_price = _no_price(market)
        yes_complement = round(1.0 - no_price, 2)
        no_complement = round(1.0 - yes_price, 2)
        if no_price < no_complement - 0.05:
            findings.append(
                {
                    "type": "side_specific_yes_no_inversion",
                    "market_id": str(market.get("id") or ""),
                    "yes_price": yes_price,
                    "no_price": no_price,
                    "candidate_side": "NO",
                    "raw_edge_reason": "NO ask is below the YES-implied complement",
                    "severity": round(no_complement - no_price, 2),
                }
            )
        elif yes_price < yes_complement - 0.05:
            findings.append(
                {
                    "type": "side_specific_yes_no_inversion",
                    "market_id": str(market.get("id") or ""),
                    "yes_price": yes_price,
                    "no_price": no_price,
                    "candidate_side": "YES",
                    "raw_edge_reason": "YES ask is below the NO-implied complement",
                    "severity": round(yes_complement - yes_price, 2),
                }
            )
    return findings


def _price(market: dict[str, Any]) -> float:
    return round(float(market.get("yes_price") or 0.0), 2)


def _no_price(market: dict[str, Any]) -> float:
    if market.get("no_price") is not None:
        return round(float(market.get("no_price") or 0.0), 2)
    return round(1.0 - _price(market), 2)
