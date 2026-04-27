from prediction_core.polymarket_execution import reconcile_orders


def test_reconcile_orders_detects_missing_exchange_order():
    local = [{"exchange_order_id": "ord-1", "token_id": "t", "notional_usdc": 5.0}]
    exchange = []

    result = reconcile_orders(local_orders=local, exchange_orders=exchange)

    assert result["missing_on_exchange"] == ["ord-1"]
    assert result["unexpected_on_exchange"] == []
    assert result["ok"] is False


def test_reconcile_orders_passes_matching_order_ids():
    local = [{"exchange_order_id": "ord-1", "token_id": "t"}]
    exchange = [{"id": "ord-1", "token_id": "t"}]

    result = reconcile_orders(local_orders=local, exchange_orders=exchange)

    assert result["ok"] is True
    assert result["missing_on_exchange"] == []
    assert result["unexpected_on_exchange"] == []


def test_reconcile_orders_detects_unexpected_exchange_order_with_order_id_alias():
    local = []
    exchange = [{"order_id": "ord-2", "token_id": "t"}]

    result = reconcile_orders(local_orders=local, exchange_orders=exchange)

    assert result["ok"] is False
    assert result["unexpected_on_exchange"] == ["ord-2"]
