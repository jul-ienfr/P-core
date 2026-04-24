from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(slots=True)
class TradingFeeSchedule:
    maker_bps: float
    taker_bps: float
    min_fee: float = 0.0


@dataclass(slots=True)
class TradingFeeEstimate:
    notional: float
    applied_bps: float
    fee: float
    is_maker: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TransferFeeSchedule:
    deposit_fixed: float = 0.0
    deposit_bps: float = 0.0
    withdrawal_fixed: float = 0.0
    withdrawal_bps: float = 0.0


@dataclass(slots=True)
class TransferCostEstimate:
    amount: float
    deposit_fee: float
    withdrawal_fee: float

    @property
    def total_fee(self) -> float:
        return round(self.deposit_fee + self.withdrawal_fee, 6)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["total_fee"] = self.total_fee
        return payload


def estimate_trading_fee(*, notional: float, schedule: TradingFeeSchedule, is_maker: bool) -> TradingFeeEstimate:
    safe_notional = max(0.0, float(notional))
    applied_bps = max(0.0, schedule.maker_bps if is_maker else schedule.taker_bps)
    proportional_fee = safe_notional * applied_bps / 10000.0
    fee = round(max(max(0.0, schedule.min_fee), proportional_fee), 6)
    return TradingFeeEstimate(
        notional=safe_notional,
        applied_bps=applied_bps,
        fee=fee,
        is_maker=is_maker,
    )


def estimate_transfer_costs(*, amount: float, schedule: TransferFeeSchedule) -> TransferCostEstimate:
    safe_amount = max(0.0, float(amount))
    deposit_fee = round(max(0.0, schedule.deposit_fixed) + safe_amount * max(0.0, schedule.deposit_bps) / 10000.0, 6)
    withdrawal_fee = round(max(0.0, schedule.withdrawal_fixed) + safe_amount * max(0.0, schedule.withdrawal_bps) / 10000.0, 6)
    return TransferCostEstimate(
        amount=safe_amount,
        deposit_fee=deposit_fee,
        withdrawal_fee=withdrawal_fee,
    )


def compute_trading_fee(*, notional: float, schedule: TradingFeeSchedule, liquidity_role: str = "taker") -> TradingFeeEstimate:
    role = (liquidity_role or "taker").lower()
    return estimate_trading_fee(notional=notional, schedule=schedule, is_maker=role == "maker")


def compute_transfer_costs(*, schedule: TransferFeeSchedule, amount: float) -> TransferCostEstimate:
    return estimate_transfer_costs(amount=amount, schedule=schedule)
