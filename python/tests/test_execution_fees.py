from __future__ import annotations

from prediction_core.execution.fees import (
    TradingFeeEstimate,
    TradingFeeSchedule,
    TransferCostEstimate,
    TransferFeeSchedule,
    estimate_trading_fee,
    estimate_transfer_costs,
)


def test_estimate_trading_fee_uses_taker_bps_and_min_fee() -> None:
    schedule = TradingFeeSchedule(maker_bps=10.0, taker_bps=20.0, min_fee=0.5)

    result = estimate_trading_fee(notional=100.0, schedule=schedule, is_maker=False)

    assert result.fee == 0.5
    assert result.applied_bps == 20.0
    assert result.is_maker is False
    assert result.notional == 100.0


def test_estimate_trading_fee_uses_maker_bps_when_flagged() -> None:
    schedule = TradingFeeSchedule(maker_bps=10.0, taker_bps=20.0, min_fee=0.0)

    result = estimate_trading_fee(notional=500.0, schedule=schedule, is_maker=True)

    assert result.fee == 0.5
    assert result.applied_bps == 10.0
    assert result.is_maker is True


def test_estimate_transfer_costs_sums_deposit_and_withdrawal_costs() -> None:
    schedule = TransferFeeSchedule(
        deposit_fixed=1.0,
        deposit_bps=20.0,
        withdrawal_fixed=2.0,
        withdrawal_bps=30.0,
    )

    result = estimate_transfer_costs(amount=1000.0, schedule=schedule)

    assert result.amount == 1000.0
    assert result.deposit_fee == 3.0
    assert result.withdrawal_fee == 5.0
    assert result.total_fee == 8.0


def test_fee_estimate_serializers_return_plain_dicts() -> None:
    trading = TradingFeeEstimate(notional=250.0, applied_bps=12.5, fee=0.3125, is_maker=False)
    transfer = TransferCostEstimate(amount=50.0, deposit_fee=0.1, withdrawal_fee=0.2)

    assert trading.to_dict() == {
        "notional": 250.0,
        "applied_bps": 12.5,
        "fee": 0.3125,
        "is_maker": False,
    }
    assert transfer.to_dict() == {
        "amount": 50.0,
        "deposit_fee": 0.1,
        "withdrawal_fee": 0.2,
        "total_fee": 0.3,
    }
