from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from prediction_core.execution.book import estimate_fill_from_book
from prediction_core.execution.models import BookLevel, OrderBookSnapshot
from weather_pm.orderbook_simulator import simulate_orderbook_fill


FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "orderbook_fill_parity.json"


def _fixture() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text())


def _snapshot(payload: dict[str, Any]) -> OrderBookSnapshot:
    book = payload["book"]
    return OrderBookSnapshot(
        bids=[BookLevel(price=level["price"], quantity=level["quantity"]) for level in book["bids"]],
        asks=[BookLevel(price=level["price"], quantity=level["quantity"]) for level in book["asks"]],
    )


def test_orderbook_fill_parity_fixture_shape() -> None:
    payload = _fixture()

    assert payload["case_id"] == "minimal_orderbook_fill_parity_v1"
    assert payload["book"]["bids"]
    assert payload["book"]["asks"]
    assert payload["polymarket_orderbook"]["no_asks"]
    assert payload["polymarket_orderbook"]["no_bids"]
    assert payload["requests"]["quantity"] > 0
    assert payload["requests"]["spend_usdc"] > 0


def test_execution_book_matches_parity_fixture() -> None:
    payload = _fixture()
    snapshot = _snapshot(payload)
    quantity = payload["requests"]["quantity"]

    buy = estimate_fill_from_book(book=snapshot, side="buy", requested_quantity=quantity).to_dict()
    sell = estimate_fill_from_book(book=snapshot, side="sell", requested_quantity=quantity).to_dict()

    assert buy == payload["expected"]["estimate_buy"]
    assert sell == payload["expected"]["estimate_sell"]


def test_weather_spend_fill_matches_parity_fixture() -> None:
    payload = _fixture()

    result = simulate_orderbook_fill(
        payload["polymarket_orderbook"],
        side="NO",
        spend_usd=payload["requests"]["spend_usdc"],
        strict_limit=payload["requests"]["strict_limit"],
    )

    expected = dict(payload["expected"]["spend_fill"])
    expected.pop("filled_quantity")

    assert result == expected
