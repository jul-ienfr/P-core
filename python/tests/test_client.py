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