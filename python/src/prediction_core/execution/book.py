from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from prediction_core.execution.models import BookLevel, OrderBookSnapshot

BookSide = Literal["buy", "sell"]


@dataclass(slots=True)
class FillEstimate:
    filled_quantity: float
    unfilled_quantity: float
    gross_notional: float
    average_price: float | None
    top_of_book_price: float | None
    slippage_cost: float
    slippage_bps: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def estimate_fill_from_book(*, book: OrderBookSnapshot, side: BookSide, requested_quantity: float) -> FillEstimate:
    quantity = max(0.0, float(requested_quantity))
    levels = _sorted_levels(book=book, side=side)
    top_of_book_price = _top_of_book_price(book=book, side=side)

    remaining = quantity
    gross_notional = 0.0
    filled_quantity = 0.0

    for level in levels:
        if remaining <= 0:
            break
        take_quantity = min(remaining, max(0.0, float(level.quantity)))
        if take_quantity <= 0:
            continue
        gross_notional += take_quantity * float(level.price)
        filled_quantity += take_quantity
        remaining -= take_quantity

    average_price = None
    slippage_cost = 0.0
    slippage_bps = 0.0
    if filled_quantity > 0:
        average_price = round(gross_notional / filled_quantity, 6)
        if top_of_book_price is not None:
            reference_notional = top_of_book_price * filled_quantity
            if side == "buy":
                slippage_cost = gross_notional - reference_notional
            else:
                slippage_cost = reference_notional - gross_notional
            slippage_cost = round(max(0.0, slippage_cost), 6)
            if reference_notional > 0:
                slippage_bps = round((slippage_cost / reference_notional) * 10000.0, 2)

    return FillEstimate(
        filled_quantity=round(filled_quantity, 6),
        unfilled_quantity=round(max(0.0, quantity - filled_quantity), 6),
        gross_notional=round(gross_notional, 6),
        average_price=average_price,
        top_of_book_price=top_of_book_price,
        slippage_cost=slippage_cost,
        slippage_bps=slippage_bps,
    )


def _sorted_levels(*, book: OrderBookSnapshot, side: BookSide) -> list[BookLevel]:
    levels = book.asks if side == "buy" else book.bids
    reverse = side == "sell"
    return sorted(levels, key=lambda level: level.price, reverse=reverse)


def _top_of_book_price(*, book: OrderBookSnapshot, side: BookSide) -> float | None:
    if side == "buy":
        return book.best_ask
    return book.best_bid
