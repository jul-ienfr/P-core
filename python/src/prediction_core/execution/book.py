from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from prediction_core.execution._rust_orderbook import estimate_fill_with_optional_rust
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
    requested_quantity: float = 0.0
    levels_consumed: int = 0

    @property
    def notional(self) -> float:
        return self.gross_notional

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def estimate_fill_from_book(*, book: OrderBookSnapshot, side: BookSide, requested_quantity: float) -> FillEstimate:
    return estimate_fill_with_optional_rust(
        book=book,
        side=side,
        requested_quantity=requested_quantity,
        fill_estimate_type=FillEstimate,
        python_fallback=_estimate_fill_from_book_python,
    )


def _estimate_fill_from_book_python(*, book: OrderBookSnapshot, side: BookSide, requested_quantity: float) -> FillEstimate:
    quantity = max(0.0, float(requested_quantity))
    if side not in ("buy", "sell"):
        return _empty_fill(quantity)

    levels = _sorted_levels(book=book, side=side)
    top_of_book_price = _top_of_book_price(book=book, side=side)

    remaining = quantity
    gross_notional = 0.0
    filled_quantity = 0.0
    levels_consumed = 0

    for level in levels:
        if remaining <= 0:
            break
        take_quantity = min(remaining, max(0.0, float(level.quantity)))
        if take_quantity <= 0:
            continue
        gross_notional += take_quantity * float(level.price)
        filled_quantity += take_quantity
        remaining -= take_quantity
        levels_consumed += 1

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
        requested_quantity=quantity,
        filled_quantity=round(filled_quantity, 6),
        unfilled_quantity=round(max(0.0, quantity - filled_quantity), 6),
        gross_notional=round(gross_notional, 6),
        average_price=average_price,
        top_of_book_price=top_of_book_price,
        slippage_cost=slippage_cost,
        slippage_bps=slippage_bps,
        levels_consumed=levels_consumed,
    )


def estimate_fill(*, book: OrderBookSnapshot, side: str, requested_quantity: float) -> FillEstimate:
    return estimate_fill_from_book(book=book, side=side, requested_quantity=requested_quantity)


def _empty_fill(requested_quantity: float) -> FillEstimate:
    return FillEstimate(
        requested_quantity=round(max(0.0, float(requested_quantity)), 6),
        filled_quantity=0.0,
        unfilled_quantity=round(max(0.0, float(requested_quantity)), 6),
        gross_notional=0.0,
        average_price=None,
        top_of_book_price=None,
        slippage_cost=0.0,
        slippage_bps=0.0,
        levels_consumed=0,
    )


def _sorted_levels(*, book: OrderBookSnapshot, side: BookSide) -> list[BookLevel]:
    levels = book.asks if side == "buy" else book.bids
    reverse = side == "sell"
    return sorted(levels, key=lambda level: level.price, reverse=reverse)


def _top_of_book_price(*, book: OrderBookSnapshot, side: BookSide) -> float | None:
    if side == "buy":
        return book.best_ask
    return book.best_bid
