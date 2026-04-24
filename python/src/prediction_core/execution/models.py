from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class BookLevel:
    price: float
    quantity: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class OrderBookSnapshot:
    bids: list[BookLevel]
    asks: list[BookLevel]
    timestamp: datetime | None = None
    venue: str | None = None

    @property
    def best_bid(self) -> float | None:
        if not self.bids:
            return None
        return max(level.price for level in self.bids)

    @property
    def best_ask(self) -> float | None:
        if not self.asks:
            return None
        return min(level.price for level in self.asks)

    @property
    def mid_price(self) -> float | None:
        if self.best_bid is None or self.best_ask is None:
            return None
        return round((self.best_bid + self.best_ask) / 2.0, 6)

    @property
    def spread(self) -> float | None:
        if self.best_bid is None or self.best_ask is None:
            return None
        return round(self.best_ask - self.best_bid, 6)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["best_bid"] = self.best_bid
        payload["best_ask"] = self.best_ask
        payload["mid_price"] = self.mid_price
        payload["spread"] = self.spread
        return payload


@dataclass(slots=True)
class TradingFeeSchedule:
    maker_bps: float
    taker_bps: float
    min_fee: float = 0.0

    def fee_for_notional(self, notional: float, *, is_maker: bool) -> float:
        bps = self.maker_bps if is_maker else self.taker_bps
        proportional_fee = max(0.0, float(notional)) * max(0.0, bps) / 10000.0
        return round(max(self.min_fee, proportional_fee), 6)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TransferFeeSchedule:
    deposit_fixed: float = 0.0
    deposit_bps: float = 0.0
    withdrawal_fixed: float = 0.0
    withdrawal_bps: float = 0.0

    def deposit_cost(self, amount: float) -> float:
        return round(max(0.0, self.deposit_fixed) + max(0.0, amount) * max(0.0, self.deposit_bps) / 10000.0, 6)

    def withdrawal_cost(self, amount: float) -> float:
        return round(max(0.0, self.withdrawal_fixed) + max(0.0, amount) * max(0.0, self.withdrawal_bps) / 10000.0, 6)

    def total_cost(self, amount: float) -> float:
        return round(self.deposit_cost(amount) + self.withdrawal_cost(amount), 6)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ExecutionCostBreakdown:
    requested_quantity: float
    estimated_filled_quantity: float
    estimated_avg_fill_price: float | None
    quoted_mid_price: float | None
    quoted_best_bid: float | None
    quoted_best_ask: float | None
    spread_cost: float = 0.0
    book_slippage_cost: float = 0.0
    trading_fee_cost: float = 0.0
    deposit_fee_cost: float = 0.0
    withdrawal_fee_cost: float = 0.0
    edge_gross: float = 0.0

    @property
    def total_execution_cost(self) -> float:
        return round(self.spread_cost + self.book_slippage_cost + self.trading_fee_cost, 6)

    @property
    def total_all_in_cost(self) -> float:
        return round(self.total_execution_cost + self.deposit_fee_cost + self.withdrawal_fee_cost, 6)

    @property
    def effective_unit_price(self) -> float | None:
        if self.estimated_filled_quantity <= 0 or self.estimated_avg_fill_price is None:
            return None
        gross_notional = self.estimated_avg_fill_price * self.estimated_filled_quantity
        return round((gross_notional + self.total_all_in_cost) / self.estimated_filled_quantity, 6)

    @property
    def edge_net_execution(self) -> float:
        return round(self.edge_gross - self.total_execution_cost, 6)

    @property
    def edge_net_all_in(self) -> float:
        return round(self.edge_gross - self.total_all_in_cost, 6)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["total_execution_cost"] = self.total_execution_cost
        payload["total_all_in_cost"] = self.total_all_in_cost
        payload["effective_unit_price"] = self.effective_unit_price
        payload["edge_net_execution"] = self.edge_net_execution
        payload["edge_net_all_in"] = self.edge_net_all_in
        return payload
