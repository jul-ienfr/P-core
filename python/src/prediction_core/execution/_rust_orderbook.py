from __future__ import annotations

import importlib
import math
import os
from collections.abc import Callable
from typing import Any

from prediction_core.execution.models import OrderBookSnapshot

RUST_ORDERBOOK_ENV = "PREDICTION_CORE_RUST_ORDERBOOK"


def rust_orderbook_enabled() -> bool:
    return os.getenv(RUST_ORDERBOOK_ENV) == "1"


def estimate_fill_with_optional_rust(
    *,
    book: OrderBookSnapshot,
    side: str,
    requested_quantity: float,
    fill_estimate_type: type,
    python_fallback: Callable[..., Any],
) -> Any:
    if not rust_orderbook_enabled() or side not in {"buy", "sell"} or not _book_is_safe_for_rust(book):
        return python_fallback(book=book, side=side, requested_quantity=requested_quantity)

    try:
        backend = importlib.import_module("prediction_core._rust_orderbook")
        payload = backend.estimate_fill_from_book(
            book=book,
            side=side,
            requested_quantity=requested_quantity,
        )
        return _fill_estimate_from_payload(payload, fill_estimate_type=fill_estimate_type, requested_quantity=requested_quantity)
    except Exception:
        return python_fallback(book=book, side=side, requested_quantity=requested_quantity)


def _book_to_payload(book: OrderBookSnapshot) -> dict[str, list[dict[str, float]]]:
    return {
        "bids": [{"price": float(level.price), "quantity": float(level.quantity)} for level in book.bids],
        "asks": [{"price": float(level.price), "quantity": float(level.quantity)} for level in book.asks],
    }


def _fill_estimate_from_payload(payload: Any, *, fill_estimate_type: type, requested_quantity: float) -> Any:
    if not isinstance(payload, dict):
        raise ValueError("rust orderbook estimate payload must be an object")
    return fill_estimate_type(
        requested_quantity=round(max(0.0, float(payload.get("requested_quantity", requested_quantity))), 6),
        filled_quantity=round(max(0.0, float(payload["filled_quantity"])), 6),
        unfilled_quantity=round(max(0.0, float(payload["unfilled_quantity"])), 6),
        gross_notional=round(max(0.0, float(payload["gross_notional"])), 6),
        average_price=_optional_float(payload.get("average_price")),
        top_of_book_price=_optional_float(payload.get("top_of_book_price")),
        slippage_cost=round(max(0.0, float(payload["slippage_cost"])), 6),
        slippage_bps=round(max(0.0, float(payload["slippage_bps"])), 2),
        levels_consumed=max(0, int(payload["levels_consumed"])),
    )


def _book_is_safe_for_rust(book: OrderBookSnapshot) -> bool:
    return all(_level_is_safe_for_rust(level.price, level.quantity) for level in [*book.bids, *book.asks])


def _level_is_safe_for_rust(price: float, quantity: float) -> bool:
    try:
        price_value = float(price)
        quantity_value = float(quantity)
    except (TypeError, ValueError):
        return False
    return math.isfinite(price_value) and 0.0 < price_value <= 1.0 and math.isfinite(quantity_value) and quantity_value > 0.0


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    result = float(value)
    return round(result, 6)
