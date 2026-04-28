import sys
import types

from prediction_core.polymarket_execution import (
    ExecutionRiskLimits,
    ExecutionRiskState,
    OrderRequest,
    evaluate_execution_risk,
)


def _order(notional=7.5, price=0.44):
    return OrderRequest(
        market_id="m1",
        token_id="t",
        outcome="Yes",
        side="buy",
        order_type="limit",
        limit_price=price,
        notional_usdc=notional,
        idempotency_key="k",
    )


def test_risk_allows_order_inside_limits():
    result = evaluate_execution_risk(
        _order(),
        limits=ExecutionRiskLimits(
            max_order_notional_usdc=10,
            max_total_exposure_usdc=100,
            max_daily_loss_usdc=25,
            max_spread=0.05,
        ),
        state=ExecutionRiskState(total_exposure_usdc=20, daily_realized_pnl_usdc=0),
        market_snapshot={"spread": 0.03, "sequence": 10},
    )

    assert result.allowed is True
    assert result.blocked_by == []


def test_risk_blocks_oversized_order():
    result = evaluate_execution_risk(
        _order(notional=11),
        limits=ExecutionRiskLimits(
            max_order_notional_usdc=10,
            max_total_exposure_usdc=100,
            max_daily_loss_usdc=25,
            max_spread=0.05,
        ),
        state=ExecutionRiskState(total_exposure_usdc=20, daily_realized_pnl_usdc=0),
        market_snapshot={"spread": 0.03, "sequence": 10},
    )

    assert result.allowed is False
    assert "max_order_notional_usdc" in result.blocked_by


def test_risk_uses_rust_when_enabled(monkeypatch):
    monkeypatch.setenv("PREDICTION_CORE_RUST_ORDERBOOK", "1")
    fake_module = types.ModuleType("prediction_core._rust_orderbook")

    def rust_evaluate_execution_risk(**kwargs):
        assert kwargs["order_notional_usdc"] == 7.5
        assert kwargs["total_exposure_usdc"] == 20.0
        assert kwargs["spread"] == 0.03
        return {"allowed": False, "blocked_by": ["max_spread"]}

    fake_module.evaluate_execution_risk = rust_evaluate_execution_risk
    monkeypatch.setitem(sys.modules, "prediction_core._rust_orderbook", fake_module)

    result = evaluate_execution_risk(
        _order(),
        limits=ExecutionRiskLimits(
            max_order_notional_usdc=10,
            max_total_exposure_usdc=100,
            max_daily_loss_usdc=25,
            max_spread=0.05,
        ),
        state=ExecutionRiskState(total_exposure_usdc=20, daily_realized_pnl_usdc=0),
        market_snapshot={"spread": 0.03, "sequence": 10},
    )

    assert result.allowed is False
    assert result.blocked_by == ["max_spread"]


def test_risk_blocks_total_exposure():
    result = evaluate_execution_risk(
        _order(notional=7.5),
        limits=ExecutionRiskLimits(
            max_order_notional_usdc=10,
            max_total_exposure_usdc=25,
            max_daily_loss_usdc=25,
            max_spread=0.05,
        ),
        state=ExecutionRiskState(total_exposure_usdc=20, daily_realized_pnl_usdc=0),
        market_snapshot={"spread": 0.03, "sequence": 10},
    )

    assert result.allowed is False
    assert "max_total_exposure_usdc" in result.blocked_by


def test_risk_blocks_wide_spread_and_daily_loss():
    result = evaluate_execution_risk(
        _order(),
        limits=ExecutionRiskLimits(
            max_order_notional_usdc=10,
            max_total_exposure_usdc=100,
            max_daily_loss_usdc=25,
            max_spread=0.05,
        ),
        state=ExecutionRiskState(total_exposure_usdc=20, daily_realized_pnl_usdc=-30),
        market_snapshot={"spread": 0.08, "sequence": 10},
    )

    assert result.allowed is False
    assert set(result.blocked_by) >= {"max_spread", "max_daily_loss_usdc"}


def test_risk_blocks_missing_spread_fail_closed():
    result = evaluate_execution_risk(
        _order(),
        limits=ExecutionRiskLimits(
            max_order_notional_usdc=10,
            max_total_exposure_usdc=100,
            max_daily_loss_usdc=25,
            max_spread=0.05,
        ),
        state=ExecutionRiskState(total_exposure_usdc=20, daily_realized_pnl_usdc=0),
        market_snapshot={"sequence": 10},
    )

    assert result.allowed is False
    assert "missing_spread" in result.blocked_by


def test_risk_blocks_invalid_or_non_finite_spread_fail_closed():
    for spread in ("bad", float("nan"), float("inf")):
        result = evaluate_execution_risk(
            _order(),
            limits=ExecutionRiskLimits(
                max_order_notional_usdc=10,
                max_total_exposure_usdc=100,
                max_daily_loss_usdc=25,
                max_spread=0.05,
            ),
            state=ExecutionRiskState(total_exposure_usdc=20, daily_realized_pnl_usdc=0),
            market_snapshot={"spread": spread, "sequence": 10},
        )

        assert result.allowed is False
        assert "invalid_spread" in result.blocked_by


def test_risk_limits_reject_non_finite_values_fail_closed():
    try:
        ExecutionRiskLimits(
            max_order_notional_usdc=float("nan"),
            max_total_exposure_usdc=100,
            max_daily_loss_usdc=25,
            max_spread=0.05,
        )
    except ValueError as exc:
        assert "max_order_notional_usdc must be finite and positive" in str(exc)
    else:
        raise AssertionError("nan risk limit should fail closed")


def test_risk_state_rejects_invalid_exposure_fail_closed():
    try:
        ExecutionRiskState(total_exposure_usdc=float("inf"), daily_realized_pnl_usdc=0)
    except ValueError as exc:
        assert "total_exposure_usdc must be finite and non-negative" in str(exc)
    else:
        raise AssertionError("infinite exposure should fail closed")
