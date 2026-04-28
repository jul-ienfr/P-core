from __future__ import annotations

import importlib.util
import sys
import types

from prediction_core.execution._rust_orderbook import estimate_fill_with_optional_rust, rust_orderbook_enabled
from prediction_core.execution.book import FillEstimate
from prediction_core.execution.models import BookLevel, OrderBookSnapshot


def _book() -> OrderBookSnapshot:
    return OrderBookSnapshot(
        bids=[BookLevel(price=0.42, quantity=12.0), BookLevel(price=0.41, quantity=10.0)],
        asks=[BookLevel(price=0.45, quantity=10.0), BookLevel(price=0.46, quantity=15.0)],
    )


def _fallback(*, book: OrderBookSnapshot, side: str, requested_quantity: float) -> FillEstimate:
    return FillEstimate(
        requested_quantity=requested_quantity,
        filled_quantity=1.0,
        unfilled_quantity=0.0,
        gross_notional=0.45,
        average_price=0.45,
        top_of_book_price=0.45,
        slippage_cost=0.0,
        slippage_bps=0.0,
        levels_consumed=1,
    )


def test_rust_orderbook_enabled_requires_exact_flag(monkeypatch) -> None:
    monkeypatch.delenv("PREDICTION_CORE_RUST_ORDERBOOK", raising=False)
    assert rust_orderbook_enabled() is False

    monkeypatch.setenv("PREDICTION_CORE_RUST_ORDERBOOK", "0")
    assert rust_orderbook_enabled() is False

    monkeypatch.setenv("PREDICTION_CORE_RUST_ORDERBOOK", "1")
    assert rust_orderbook_enabled() is True


def test_optional_rust_uses_fallback_when_flag_is_disabled(monkeypatch) -> None:
    monkeypatch.delenv("PREDICTION_CORE_RUST_ORDERBOOK", raising=False)

    result = estimate_fill_with_optional_rust(
        book=_book(),
        side="buy",
        requested_quantity=20.0,
        fill_estimate_type=FillEstimate,
        python_fallback=_fallback,
    )

    assert result.filled_quantity == 1.0
    assert result.gross_notional == 0.45


def test_optional_rust_falls_back_when_native_module_is_missing(monkeypatch) -> None:
    monkeypatch.setenv("PREDICTION_CORE_RUST_ORDERBOOK", "1")

    def import_missing(name: str):
        raise ModuleNotFoundError(name)

    monkeypatch.setattr("prediction_core.execution._rust_orderbook.importlib.import_module", import_missing)

    result = estimate_fill_with_optional_rust(
        book=_book(),
        side="buy",
        requested_quantity=20.0,
        fill_estimate_type=FillEstimate,
        python_fallback=_fallback,
    )

    assert result.filled_quantity == 1.0
    assert result.gross_notional == 0.45


def test_optional_rust_converts_native_payload_to_python_fill_estimate(monkeypatch) -> None:
    monkeypatch.setenv("PREDICTION_CORE_RUST_ORDERBOOK", "1")
    fake_module = types.ModuleType("prediction_core._rust_orderbook")

    def estimate_fill_from_book(*, book, side, requested_quantity):
        assert side == "buy"
        assert requested_quantity == 20.0
        assert [level.to_dict() for level in book.asks] == [{"price": 0.45, "quantity": 10.0}, {"price": 0.46, "quantity": 15.0}]
        return {
            "requested_quantity": 20.0,
            "filled_quantity": 20.0,
            "unfilled_quantity": 0.0,
            "gross_notional": 9.1,
            "average_price": 0.455,
            "top_of_book_price": 0.45,
            "slippage_cost": 0.1,
            "slippage_bps": 111.11,
            "levels_consumed": 2,
            "status": "filled",
        }

    fake_module.estimate_fill_from_book = estimate_fill_from_book
    monkeypatch.setitem(sys.modules, "prediction_core._rust_orderbook", fake_module)

    result = estimate_fill_with_optional_rust(
        book=_book(),
        side="buy",
        requested_quantity=20.0,
        fill_estimate_type=FillEstimate,
        python_fallback=_fallback,
    )

    assert isinstance(result, FillEstimate)
    assert result.to_dict() == {
        "filled_quantity": 20.0,
        "unfilled_quantity": 0.0,
        "gross_notional": 9.1,
        "average_price": 0.455,
        "top_of_book_price": 0.45,
        "slippage_cost": 0.1,
        "slippage_bps": 111.11,
        "requested_quantity": 20.0,
        "levels_consumed": 2,
    }


def test_native_orderbook_module_matches_python_estimate_when_installed(monkeypatch) -> None:
    if importlib.util.find_spec("prediction_core._rust_orderbook") is None:
        return
    monkeypatch.setenv("PREDICTION_CORE_RUST_ORDERBOOK", "1")

    result = estimate_fill_with_optional_rust(
        book=_book(),
        side="buy",
        requested_quantity=20.0,
        fill_estimate_type=FillEstimate,
        python_fallback=_fallback,
    )

    assert result.to_dict() == {
        "filled_quantity": 20.0,
        "unfilled_quantity": 0.0,
        "gross_notional": 9.1,
        "average_price": 0.455,
        "top_of_book_price": 0.45,
        "slippage_cost": 0.1,
        "slippage_bps": 111.11,
        "requested_quantity": 20.0,
        "levels_consumed": 2,
    }


def test_optional_rust_falls_back_for_invalid_book_even_when_flag_enabled(monkeypatch) -> None:
    monkeypatch.setenv("PREDICTION_CORE_RUST_ORDERBOOK", "1")
    fake_module = types.ModuleType("prediction_core._rust_orderbook")

    def estimate_fill_from_book(*, book, side, requested_quantity):
        raise AssertionError("unsafe books must not call native backend")

    fake_module.estimate_fill_from_book = estimate_fill_from_book
    monkeypatch.setitem(sys.modules, "prediction_core._rust_orderbook", fake_module)

    result = estimate_fill_with_optional_rust(
        book=OrderBookSnapshot(bids=[], asks=[BookLevel(price=1.2, quantity=10.0)]),
        side="buy",
        requested_quantity=20.0,
        fill_estimate_type=FillEstimate,
        python_fallback=_fallback,
    )

    assert result.filled_quantity == 1.0
