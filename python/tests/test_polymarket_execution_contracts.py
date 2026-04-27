import pytest

from prediction_core.polymarket_execution import (
    ClobRestPolymarketExecutor,
    DryRunPolymarketExecutor,
    ExecutionCredentialsError,
    ExecutionMode,
    OrderRequest,
    OrderResult,
    OrderSide,
    OrderType,
)


def test_order_request_serializes_limit_buy():
    order = OrderRequest(
        market_id="m1",
        token_id="yes-token",
        outcome="Yes",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        limit_price=0.44,
        notional_usdc=7.5,
        idempotency_key="weather:m1:yes-token:buy:20260427T010000Z",
    )

    assert order.to_dict() == {
        "market_id": "m1",
        "token_id": "yes-token",
        "outcome": "Yes",
        "side": "buy",
        "order_type": "limit",
        "limit_price": 0.44,
        "notional_usdc": 7.5,
        "idempotency_key": "weather:m1:yes-token:buy:20260427T010000Z",
        "metadata": {},
    }


def test_order_request_rejects_invalid_price_and_size():
    with pytest.raises(ValueError, match="limit_price must be between 0 and 1"):
        OrderRequest(
            market_id="m1",
            token_id="t",
            outcome="Yes",
            side="buy",
            order_type="limit",
            limit_price=1.5,
            notional_usdc=5,
            idempotency_key="k",
        )
    with pytest.raises(ValueError, match="notional_usdc must be positive"):
        OrderRequest(
            market_id="m1",
            token_id="t",
            outcome="Yes",
            side="buy",
            order_type="limit",
            limit_price=0.5,
            notional_usdc=0,
            idempotency_key="k",
        )


def test_order_result_serializes_executor_response():
    result = OrderResult(
        accepted=True,
        status="accepted",
        exchange_order_id="dry-1",
        idempotency_key="k",
        raw_response={"ok": True},
    )
    assert result.to_dict()["accepted"] is True
    assert result.to_dict()["exchange_order_id"] == "dry-1"


def test_execution_mode_values_are_stable():
    assert ExecutionMode.PAPER.value == "paper"
    assert ExecutionMode.DRY_RUN.value == "dry_run"
    assert ExecutionMode.LIVE.value == "live"


def test_dry_run_executor_accepts_without_network_and_records_order():
    executor = DryRunPolymarketExecutor()
    order = OrderRequest(
        market_id="m1",
        token_id="yes-token",
        outcome="Yes",
        side="buy",
        order_type="limit",
        limit_price=0.44,
        notional_usdc=7.5,
        idempotency_key="k1",
    )

    result = executor.submit_order(order)

    assert result.accepted is True
    assert result.status == "dry_run_accepted"
    assert result.exchange_order_id == "dry-run:k1"
    assert executor.orders == [order]
    assert result.raw_response["dry_run"] is True


def test_clob_rest_executor_requires_credentials():
    with pytest.raises(ExecutionCredentialsError, match="credentials are required"):
        ClobRestPolymarketExecutor.from_env(env={})
