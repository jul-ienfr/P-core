from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from prediction_core.execution import (
    OrderBookSnapshot,
    TradingFeeSchedule,
    TransferFeeSchedule,
    quote_execution_cost,
)


class PaperTradeStatus(str, Enum):
    filled = "filled"
    partial = "partial"
    skipped = "skipped"
    rejected = "rejected"


class PaperPositionSide(str, Enum):
    yes = "yes"
    no = "no"


class PaperExecutionSide(str, Enum):
    buy = "buy"
    sell = "sell"


class PaperTradeFill(BaseModel):
    schema_version: str = "v1"
    fill_id: str = Field(default_factory=lambda: f"fill_{uuid4().hex[:12]}")
    trade_id: str
    run_id: str
    market_id: str
    position_side: PaperPositionSide = PaperPositionSide.yes
    execution_side: PaperExecutionSide = PaperExecutionSide.buy
    requested_quantity: float
    filled_quantity: float
    fill_price: float
    gross_notional: float
    fee_paid: float = 0.0
    slippage_bps: float = 0.0
    level_index: int | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)


class PaperTradePostmortem(BaseModel):
    schema_version: str = "v1"
    postmortem_id: str = Field(default_factory=lambda: f"paperpm_{uuid4().hex[:12]}")
    run_id: str
    trade_id: str
    market_id: str
    status: PaperTradeStatus = PaperTradeStatus.skipped
    position_side: PaperPositionSide = PaperPositionSide.yes
    execution_side: PaperExecutionSide = PaperExecutionSide.buy
    order_count: int = 1
    requested_quantity: float = 0.0
    filled_quantity: float = 0.0
    fill_rate: float = 0.0
    reference_price: float | None = None
    average_fill_price: float | None = None
    closing_line_drift_bps: float = 0.0
    slippage_bps: float = 0.0
    fee_paid: float = 0.0
    gross_notional: float = 0.0
    gross_cash_flow: float = 0.0
    net_cash_flow: float = 0.0
    effective_price_after_fees: float | None = None
    fill_count: int = 0
    average_fill_quantity: float = 0.0
    fragmented: bool = False
    fragmentation_score: float = 0.0
    no_trade_zone: bool = False
    stale_blocked: bool = False
    settlement_status: str = "not_settled"
    recommendation: str = "hold"
    notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


def _derive_execution_slippage_bps(*, execution: Any, side: str) -> float:
    if execution.estimated_filled_quantity <= 0:
        return 0.0
    top_price = execution.quoted_best_ask if side == "buy" else execution.quoted_best_bid
    if top_price is None or top_price <= 0:
        return 0.0
    reference_notional = top_price * execution.estimated_filled_quantity
    if reference_notional <= 0:
        return 0.0
    return round(execution.book_slippage_cost / reference_notional * 10000.0, 2)


def simulate_paper_trade_from_execution(
    *,
    run_id: str,
    market_id: str,
    book: OrderBookSnapshot,
    side: str,
    size: float,
    is_maker: bool,
    trading_fees: TradingFeeSchedule | None,
    transfer_fees: TransferFeeSchedule | None,
    edge_gross: float = 0.0,
    position_side: PaperPositionSide = PaperPositionSide.yes,
    reference_price: float | None = None,
    metadata: dict[str, Any] | None = None,
) -> "PaperTradeSimulation":
    execution = quote_execution_cost(
        book=book,
        side=side,
        size=size,
        is_maker=is_maker,
        trading_fees=trading_fees,
        transfer_fees=transfer_fees,
        edge_gross=edge_gross,
    )
    execution_payload = execution.to_dict()
    fee_paid = round(
        execution.trading_fee_cost + execution.deposit_fee_cost + execution.withdrawal_fee_cost,
        6,
    )
    slippage_bps = _derive_execution_slippage_bps(execution=execution, side=side)
    combined_metadata = dict(metadata or {})
    combined_metadata["execution"] = execution_payload

    fills: list[PaperTradeFill] = []
    status = PaperTradeStatus.skipped
    if execution.estimated_filled_quantity > 0:
        status = (
            PaperTradeStatus.filled
            if execution.estimated_filled_quantity >= execution.requested_quantity
            else PaperTradeStatus.partial
        )
        fills = [
            PaperTradeFill(
                trade_id=f"paper_{uuid4().hex[:12]}",
                run_id=run_id,
                market_id=market_id,
                position_side=position_side,
                execution_side=PaperExecutionSide(side),
                requested_quantity=execution.requested_quantity,
                filled_quantity=execution.estimated_filled_quantity,
                fill_price=execution.estimated_avg_fill_price or 0.0,
                gross_notional=round((execution.estimated_avg_fill_price or 0.0) * execution.estimated_filled_quantity, 6),
                fee_paid=fee_paid,
                slippage_bps=slippage_bps,
            )
        ]
    else:
        combined_metadata.setdefault("reason", "no_fill")

    return PaperTradeSimulation(
        run_id=run_id,
        market_id=market_id,
        position_side=position_side,
        execution_side=PaperExecutionSide(side),
        requested_quantity=execution.requested_quantity,
        filled_quantity=execution.estimated_filled_quantity,
        average_fill_price=execution.estimated_avg_fill_price,
        reference_price=reference_price if reference_price is not None else execution.quoted_mid_price,
        gross_notional=round((execution.estimated_avg_fill_price or 0.0) * execution.estimated_filled_quantity, 6),
        fee_paid=fee_paid,
        cash_flow=round((execution.estimated_avg_fill_price or 0.0) * execution.estimated_filled_quantity + fee_paid, 6),
        slippage_bps=slippage_bps,
        fill_count=len(fills),
        status=status,
        fills=fills,
        metadata=combined_metadata,
    )


