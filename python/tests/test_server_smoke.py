from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

from prediction_core.server import build_server


def _start_server() -> tuple[object, threading.Thread, int]:
    server = build_server(host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, server.server_address[1]


def _json_request(url: str, *, method: str = "GET", payload: dict | None = None) -> tuple[int, dict]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def test_health_endpoint_returns_ok() -> None:
    server, thread, port = _start_server()
    try:
        status, payload = _json_request(f"http://127.0.0.1:{port}/health")
        assert status == 200
        assert payload["status"] == "ok"
        assert payload["service"] == "prediction_core_python"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_parse_market_endpoint_returns_parsed_market_json() -> None:
    server, thread, port = _start_server()
    try:
        status, payload = _json_request(
            f"http://127.0.0.1:{port}/weather/parse-market",
            method="POST",
            payload={"question": "Will the highest temperature in Denver be 64F or higher?"},
        )
        assert status == 200
        assert payload["city"] == "Denver"
        assert payload["measurement_kind"] == "high"
        assert payload["is_threshold"] is True
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_score_market_endpoint_rejects_invalid_request_payload() -> None:
    server, thread, port = _start_server()
    try:
        status, payload = _json_request(
            f"http://127.0.0.1:{port}/weather/score-market",
            method="POST",
            payload={"question": "Will the highest temperature in Denver be 64F or higher?"},
        )
        assert status == 400
        assert payload["status"] == "error"
        assert "yes_price" in payload["message"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_fetch_markets_endpoint_returns_normalized_weather_market_list() -> None:
    server, thread, port = _start_server()
    try:
        status, payload = _json_request(
            f"http://127.0.0.1:{port}/weather/fetch-markets",
            method="POST",
            payload={"source": "fixture", "limit": 2},
        )
        assert status == 200
        assert len(payload["markets"]) == 2
        assert payload["markets"][0]["id"] == "denver-high-64"
        assert payload["markets"][0]["spread"] == 0.03
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_paper_cycle_endpoint_returns_simulation_and_postmortem() -> None:
    server, thread, port = _start_server()
    try:
        status, payload = _json_request(
            f"http://127.0.0.1:{port}/weather/paper-cycle",
            method="POST",
            payload={
                "run_id": "run-http-1",
                "market_id": "market-denver-64f",
                "requested_quantity": 4,
                "filled_quantity": 3,
                "fill_price": 0.53,
                "reference_price": 0.5,
                "fee_paid": 0.01,
            },
        )
        assert status == 200
        assert payload["simulation"]["run_id"] == "run-http-1"
        assert payload["simulation"]["market_id"] == "market-denver-64f"
        assert payload["simulation"]["status"] == "partial"
        assert payload["simulation"]["average_fill_price"] == 0.53
        assert payload["postmortem"]["fill_rate"] == 0.75
        assert payload["postmortem"]["recommendation"] == "reduce_size"
        assert payload["score_bundle"] is None
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_paper_cycle_endpoint_returns_scoring_bundle_when_question_and_yes_price_are_provided() -> None:
    server, thread, port = _start_server()
    try:
        status, payload = _json_request(
            f"http://127.0.0.1:{port}/weather/paper-cycle",
            method="POST",
            payload={
                "run_id": "run-http-2",
                "market_id": "market-denver-64f",
                "question": "Will the highest temperature in Denver be 64F or higher?",
                "yes_price": 0.53,
                "requested_quantity": 4,
                "filled_quantity": 4,
                "fill_price": 0.53,
            },
        )
        assert status == 200
        assert payload["simulation"]["status"] == "filled"
        assert payload["score_bundle"]["market"]["city"] == "Denver"
        assert payload["score_bundle"]["score"]["grade"] == "B"
        assert payload["score_bundle"]["decision"]["status"] == "trade_small"
        assert payload["postmortem"]["recommendation"] == "reprice"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_paper_cycle_endpoint_derives_fill_from_trade_small_decision() -> None:
    server, thread, port = _start_server()
    try:
        status, payload = _json_request(
            f"http://127.0.0.1:{port}/weather/paper-cycle",
            method="POST",
            payload={
                "run_id": "run-http-4",
                "market_id": "market-denver-64f",
                "question": "Will the highest temperature in Denver be 64F or higher?",
                "yes_price": 0.53,
                "requested_quantity": 4,
            },
        )
        assert status == 200
        assert payload["score_bundle"]["decision"]["status"] == "trade_small"
        assert payload["simulation"]["status"] == "filled"
        assert payload["simulation"]["filled_quantity"] == 4.0
        assert payload["simulation"]["average_fill_price"] == 0.53
        assert payload["postmortem"]["fill_rate"] == 1.0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_paper_cycle_endpoint_derives_skip_when_decision_is_not_tradeable() -> None:
    server, thread, port = _start_server()
    try:
        status, payload = _json_request(
            f"http://127.0.0.1:{port}/weather/paper-cycle",
            method="POST",
            payload={
                "run_id": "run-http-5",
                "market_id": "market-denver-64f",
                "question": "Will the highest temperature in Denver be 64F or higher?",
                "yes_price": 0.63,
                "requested_quantity": 4,
            },
        )
        assert status == 200
        assert payload["score_bundle"]["decision"]["status"] == "skip"
        assert payload["simulation"]["status"] == "skipped"
        assert payload["simulation"]["filled_quantity"] == 0.0
        assert payload["postmortem"]["recommendation"] == "no_trade"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_paper_cycle_endpoint_derives_requested_quantity_from_bankroll_and_decision() -> None:
    server, thread, port = _start_server()
    try:
        status, payload = _json_request(
            f"http://127.0.0.1:{port}/weather/paper-cycle",
            method="POST",
            payload={
                "run_id": "run-http-6",
                "market_id": "market-denver-64f",
                "question": "Will the highest temperature in Denver be 64F or higher?",
                "yes_price": 0.53,
                "bankroll_usd": 1000,
            },
        )
        assert status == 200
        assert payload["score_bundle"]["decision"]["status"] == "trade_small"
        assert payload["simulation"]["requested_quantity"] == 18.867925
        assert payload["simulation"]["filled_quantity"] == 18.867925
        assert payload["simulation"]["gross_notional"] == 10.0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_paper_cycle_endpoint_derives_zero_requested_quantity_when_decision_skips() -> None:
    server, thread, port = _start_server()
    try:
        status, payload = _json_request(
            f"http://127.0.0.1:{port}/weather/paper-cycle",
            method="POST",
            payload={
                "run_id": "run-http-7",
                "market_id": "market-denver-64f",
                "question": "Will the highest temperature in Denver be 64F or higher?",
                "yes_price": 0.63,
                "bankroll_usd": 1000,
            },
        )
        assert status == 200
        assert payload["score_bundle"]["decision"]["status"] == "skip"
        assert payload["simulation"]["requested_quantity"] == 0.0
        assert payload["simulation"]["filled_quantity"] == 0.0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_paper_cycle_endpoint_prefers_explicit_requested_quantity_over_bankroll() -> None:
    server, thread, port = _start_server()
    try:
        status, payload = _json_request(
            f"http://127.0.0.1:{port}/weather/paper-cycle",
            method="POST",
            payload={
                "run_id": "run-http-8",
                "market_id": "market-denver-64f",
                "question": "Will the highest temperature in Denver be 64F or higher?",
                "yes_price": 0.53,
                "requested_quantity": 4,
                "bankroll_usd": 1000,
            },
        )
        assert status == 200
        assert payload["score_bundle"]["decision"]["status"] == "trade_small"
        assert payload["simulation"]["requested_quantity"] == 4.0
        assert payload["simulation"]["filled_quantity"] == 4.0
        assert payload["simulation"]["gross_notional"] == 2.12
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_paper_cycle_endpoint_rejects_missing_run_id() -> None:
    server, thread, port = _start_server()
    try:
        status, payload = _json_request(
            f"http://127.0.0.1:{port}/weather/paper-cycle",
            method="POST",
            payload={
                "market_id": "market-denver-64f",
                "requested_quantity": 4,
                "filled_quantity": 4,
                "fill_price": 0.53,
            },
        )
        assert status == 400
        assert payload["status"] == "error"
        assert "run_id" in payload["message"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_paper_cycle_endpoint_rejects_yes_price_without_question() -> None:
    server, thread, port = _start_server()
    try:
        status, payload = _json_request(
            f"http://127.0.0.1:{port}/weather/paper-cycle",
            method="POST",
            payload={
                "run_id": "run-http-3",
                "market_id": "market-denver-64f",
                "yes_price": 0.53,
                "requested_quantity": 4,
                "filled_quantity": 4,
                "fill_price": 0.53,
            },
        )
        assert status == 400
        assert payload["status"] == "error"
        assert "question" in payload["message"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_paper_cycle_endpoint_applies_cost_inputs_to_score_bundle_and_auto_fee_paid() -> None:
    server, thread, port = _start_server()
    try:
        status, payload = _json_request(
            f"http://127.0.0.1:{port}/weather/paper-cycle",
            method="POST",
            payload={
                "run_id": "run-http-costs",
                "market_id": "market-denver-64f",
                "question": "Will the highest temperature in Denver be 64F or higher?",
                "yes_price": 0.53,
                "requested_quantity": 10,
                "best_bid": 0.5,
                "best_ask": 0.52,
                "volume": 6000,
                "target_order_size_usd": 80,
                "taker_fee_bps": 90,
                "deposit_fee_usd": 1.5,
                "withdrawal_fee_usd": 2.0,
                "bids": [
                    {"price": 0.5, "size": 100},
                    {"price": 0.49, "size": 80},
                ],
                "asks": [
                    {"price": 0.52, "size": 120},
                    {"price": 0.54, "size": 40},
                ],
            },
        )
        assert status == 200
        assert payload["score_bundle"]["execution"]["deposit_fee_usd"] == 1.5
        assert payload["score_bundle"]["execution"]["withdrawal_fee_usd"] == 2.0
        assert payload["score_bundle"]["execution"]["order_book_depth_usd"] == 84.0
        assert payload["score_bundle"]["execution"]["all_in_cost_bps"] == 577.5
        assert payload["simulation"]["fee_paid"] == 3.547
        assert payload["simulation"]["metadata"]["execution_costs"]["all_in_cost_bps"] == 577.5
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
