from __future__ import annotations

from dataclasses import asdict, dataclass
import importlib
import os
from typing import Any

RUST_ENTRY_POLICY_ENV = "PREDICTION_CORE_RUST_ORDERBOOK"


@dataclass(frozen=True, slots=True)
class EntryPolicy:
    name: str
    q_min: float
    q_max: float
    min_edge: float
    min_confidence: float
    max_spread: float
    min_depth_usd: float
    max_position_usd: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class EntryDecision:
    policy: str
    enter: bool
    action: str
    side: str
    market_price: float
    model_probability: float
    confidence: float
    edge_gross: float
    edge_net_all_in: float
    blocked_by: list[str]
    size_hint_usd: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_entry(
    *,
    policy: EntryPolicy,
    market_price: float,
    model_probability: float,
    confidence: float,
    spread: float,
    depth_usd: float,
    execution_cost_bps: float = 0.0,
    side: str = "yes",
) -> EntryDecision:
    if os.getenv(RUST_ENTRY_POLICY_ENV) == "1":
        try:
            return _evaluate_entry_with_rust(
                policy=policy,
                market_price=market_price,
                model_probability=model_probability,
                confidence=confidence,
                spread=spread,
                depth_usd=depth_usd,
                execution_cost_bps=execution_cost_bps,
                side=side,
            )
        except (ImportError, AttributeError):
            pass
    return _evaluate_entry_python(
        policy=policy,
        market_price=market_price,
        model_probability=model_probability,
        confidence=confidence,
        spread=spread,
        depth_usd=depth_usd,
        execution_cost_bps=execution_cost_bps,
        side=side,
    )


def _evaluate_entry_with_rust(
    *,
    policy: EntryPolicy,
    market_price: float,
    model_probability: float,
    confidence: float,
    spread: float,
    depth_usd: float,
    execution_cost_bps: float,
    side: str,
) -> EntryDecision:
    backend = importlib.import_module("prediction_core._rust_orderbook")
    payload = backend.evaluate_entry(
        policy_name=policy.name,
        q_min=policy.q_min,
        q_max=policy.q_max,
        min_edge=policy.min_edge,
        min_confidence=policy.min_confidence,
        max_spread=policy.max_spread,
        min_depth_usd=policy.min_depth_usd,
        max_position_usd=policy.max_position_usd,
        market_price=market_price,
        model_probability=model_probability,
        confidence=confidence,
        spread=spread,
        depth_usd=depth_usd,
        execution_cost_bps=execution_cost_bps,
        side=side,
    )
    if not isinstance(payload, dict):
        raise ValueError("rust entry decision payload must be an object")
    return EntryDecision(
        policy=str(payload["policy"]),
        enter=bool(payload["enter"]),
        action=str(payload["action"]),
        side=str(payload["side"]),
        market_price=float(payload["market_price"]),
        model_probability=float(payload["model_probability"]),
        confidence=float(payload["confidence"]),
        edge_gross=float(payload["edge_gross"]),
        edge_net_all_in=float(payload["edge_net_all_in"]),
        blocked_by=[str(reason) for reason in payload["blocked_by"]],
        size_hint_usd=float(payload["size_hint_usd"]),
    )


def _evaluate_entry_python(
    *,
    policy: EntryPolicy,
    market_price: float,
    model_probability: float,
    confidence: float,
    spread: float,
    depth_usd: float,
    execution_cost_bps: float = 0.0,
    side: str = "yes",
) -> EntryDecision:
    price = _probability("market_price", market_price)
    probability = _probability("model_probability", model_probability)
    resolved_confidence = _probability("confidence", confidence)
    resolved_side = _side(side)
    gross_edge = _edge(probability=probability, price=price, side=resolved_side)
    cost = max(float(execution_cost_bps), 0.0) / 10000.0
    net_edge = round(gross_edge - cost, 4)

    blocked_by: list[str] = []
    if price < policy.q_min or price > policy.q_max:
        blocked_by.append("price_outside_window")
    if gross_edge < policy.min_edge:
        blocked_by.append("edge_below_threshold")
    if resolved_confidence < policy.min_confidence:
        blocked_by.append("confidence_below_threshold")
    if float(spread) > policy.max_spread:
        blocked_by.append("spread_too_wide")
    if float(depth_usd) < policy.min_depth_usd:
        blocked_by.append("depth_insufficient")
    if net_edge <= 0.0 or net_edge < policy.min_edge:
        blocked_by.append("execution_cost_exceeds_edge")

    enter = not blocked_by
    return EntryDecision(
        policy=policy.name,
        enter=enter,
        action="paper_trade_small" if enter else "skip",
        side=resolved_side,
        market_price=round(price, 4),
        model_probability=round(probability, 4),
        confidence=round(resolved_confidence, 4),
        edge_gross=round(gross_edge, 4),
        edge_net_all_in=round(net_edge, 4),
        blocked_by=blocked_by,
        size_hint_usd=round(float(policy.max_position_usd), 4) if enter else 0.0,
    )


def _edge(*, probability: float, price: float, side: str) -> float:
    if side == "yes":
        return round(probability - price, 4)
    return round(price - probability, 4)


def _probability(name: str, value: float) -> float:
    resolved = float(value)
    if resolved < 0.0 or resolved > 1.0:
        raise ValueError(f"{name} must be between 0 and 1")
    return resolved


def _side(value: str) -> str:
    resolved = str(value).strip().lower() or "yes"
    aliases = {"buy": "yes", "y": "yes", "yes": "yes", "no": "no", "n": "no"}
    if resolved not in aliases:
        raise ValueError("side must be 'yes' or 'no'")
    return aliases[resolved]
