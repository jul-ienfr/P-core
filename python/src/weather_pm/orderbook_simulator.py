from __future__ import annotations

from typing import Any

from prediction_core.execution.orderbook_spend import (
    normalize_orderbook_asks,
    normalize_orderbook_bids,
    rust_compatible_orderbook_payload,
    simulate_orderbook_fill,
)

DEFAULT_SPEND_SIZES_USD = (5.0, 20.0, 50.0)


def simulate_spend_sizes(
    orderbook: dict[str, Any] | None,
    *,
    side: str,
    spend_sizes_usd: tuple[float, ...] | list[float] = DEFAULT_SPEND_SIZES_USD,
    probability_edge: float | None = None,
    strict_limit: float | None = None,
) -> dict[str, dict[str, Any]]:
    return {
        str(float(spend)): simulate_orderbook_fill(
            orderbook,
            side=side,
            spend_usd=float(spend),
            probability_edge=probability_edge,
            strict_limit=strict_limit,
        )
        for spend in spend_sizes_usd
    }


__all__ = [
    "DEFAULT_SPEND_SIZES_USD",
    "normalize_orderbook_asks",
    "normalize_orderbook_bids",
    "rust_compatible_orderbook_payload",
    "simulate_orderbook_fill",
    "simulate_spend_sizes",
]
