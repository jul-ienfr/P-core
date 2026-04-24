from __future__ import annotations

import threading

import pytest

from prediction_core.client import PredictionCoreClient, PredictionCoreClientError
from prediction_core.server import build_server


def _start_server() -> tuple[object, threading.Thread, int]:
    server = build_server(host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, server.server_address[1]


def test_client_health_returns_service_payload() -> None:
    server, thread, port = _start_server()
    client = PredictionCoreClient(f"http://127.0.0.1:{port}")
    try:
        payload = client.health()
        assert payload == {"status": "ok", "service": "prediction_core_python"}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_client_parse_market_returns_market_payload() -> None:
    server, thread, port = _start_server()
    client = PredictionCoreClient(f"http://127.0.0.1:{port}")
    try:
        payload = client.parse_market(question="Will the highest temperature in Denver be 64F or higher?")
        assert payload["city"] == "Denver"
        assert payload["measurement_kind"] == "high"
        assert payload["is_threshold"] is True
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_client_fetch_markets_returns_normalized_market_list() -> None:
    server, thread, port = _start_server()
    client = PredictionCoreClient(f"http://127.0.0.1:{port}")
    try:
        payload = client.fetch_markets(source="fixture", limit=2)
        assert len(payload) == 2
        assert payload[0]["id"] == "denver-high-64"
        assert payload[0]["spread"] == 0.03
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_client_score_market_raises_structured_error_for_bad_request() -> None:
    server, thread, port = _start_server()
    client = PredictionCoreClient(f"http://127.0.0.1:{port}")
    try:
        with pytest.raises(PredictionCoreClientError) as exc_info:
            client.score_market(question="Will the highest temperature in Denver be 64F or higher?")
        assert exc_info.value.status_code == 400
        assert exc_info.value.payload == {"status": "error", "message": "yes_price is required when using question"}
        assert "yes_price" in str(exc_info.value)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_client_paper_cycle_returns_simulation_bundle() -> None:
    server, thread, port = _start_server()
    client = PredictionCoreClient(f"http://127.0.0.1:{port}")
    try:
        payload = client.paper_cycle(
            run_id="run-client-1",
            market_id="market-denver-64f",
            question="Will the highest temperature in Denver be 64F or higher?",
            yes_price=0.53,
            requested_quantity=4,
        )
        assert payload["simulation"]["run_id"] == "run-client-1"
        assert payload["simulation"]["market_id"] == "market-denver-64f"
        assert payload["simulation"]["status"] == "filled"
        assert payload["score_bundle"]["decision"]["status"] == "trade_small"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_client_score_market_live_question_exposes_execution_costs_quote() -> None:
    server, thread, port = _start_server()
    client = PredictionCoreClient(f"http://127.0.0.1:{port}")
    try:
        payload = client.score_market(
            question="Will the highest temperature in Denver be 64F or higher?",
            yes_price=0.43,
            source="live",
            best_bid=0.42,
            best_ask=0.45,
            transaction_fee_bps=20.0,
            deposit_fee_usd=1.0,
            withdrawal_fee_usd=2.0,
            bids=[{"price": 0.42, "size": 200.0}],
            asks=[{"price": 0.45, "size": 100.0}, {"price": 0.46, "size": 150.0}],
            target_order_size_usd=40.0,
        )
        assert payload["execution"]["fillable_size_usd"] > 0
        assert payload["execution_costs"]["quoted_best_bid"] == 0.42
        assert payload["execution_costs"]["quoted_best_ask"] == 0.45
        assert payload["execution_costs"]["estimated_filled_quantity"] > 0
        assert payload["execution_costs"]["total_all_in_cost"] >= payload["execution_costs"]["total_execution_cost"]
        assert payload["execution_costs"]["effective_unit_price"] is not None
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_client_paper_cycle_live_question_embeds_execution_quote_metadata() -> None:
    server, thread, port = _start_server()
    client = PredictionCoreClient(f"http://127.0.0.1:{port}")
    try:
        payload = client.paper_cycle(
            run_id="run-client-live-1",
            market_id="market-denver-live-64f",
            question="Will the highest temperature in Denver be 64F or higher?",
            yes_price=0.43,
            source="live",
            requested_quantity=20.0,
            best_bid=0.42,
            best_ask=0.45,
            transaction_fee_bps=20.0,
            deposit_fee_usd=1.0,
            withdrawal_fee_usd=2.0,
            bids=[{"price": 0.42, "size": 200.0}],
            asks=[{"price": 0.45, "size": 100.0}, {"price": 0.46, "size": 150.0}],
        )
        execution = payload["simulation"]["metadata"]["execution"]
        assert execution["quoted_best_bid"] == 0.42
        assert execution["quoted_best_ask"] == 0.45
        assert execution["estimated_filled_quantity"] > 0
        assert execution["total_all_in_cost"] >= execution["total_execution_cost"]
        assert payload["simulation"]["fee_paid"] == round(
            execution["trading_fee_cost"] + execution["deposit_fee_cost"] + execution["withdrawal_fee_cost"],
            6,
        )
        assert payload["simulation"]["status"] in {"filled", "partial"}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