class PaperTradeSimulation(BaseModel):
    schema_version: str = "v1"
    trade_id: str = Field(default_factory=lambda: f"paper_{uuid4().hex[:12]}")
    run_id: str
    market_id: str
    position_side: PaperPositionSide = PaperPositionSide.yes
    execution_side: PaperExecutionSide = PaperExecutionSide.buy
    stake: float = 0.0
    requested_quantity: float = 0.0
    filled_quantity: float = 0.0
    average_fill_price: float | None = None
    reference_price: float | None = None
    gross_notional: float = 0.0
    fee_paid: float = 0.0
    cash_flow: float = 0.0
    slippage_bps: float = 0.0
    order_count: int = 1
    fill_count: int = 0
    settlement_status: str = "simulated"
    status: PaperTradeStatus = PaperTradeStatus.skipped
    snapshot_id: str | None = None
    fills: list[PaperTradeFill] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _derive_fields(self) -> "PaperTradeSimulation":
        self.fill_count = len(self.fills) if self.fill_count <= 0 else max(0, int(self.fill_count))
        self.order_count = max(1, int(self.order_count))
        if not self.settlement_status:
            self.settlement_status = "simulated"
        if self.status in {PaperTradeStatus.filled, PaperTradeStatus.partial}:
            if self.settlement_status == "simulated":
                self.settlement_status = "simulated_settled"
        elif self.settlement_status == "simulated":
            self.settlement_status = "not_settled"
        if self.filled_quantity > 0 and self.average_fill_price is None:
            self.average_fill_price = round(self.gross_notional / self.filled_quantity, 6)
        if self.average_fill_price is not None:
            self.average_fill_price = round(max(0.0, min(1.0, float(self.average_fill_price))), 6)
        return self

    @property
    def is_active(self) -> bool:
        return self.status in {PaperTradeStatus.filled, PaperTradeStatus.partial}

    def postmortem(self) -> PaperTradePostmortem:
        fill_rate = 0.0 if self.requested_quantity <= 0 else round(min(1.0, self.filled_quantity / self.requested_quantity), 6)
        closing_line_drift_bps = 0.0
        if self.average_fill_price is not None and self.reference_price is not None:
            closing_line_drift_bps = round((self.average_fill_price - self.reference_price) * 10000.0, 2)
        fill_count = len(self.fills)
        average_fill_quantity = 0.0 if fill_count <= 0 else round(self.filled_quantity / fill_count, 6)
        fragmented = fill_count > 1
        fragmentation_score = 0.0
        if fragmented and self.filled_quantity > 0:
            largest_fill = max(fill.filled_quantity for fill in self.fills)
            fragmentation_score = round(1.0 - min(1.0, largest_fill / self.filled_quantity), 6)
        gross_cash_flow = self.gross_notional if self.execution_side == PaperExecutionSide.sell else -self.gross_notional
        net_cash_flow = gross_cash_flow - self.fee_paid
        effective_price_after_fees = None
        if self.filled_quantity > 0:
            effective_price_after_fees = round(abs(net_cash_flow) / self.filled_quantity, 6)
        stale_blocked = bool(self.metadata.get("stale_blocked")) or str(self.metadata.get("reason", "")) == "snapshot_stale"
        no_trade_zone = (
            bool(self.metadata.get("no_trade_zone"))
            or self.status in {PaperTradeStatus.skipped, PaperTradeStatus.rejected}
            or stale_blocked
        )
        notes = []
        if self.status is PaperTradeStatus.filled:
            notes.append("filled")
        elif self.status is PaperTradeStatus.partial:
            notes.append("partial_fill")
        elif self.status is PaperTradeStatus.skipped:
            notes.append("skipped")
        elif self.status is PaperTradeStatus.rejected:
            notes.append("rejected")
        if fragmented:
            notes.append("fragmented")
        if no_trade_zone:
            notes.append("no_trade_zone")
        if stale_blocked:
            notes.append("stale_blocked")
        if self.metadata.get("reason"):
            notes.append(str(self.metadata["reason"]))
        recommendation = "hold"
        if no_trade_zone:
            recommendation = "no_trade"
        elif self.status in {PaperTradeStatus.skipped, PaperTradeStatus.rejected}:
            recommendation = "review_thresholds"
        elif self.status is PaperTradeStatus.partial:
            recommendation = "reduce_size"
        elif abs(closing_line_drift_bps) > 100.0:
            recommendation = "reprice"
        return PaperTradePostmortem(
            run_id=self.run_id,
            trade_id=self.trade_id,
            market_id=self.market_id,
            status=self.status,
            position_side=self.position_side,
            execution_side=self.execution_side,
            order_count=self.order_count,
            requested_quantity=self.requested_quantity,
            filled_quantity=self.filled_quantity,
            fill_rate=fill_rate,
            reference_price=self.reference_price,
            average_fill_price=self.average_fill_price,
            closing_line_drift_bps=closing_line_drift_bps,
            slippage_bps=self.slippage_bps,
            fee_paid=self.fee_paid,
            gross_notional=self.gross_notional,
            gross_cash_flow=gross_cash_flow,
            net_cash_flow=net_cash_flow,
            effective_price_after_fees=effective_price_after_fees,
            fill_count=fill_count,
            average_fill_quantity=average_fill_quantity,
            fragmented=fragmented,
            fragmentation_score=fragmentation_score,
            no_trade_zone=no_trade_zone,
            stale_blocked=stale_blocked,
            settlement_status=self.settlement_status,
            recommendation=recommendation,
            notes=notes,
            metadata=dict(self.metadata),
        )
