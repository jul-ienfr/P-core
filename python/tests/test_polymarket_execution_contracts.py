import pytest

from prediction_core.polymarket_execution import (
    ClobRestPolymarketExecutor,
    DryRunPolymarketExecutor,
    ClobRestExecutorConfig,
    ExecutionCredentialsError,
    ExecutionMode,
    LiveExecutionGuardrailError,
    LiveExecutionUnavailableError,
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
    with pytest.raises(ValueError, match="limit_price must be finite and between 0 and 1"):
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
    with pytest.raises(ValueError, match="notional_usdc must be finite and positive"):
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
    assert executor.list_open_orders() == [{"id": "dry-run:k1", "status": "open", "idempotency_key": "k1", "token_id": "yes-token"}]
    assert result.raw_response["dry_run"] is True


def test_dry_run_cancel_is_recorded_but_never_submitted():
    executor = DryRunPolymarketExecutor()

    result = executor.cancel_order("ord-1")

    assert result.accepted is False
    assert result.status == "dry_run_cancel_not_submitted"
    assert executor.cancel_requests == ["ord-1"]
    assert result.raw_response["cancel_submitted"] is False


def test_clob_rest_executor_requires_credentials():
    with pytest.raises(ExecutionCredentialsError, match="credentials are required"):
        ClobRestPolymarketExecutor.from_env(env={})


def test_clob_rest_executor_requires_operator_guardrails_even_with_credentials():
    with pytest.raises(LiveExecutionGuardrailError, match="POLYMARKET_LIVE_ENABLED=1"):
        ClobRestPolymarketExecutor.from_env(
            env={
                "POLYMARKET_PRIVATE_KEY": "secret",
                "POLYMARKET_FUNDER_ADDRESS": "0xabc",
                "POLYMARKET_CHAIN_ID": "137",
                "POLYMARKET_MAX_ORDER_NOTIONAL_USDC": "10",
            },
            client=object(),
        )


def test_clob_rest_executor_respects_kill_switch():
    with pytest.raises(LiveExecutionGuardrailError, match="kill switch"):
        ClobRestPolymarketExecutor.from_env(
            env={
                "POLYMARKET_PRIVATE_KEY": "secret",
                "POLYMARKET_FUNDER_ADDRESS": "0xabc",
                "POLYMARKET_CHAIN_ID": "137",
                "POLYMARKET_LIVE_ENABLED": "1",
                "POLYMARKET_LIVE_ACK": "I_UNDERSTAND_THIS_SUBMITS_REAL_POLYMARKET_ORDERS",
                "POLYMARKET_MAX_ORDER_NOTIONAL_USDC": "10",
                "PREDICTION_CORE_DISABLE_LIVE_EXECUTION": "1",
            },
            client=object(),
        )


class FakeClobClient:
    def __init__(self):
        self.submitted = []

    def submit_order(self, payload):
        self.submitted.append(payload)
        return {"accepted": True, "status": "submitted", "order_id": "ord-1", "api_key": "must-redact"}

    def list_open_orders(self):
        return [{"id": "ord-open", "status": "open", "asset_id": "yes-token", "signature": "must-redact"}]


def _live_config():
    return ClobRestExecutorConfig(
        private_key="secret",
        funder_address="0xabc",
        chain_id=137,
        live_enabled=True,
        live_ack="I_UNDERSTAND_THIS_SUBMITS_REAL_POLYMARKET_ORDERS",
        allow_order_submission=True,
        max_order_notional_usdc=10,
    )


def test_clob_rest_executor_submits_limit_buy_with_injected_client_and_sanitizes_response():
    client = FakeClobClient()
    executor = ClobRestPolymarketExecutor(config=_live_config(), client=client)
    order = OrderRequest(market_id="m1", token_id="yes-token", outcome="Yes", side="buy", order_type="limit", limit_price=0.5, notional_usdc=5, idempotency_key="k1")

    result = executor.submit_order(order)

    assert result.accepted is True
    assert result.status == "submitted"
    assert result.exchange_order_id == "ord-1"
    assert client.submitted == [{"token_id": "yes-token", "price": 0.5, "size": 10.0, "side": "BUY", "order_type": "LIMIT"}]
    assert result.raw_response["response"]["api_key"] == "[redacted]"
    assert "secret" not in str(result.raw_response)


def test_clob_rest_executor_lists_open_orders_read_only_and_redacts_sensitive_fields():
    executor = ClobRestPolymarketExecutor(config=_live_config(), client=FakeClobClient())

    assert executor.list_open_orders() == [{"id": "ord-open", "status": "open", "asset_id": "yes-token", "signature": "[redacted]"}]


def test_clob_rest_executor_rejects_unsupported_live_order_shapes():
    executor = ClobRestPolymarketExecutor(config=_live_config(), client=FakeClobClient())
    sell_order = OrderRequest(market_id="m1", token_id="yes-token", outcome="Yes", side="sell", order_type="limit", limit_price=0.5, notional_usdc=5, idempotency_key="k1")
    oversized = OrderRequest(market_id="m1", token_id="yes-token", outcome="Yes", side="buy", order_type="limit", limit_price=0.5, notional_usdc=11, idempotency_key="k2")

    with pytest.raises(LiveExecutionGuardrailError, match="only supports buy"):
        executor.submit_order(sell_order)
    with pytest.raises(LiveExecutionGuardrailError, match="exceeds"):
        executor.submit_order(oversized)


def test_clob_rest_order_management_keeps_cancel_fail_closed():
    executor = ClobRestPolymarketExecutor(config=_live_config(), client=FakeClobClient())

    with pytest.raises(LiveExecutionUnavailableError, match="cancel requires"):
        executor.cancel_order("ord-1")
