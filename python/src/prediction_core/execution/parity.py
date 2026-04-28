from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from prediction_core.execution.book import FillEstimate, estimate_fill_from_book
from prediction_core.execution.fees import TradingFeeSchedule, TransferFeeSchedule, estimate_trading_fee, estimate_transfer_costs
from prediction_core.execution.models import ExecutionCostBreakdown, OrderBookSnapshot

BookSide = Literal["buy", "sell"]


@dataclass(slots=True)
class ExecutionAssumptions:
    """Paper/dry-run execution knobs shared by replay, paper, and future Rust live simulation.

    This intentionally models only deterministic simulation inputs. It does not contain
    credentials, wallet material, venue client handles, or any order-placement affordance.
    """

    schema_version: str = "v1"
    mode: Literal["replay", "paper", "live_dry_run"] = "paper"
    latency_ms: int = 0
    slippage_bps: float = 0.0
    queue_ahead_quantity: float = 0.0
    allow_multi_level_sweep: bool = True
    reject_on_empty_book: bool = True
    reject_on_insufficient_depth: bool = False
    maker_fee_bps: float = 0.0
    taker_fee_bps: float = 0.0
    min_fee: float = 0.0
    deposit_fixed: float = 0.0
    deposit_bps: float = 0.0
    withdrawal_fixed: float = 0.0
    withdrawal_bps: float = 0.0

    def __post_init__(self) -> None:
        if self.mode not in {"replay", "paper", "live_dry_run"}:
            raise ValueError("execution assumptions are paper/dry-run only")
        self.latency_ms = max(0, int(self.latency_ms))
        self.slippage_bps = max(0.0, float(self.slippage_bps))
        self.queue_ahead_quantity = max(0.0, float(self.queue_ahead_quantity))
        self.maker_fee_bps = max(0.0, float(self.maker_fee_bps))
        self.taker_fee_bps = max(0.0, float(self.taker_fee_bps))
        self.min_fee = max(0.0, float(self.min_fee))
        self.deposit_fixed = max(0.0, float(self.deposit_fixed))
        self.deposit_bps = max(0.0, float(self.deposit_bps))
        self.withdrawal_fixed = max(0.0, float(self.withdrawal_fixed))
        self.withdrawal_bps = max(0.0, float(self.withdrawal_bps))

    def trading_fees(self) -> TradingFeeSchedule:
        return TradingFeeSchedule(maker_bps=self.maker_fee_bps, taker_bps=self.taker_fee_bps, min_fee=self.min_fee)

    def transfer_fees(self) -> TransferFeeSchedule:
        return TransferFeeSchedule(
            deposit_fixed=self.deposit_fixed,
            deposit_bps=self.deposit_bps,
            withdrawal_fixed=self.withdrawal_fixed,
            withdrawal_bps=self.withdrawal_bps,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ExecutionParityQuote:
    schema_version: str
    mode: str
    side: str
    requested_quantity: float
    filled_quantity: float
    unfilled_quantity: float
    average_fill_price: float | None
    top_of_book_price: float | None
    gross_notional: float
    book_slippage_cost: float
    assumption_slippage_cost: float
    total_slippage_cost: float
    latency_ms: int
    queue_ahead_quantity: float
    levels_consumed: int
    status: str
    blocker: str | None
    cost: ExecutionCostBreakdown

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["cost"] = self.cost.to_dict()
        return payload


@dataclass(frozen=True, slots=True)
class ReplayScenario:
    name: str
    book: OrderBookSnapshot
    side: BookSide
    requested_quantity: float
    assumptions: ExecutionAssumptions
    expected_status: str
    expected_blocker: str | None = None


def quote_execution_parity(
    *,
    book: OrderBookSnapshot,
    side: BookSide,
    requested_quantity: float,
    assumptions: ExecutionAssumptions | None = None,
    is_maker: bool = False,
    edge_gross: float = 0.0,
) -> ExecutionParityQuote:
    """Quote a deterministic replay/paper/live_dry_run execution without side effects."""

    assumptions = assumptions or ExecutionAssumptions()
    if assumptions.mode not in {"replay", "paper", "live_dry_run"}:
        raise ValueError("live execution is outside this dry-run parity contract")

    queued_book = _apply_queue_ahead(book=book, side=side, queue_ahead_quantity=assumptions.queue_ahead_quantity)
    sweep_book = queued_book if assumptions.allow_multi_level_sweep else _top_level_book(queued_book, side=side)
    fill = estimate_fill_from_book(book=sweep_book, side=side, requested_quantity=requested_quantity)

    assumption_slippage_cost = 0.0
    if fill.gross_notional > 0 and assumptions.slippage_bps > 0:
        assumption_slippage_cost = round(fill.gross_notional * assumptions.slippage_bps / 10000.0, 6)

    trading_fees = assumptions.trading_fees()
    transfer_fees = assumptions.transfer_fees()
    trading_fee = estimate_trading_fee(notional=fill.gross_notional, schedule=trading_fees, is_maker=is_maker)
    transfer_fee = estimate_transfer_costs(amount=fill.gross_notional, schedule=transfer_fees)
    cost = ExecutionCostBreakdown(
        requested_quantity=round(max(0.0, float(requested_quantity)), 6),
        estimated_filled_quantity=fill.filled_quantity,
        estimated_avg_fill_price=fill.average_price,
        quoted_mid_price=book.mid_price,
        quoted_best_bid=book.best_bid,
        quoted_best_ask=book.best_ask,
        spread_cost=_spread_cost(book=book, fill=fill, side=side),
        book_slippage_cost=round(fill.slippage_cost + assumption_slippage_cost, 6),
        trading_fee_cost=trading_fee.fee if fill.filled_quantity > 0 else 0.0,
        deposit_fee_cost=transfer_fee.deposit_fee if fill.filled_quantity > 0 else 0.0,
        withdrawal_fee_cost=transfer_fee.withdrawal_fee if fill.filled_quantity > 0 else 0.0,
        edge_gross=round(float(edge_gross), 6),
    )

    status, blocker = _execution_status(fill=fill, assumptions=assumptions, book=sweep_book)
    return ExecutionParityQuote(
        schema_version=assumptions.schema_version,
        mode=assumptions.mode,
        side=side,
        requested_quantity=round(max(0.0, float(requested_quantity)), 6),
        filled_quantity=fill.filled_quantity,
        unfilled_quantity=fill.unfilled_quantity,
        average_fill_price=fill.average_price,
        top_of_book_price=fill.top_of_book_price,
        gross_notional=fill.gross_notional,
        book_slippage_cost=fill.slippage_cost,
        assumption_slippage_cost=assumption_slippage_cost,
        total_slippage_cost=round(fill.slippage_cost + assumption_slippage_cost, 6),
        latency_ms=assumptions.latency_ms,
        queue_ahead_quantity=assumptions.queue_ahead_quantity,
        levels_consumed=fill.levels_consumed,
        status=status,
        blocker=blocker,
        cost=cost,
    )


def deterministic_replay_scenarios() -> list[ReplayScenario]:
    return [
        ReplayScenario(
            name="empty_book",
            book=OrderBookSnapshot(bids=[], asks=[]),
            side="buy",
            requested_quantity=5.0,
            assumptions=ExecutionAssumptions(mode="replay"),
            expected_status="skipped",
            expected_blocker="empty_book",
        ),
        ReplayScenario(
            name="wide_spread_with_latency_and_fees",
            book=OrderBookSnapshot(bids=[_level(0.35, 10.0)], asks=[_level(0.65, 10.0)]),
            side="buy",
            requested_quantity=2.0,
            assumptions=ExecutionAssumptions(mode="paper", latency_ms=750, slippage_bps=25.0, taker_fee_bps=10.0),
            expected_status="filled",
        ),
        ReplayScenario(
            name="partial_fill_insufficient_depth",
            book=OrderBookSnapshot(bids=[_level(0.39, 1.0)], asks=[_level(0.41, 2.0), _level(0.42, 1.0)]),
            side="buy",
            requested_quantity=5.0,
            assumptions=ExecutionAssumptions(mode="replay", reject_on_insufficient_depth=False),
            expected_status="partial",
            expected_blocker="insufficient_depth",
        ),
        ReplayScenario(
            name="insufficient_depth_rejected",
            book=OrderBookSnapshot(bids=[_level(0.39, 1.0)], asks=[_level(0.41, 2.0)]),
            side="buy",
            requested_quantity=5.0,
            assumptions=ExecutionAssumptions(mode="live_dry_run", reject_on_insufficient_depth=True),
            expected_status="rejected",
            expected_blocker="insufficient_depth",
        ),
        ReplayScenario(
            name="single_level_no_sweep_partial",
            book=OrderBookSnapshot(bids=[_level(0.40, 5.0)], asks=[_level(0.50, 2.0), _level(0.51, 10.0)]),
            side="buy",
            requested_quantity=5.0,
            assumptions=ExecutionAssumptions(mode="paper", allow_multi_level_sweep=False),
            expected_status="partial",
            expected_blocker="insufficient_depth",
        ),
        ReplayScenario(
            name="queue_position_consumes_top_level",
            book=OrderBookSnapshot(bids=[_level(0.44, 5.0)], asks=[_level(0.45, 2.0), _level(0.47, 4.0)]),
            side="buy",
            requested_quantity=3.0,
            assumptions=ExecutionAssumptions(mode="replay", queue_ahead_quantity=2.0),
            expected_status="filled",
        ),
    ]


def _execution_status(
    *,
    fill: FillEstimate,
    assumptions: ExecutionAssumptions,
    book: OrderBookSnapshot,
) -> tuple[str, str | None]:
    if _book_is_empty(book) and assumptions.reject_on_empty_book:
        return "skipped", "empty_book"
    if fill.filled_quantity <= 0:
        return "skipped", "no_fill"
    if fill.unfilled_quantity > 0:
        if assumptions.reject_on_insufficient_depth:
            return "rejected", "insufficient_depth"
        return "partial", "insufficient_depth"
    return "filled", None


def _book_is_empty(book: OrderBookSnapshot) -> bool:
    return not book.bids and not book.asks


def _spread_cost(*, book: OrderBookSnapshot, fill: FillEstimate, side: str) -> float:
    if fill.filled_quantity <= 0 or book.mid_price is None or fill.top_of_book_price is None:
        return 0.0
    return round(abs(fill.top_of_book_price - book.mid_price) * fill.filled_quantity, 6)


def _apply_queue_ahead(*, book: OrderBookSnapshot, side: str, queue_ahead_quantity: float) -> OrderBookSnapshot:
    queue = max(0.0, float(queue_ahead_quantity))
    if queue <= 0.0:
        return book
    bids = [_level(level.price, level.quantity) for level in book.bids]
    asks = [_level(level.price, level.quantity) for level in book.asks]
    target = asks if side == "buy" else bids
    reverse = side == "sell"
    target.sort(key=lambda level: level.price, reverse=reverse)
    while queue > 1e-12 and target:
        consume = min(queue, target[0].quantity)
        target[0].quantity = round(target[0].quantity - consume, 6)
        queue -= consume
        if target[0].quantity <= 1e-12:
            target.pop(0)
    return OrderBookSnapshot(bids=bids, asks=asks, timestamp=book.timestamp, venue=book.venue)


def _top_level_book(book: OrderBookSnapshot, *, side: str) -> OrderBookSnapshot:
    bids = sorted([_level(level.price, level.quantity) for level in book.bids], key=lambda level: level.price, reverse=True)
    asks = sorted([_level(level.price, level.quantity) for level in book.asks], key=lambda level: level.price)
    if side == "buy":
        return OrderBookSnapshot(bids=bids[:1], asks=asks[:1], timestamp=book.timestamp, venue=book.venue)
    return OrderBookSnapshot(bids=bids[:1], asks=asks[:1], timestamp=book.timestamp, venue=book.venue)


def _level(price: float, quantity: float) -> Any:
    from prediction_core.execution.models import BookLevel

    return BookLevel(price=float(price), quantity=float(quantity))
