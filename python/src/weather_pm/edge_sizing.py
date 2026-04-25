from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(slots=True)
class EdgeSizing:
    prediction_probability: float
    market_price: float
    side: str
    raw_edge: float
    net_edge: float
    edge_bps: int
    net_edge_bps: int
    kelly_fraction: float
    suggested_fraction: float
    recommendation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def calculate_edge_sizing(
    *,
    prediction_probability: float,
    market_price: float,
    side: str = "buy",
    edge_cost_bps: float = 0.0,
    kelly_scale: float = 0.25,
    max_fraction: float = 0.02,
    min_net_edge: float = 0.015,
) -> EdgeSizing:
    prediction = _validate_probability("prediction_probability", prediction_probability)
    price = _validate_probability("market_price", market_price)
    resolved_side = _validate_side(side)
    cost_fraction = max(float(edge_cost_bps), 0.0) / 10000.0

    raw_edge = round(prediction - price, 4)
    directional_edge = raw_edge if resolved_side == "buy" else -raw_edge
    net_edge = round(directional_edge - cost_fraction, 4)

    kelly_fraction = _kelly_fraction(prediction=prediction, price=price, side=resolved_side)
    suggested_fraction = 0.0
    if net_edge >= min_net_edge:
        suggested_fraction = min(max(kelly_fraction, 0.0) * max(kelly_scale, 0.0), max(max_fraction, 0.0))

    recommendation = "skip"
    if suggested_fraction > 0.0:
        recommendation = resolved_side

    return EdgeSizing(
        prediction_probability=prediction,
        market_price=price,
        side=resolved_side,
        raw_edge=round(raw_edge, 4),
        net_edge=round(net_edge, 4),
        edge_bps=round(raw_edge * 10000),
        net_edge_bps=round(net_edge * 10000),
        kelly_fraction=round(kelly_fraction, 4),
        suggested_fraction=round(suggested_fraction, 4),
        recommendation=recommendation,
    )


def _kelly_fraction(*, prediction: float, price: float, side: str) -> float:
    if price <= 0.0 or price >= 1.0:
        return 0.0
    if side == "buy":
        b = (1.0 - price) / price
        p = prediction
    else:
        no_price = 1.0 - price
        if no_price <= 0.0 or no_price >= 1.0:
            return 0.0
        b = (1.0 - no_price) / no_price
        p = 1.0 - prediction
    q = 1.0 - p
    if b <= 0.0:
        return 0.0
    return max((b * p - q) / b, 0.0)


def _validate_probability(name: str, value: float) -> float:
    resolved = float(value)
    if resolved < 0.0 or resolved > 1.0:
        raise ValueError(f"{name} must be between 0 and 1")
    return resolved


def _validate_side(side: str) -> str:
    resolved = str(side).strip().lower() or "buy"
    if resolved not in {"buy", "sell"}:
        raise ValueError("side must be 'buy' or 'sell'")
    return resolved
