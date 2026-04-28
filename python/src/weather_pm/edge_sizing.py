from __future__ import annotations

from dataclasses import asdict, dataclass
import importlib
import math
import os
from typing import Any


RUST_EDGE_SIZING_ENV = "PREDICTION_CORE_RUST_ORDERBOOK"


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
    if _rust_edge_sizing_enabled():
        try:
            return _calculate_edge_sizing_with_rust(
                prediction_probability=prediction_probability,
                market_price=market_price,
                side=side,
                edge_cost_bps=edge_cost_bps,
                kelly_scale=kelly_scale,
                max_fraction=max_fraction,
                min_net_edge=min_net_edge,
            )
        except (ImportError, AttributeError):
            pass
    return _calculate_edge_sizing_python(
        prediction_probability=prediction_probability,
        market_price=market_price,
        side=side,
        edge_cost_bps=edge_cost_bps,
        kelly_scale=kelly_scale,
        max_fraction=max_fraction,
        min_net_edge=min_net_edge,
    )


def _calculate_edge_sizing_python(
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
    cost_bps = _validate_finite("edge_cost_bps", edge_cost_bps)
    scale = _validate_finite("kelly_scale", kelly_scale)
    fraction_cap = _validate_finite("max_fraction", max_fraction)
    minimum_edge = _validate_finite("min_net_edge", min_net_edge)
    cost_fraction = max(cost_bps, 0.0) / 10000.0

    raw_edge = round(prediction - price, 4)
    directional_edge = raw_edge if resolved_side == "buy" else -raw_edge
    net_edge = round(directional_edge - cost_fraction, 4)

    kelly_fraction = _kelly_fraction(prediction=prediction, price=price, side=resolved_side)
    suggested_fraction = 0.0
    if net_edge >= minimum_edge:
        suggested_fraction = min(max(kelly_fraction, 0.0) * max(scale, 0.0), max(fraction_cap, 0.0))

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


def _calculate_edge_sizing_with_rust(
    *,
    prediction_probability: float,
    market_price: float,
    side: str,
    edge_cost_bps: float,
    kelly_scale: float,
    max_fraction: float,
    min_net_edge: float,
) -> EdgeSizing:
    backend = importlib.import_module("prediction_core._rust_orderbook")
    payload = backend.calculate_edge_sizing(
        prediction_probability=prediction_probability,
        market_price=market_price,
        side=side,
        edge_cost_bps=edge_cost_bps,
        kelly_scale=kelly_scale,
        max_fraction=max_fraction,
        min_net_edge=min_net_edge,
    )
    if not isinstance(payload, dict):
        raise ValueError("rust edge sizing payload must be an object")
    return EdgeSizing(
        prediction_probability=float(payload["prediction_probability"]),
        market_price=float(payload["market_price"]),
        side=str(payload["side"]),
        raw_edge=float(payload["raw_edge"]),
        net_edge=float(payload["net_edge"]),
        edge_bps=int(payload["edge_bps"]),
        net_edge_bps=int(payload["net_edge_bps"]),
        kelly_fraction=float(payload["kelly_fraction"]),
        suggested_fraction=float(payload["suggested_fraction"]),
        recommendation=str(payload["recommendation"]),
    )


def _rust_edge_sizing_enabled() -> bool:
    return os.getenv(RUST_EDGE_SIZING_ENV) == "1"


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
    resolved = _validate_finite(name, value)
    if resolved < 0.0 or resolved > 1.0:
        raise ValueError(f"{name} must be between 0 and 1")
    return resolved


def _validate_finite(name: str, value: float) -> float:
    resolved = float(value)
    if not math.isfinite(resolved):
        raise ValueError(f"{name} must be finite")
    return resolved


def _validate_side(side: str) -> str:
    resolved = str(side).strip().lower() or "buy"
    if resolved not in {"buy", "sell"}:
        raise ValueError("side must be 'buy' or 'sell'")
    return resolved
