from __future__ import annotations

from tests.test_server_smoke import _json_request, _start_server


def test_paper_cycle_derives_cost_model_fields_from_book_and_fee_schedule() -> None:
    server, thread, port = _start_server()
    try:
        status, payload = _json_request(
            f"http://127.0.0.1:{port}/weather/paper-cycle",
            method="POST",
            payload={
                "run_id": "run-cost-model-1",
                "market_id": "market-denver-64f",
                "question": "Will the highest temperature in Denver be 64F or higher?",
                "yes_price": 0.53,
                "requested_quantity": 15,
                "asks": [
                    {"price": 0.53, "size": 10},
                    {"price": 0.55, "size": 10},
                ],
                "bids": [
                    {"price": 0.50, "size": 20},
                ],
                "taker_fee_bps": 50,
                "deposit_fee_usd": 1.0,
                "deposit_fee_bps": 10,
                "withdrawal_fee_usd": 2.0,
                "withdrawal_fee_bps": 20,
            },
        )

        assert status == 200
        assert payload["simulation"]["status"] == "filled"
        assert payload["simulation"]["filled_quantity"] == 15.0
        assert payload["simulation"]["average_fill_price"] == 0.536667
        assert payload["simulation"]["fee_paid"] == 3.0644
        assert payload["simulation"]["slippage_bps"] == 125.79

        postmortem = payload["postmortem"]
        assert postmortem["fee_paid"] == 3.0644
        assert postmortem["slippage_bps"] == 125.79
        assert postmortem["effective_price_after_fees"] == 0.74096

        execution = payload["simulation"]["metadata"]["execution"]
        assert execution["estimated_avg_fill_price"] == 0.536667
        assert execution["book_slippage_cost"] == 0.1
        assert execution["trading_fee_cost"] == 0.04025
        assert execution["deposit_fee_cost"] == 1.00805
        assert execution["withdrawal_fee_cost"] == 2.0161
        assert execution["total_execution_cost"] == 0.36525
        assert execution["total_all_in_cost"] == 3.3894
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
