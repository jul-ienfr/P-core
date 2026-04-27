from prediction_core.polymarket_execution import reconcile_orders


def test_reconcile_orders_detects_missing_exchange_order():
    local = [{"exchange_order_id": "ord-1", "token_id": "t", "notional_usdc": 5.0}]
    exchange = []

    result = reconcile_orders(local_orders=local, exchange_orders=exchange)

    assert result["missing_on_exchange"] == ["ord-1"]
    assert result["unexpected_on_exchange"] == []
    assert result["ok"] is False


def test_reconcile_orders_passes_matching_order_ids():
    local = [{"exchange_order_id": "ord-1", "token_id": "t", "status": "submitted"}]
    exchange = [{"id": "ord-1", "token_id": "t", "status": "submitted"}]

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
    assert result["status"] == "critical"


def test_reconcile_orders_reports_open_partial_status_and_duplicates():
    local = [
        {"exchange_order_id": "ord-1", "status": "filled", "token_id": "t"},
        {"exchange_order_id": "ord-1", "status": "filled", "token_id": "t"},
    ]
    exchange = [
        {"id": "ord-1", "status": "partially_filled", "filled_size": "2.5", "token_id": "t"},
        {"id": "ord-2", "status": "open", "token_id": "t"},
        {"id": "ord-2", "status": "open", "token_id": "t"},
    ]

    result = reconcile_orders(local_orders=local, exchange_orders=exchange)

    assert result["status"] == "critical"
    assert result["severity"] == "critical"
    assert result["open_order_ids"] == ["ord-1", "ord-2"]
    assert result["partial_fill_order_ids"] == ["ord-1"]
    assert result["status_mismatches"] == [{"exchange_order_id": "ord-1", "local_status": "filled", "exchange_status": "partially_filled"}]
    assert result["duplicate_local_order_ids"] == ["ord-1"]
    assert result["duplicate_exchange_order_ids"] == ["ord-2"]


def test_reconcile_orders_warns_on_confirmed_open_orders():
    result = reconcile_orders(local_orders=[{"exchange_order_id": "ord-1", "status": "submitted"}], exchange_orders=[{"id": "ord-1", "status": "open"}])

    assert result["ok"] is False
    assert result["status"] == "warning"
    assert result["open_order_ids"] == ["ord-1"]


def test_reconcile_orders_detects_field_mismatches_when_fields_are_present():
    local = [
        {
            "exchange_order_id": "ord-1",
            "status": "submitted",
            "token_id": "local-token",
            "side": "BUY",
            "limit_price": 0.44,
            "notional_usdc": 5.0,
        }
    ]
    exchange = [
        {
            "id": "ord-1",
            "status": "submitted",
            "token_id": "exchange-token",
            "side": "sell",
            "price": "0.45",
            "size": "6.0",
        }
    ]

    result = reconcile_orders(local_orders=local, exchange_orders=exchange)

    assert result["status"] == "critical"
    assert result["field_mismatches"] == [
        {"exchange_order_id": "ord-1", "field": "token_id", "local": "local-token", "exchange": "exchange-token"},
        {"exchange_order_id": "ord-1", "field": "side", "local": "buy", "exchange": "sell"},
        {"exchange_order_id": "ord-1", "field": "limit_price", "local": 0.44, "exchange": 0.45},
        {"exchange_order_id": "ord-1", "field": "notional", "local": 5.0, "exchange": 6.0},
    ]


def test_reconcile_orders_does_not_mark_filled_order_as_partial_without_total_size():
    result = reconcile_orders(
        local_orders=[{"exchange_order_id": "ord-1", "status": "filled"}],
        exchange_orders=[{"id": "ord-1", "status": "filled", "filled_size": "2.5"}],
    )

    assert result["partial_fill_order_ids"] == []
    assert result["status"] == "ok"


def test_reconcile_orders_marks_filled_order_partial_when_total_size_is_larger():
    result = reconcile_orders(
        local_orders=[{"exchange_order_id": "ord-1", "status": "filled"}],
        exchange_orders=[{"id": "ord-1", "status": "filled", "filled_size": "2.5", "size": "5.0"}],
    )

    assert result["partial_fill_order_ids"] == ["ord-1"]
    assert result["status"] == "warning"
