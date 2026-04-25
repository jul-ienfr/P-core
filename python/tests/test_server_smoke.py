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


def test_score_market_endpoint_returns_resolution_source_route_for_direct_station_source() -> None:
    server, thread, port = _start_server()
    try:
        status, payload = _json_request(
            f"http://127.0.0.1:{port}/weather/score-market",
            method="POST",
            payload={
                "question": "Will the highest temperature in Denver be 64F or higher?",
                "yes_price": 0.43,
                "resolution_source": "Resolution source: NOAA daily climate report for station KDEN",
                "description": "Official observed high temperature at Denver International Airport station KDEN.",
                "rules": "Source: https://www.weather.gov/wrh/climate?wfo=bou station KDEN.",
            },
        )
        assert status == 200
        assert payload["resolution"]["provider"] == "noaa"
        assert payload["source_route"]["station_code"] == "KDEN"
        assert payload["source_route"]["direct"] is True
        assert payload["source_route"]["latest_url"] == "https://api.weather.gov/stations/KDEN/observations/latest"
        assert payload["source_route"]["latency_tier"] == "direct_latest"
        assert payload["source_route"]["polling_focus"] == "station_observations_latest"
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


def test_polymarket_weather_markets_get_endpoint_returns_normalized_markets() -> None:
    server, thread, port = _start_server()
    try:
        status, payload = _json_request(
            f"http://127.0.0.1:{port}/weather/polymarket/markets?source=fixture&limit=2",
        )
        assert status == 200
        assert payload["source"] == "fixture"
        assert len(payload["markets"]) == 2
        assert payload["markets"][0]["id"] == "denver-high-64"
        assert payload["markets"][0]["question"] == "Will the highest temperature in Denver be 64F or higher?"
        assert payload["markets"][0]["spread"] == 0.03
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_polymarket_weather_markets_get_endpoint_rejects_invalid_source() -> None:
    server, thread, port = _start_server()
    try:
        status, payload = _json_request(
            f"http://127.0.0.1:{port}/weather/polymarket/markets?source=bad&limit=2",
        )
        assert status == 400
        assert payload["status"] == "error"
        assert payload["message"] == "source must be 'fixture' or 'live'"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_polymarket_weather_markets_get_endpoint_rejects_non_positive_limit() -> None:
    server, thread, port = _start_server()
    try:
        status, payload = _json_request(
            f"http://127.0.0.1:{port}/weather/polymarket/markets?source=fixture&limit=0",
        )
        assert status == 400
        assert payload["status"] == "error"
        assert payload["message"] == "limit must be >= 1"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_station_history_endpoint_fetches_direct_resolution_station_history() -> None:
    from unittest.mock import patch

    from weather_pm.models import StationHistoryBundle, StationHistoryPoint

    market = {
        "id": "404359",
        "question": "Lowest temperature in Miami on April 23?",
        "resolution_source": "https://www.wunderground.com/history/daily/us/fl/miami/KMIA",
        "description": "This market resolves to the lowest temperature recorded at the Miami Intl Airport Station in degrees Fahrenheit on 23 Apr '26.",
        "rules": "This market resolves based on the final daily observation published at the resolution source.",
    }
    history = StationHistoryBundle(
        source_provider="wunderground",
        station_code="KMIA",
        source_url="https://www.wunderground.com/history/daily/us/fl/miami/KMIA/date/2026-04-23",
        latency_tier="direct",
        points=[StationHistoryPoint(timestamp="2026-04-23 06:53", value=71.0, unit="f")],
        summary={"min": 71.0, "max": 71.0, "mean": 71.0},
    )

    with patch("weather_pm.cli.get_market_by_id", return_value=market), patch(
        "weather_pm.cli.build_station_history_bundle", return_value=history
    ):
        server, thread, port = _start_server()
        try:
            status, payload = _json_request(
                f"http://127.0.0.1:{port}/weather/station-history",
                method="POST",
                payload={"market_id": "404359", "source": "live", "start_date": "2026-04-23", "end_date": "2026-04-23"},
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    assert status == 200
    assert payload["resolution"]["station_code"] == "KMIA"
    assert payload["history"]["latency_tier"] == "direct"
    assert payload["history"]["source_url"].endswith("/KMIA/date/2026-04-23")
    assert payload["history"]["summary"]["min"] == 71.0
    assert payload["history"]["latest"] == {"timestamp": "2026-04-23 06:53", "value": 71.0, "unit": "f"}
    assert payload["latency"]["direct"] is True
    assert payload["latency"]["latest_value"] == 71.0
    assert payload["latency"]["latest_timestamp"] == "2026-04-23 06:53"


def test_station_history_endpoint_rejects_missing_market_id() -> None:
    server, thread, port = _start_server()
    try:
        status, payload = _json_request(
            f"http://127.0.0.1:{port}/weather/station-history",
            method="POST",
            payload={"source": "live", "start_date": "2026-04-23", "end_date": "2026-04-23"},
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert status == 400
    assert payload["status"] == "error"
    assert payload["message"] == "market_id is required"


def test_station_latest_endpoint_fetches_latest_direct_resolution_station_observation() -> None:
    from unittest.mock import patch

    from weather_pm.models import StationHistoryBundle, StationHistoryPoint

    latest = StationHistoryBundle(
        source_provider="noaa",
        station_code="KDEN",
        source_url="https://api.weather.gov/stations/KDEN/observations/latest",
        latency_tier="direct_latest",
        points=[StationHistoryPoint(timestamp="2026-04-25T21:53:00+00:00", value=68.0, unit="f")],
        summary={"min": 68.0, "max": 68.0, "mean": 68.0},
    )

    with patch("prediction_core.server.station_latest_for_market_id", return_value={"latest": latest.latest().to_dict(), "latency": latest.latency_diagnostics()}):
        server, thread, port = _start_server()
        try:
            status, payload = _json_request(
                f"http://127.0.0.1:{port}/weather/station-latest",
                method="POST",
                payload={"market_id": "denver-latest", "source": "live"},
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    assert status == 200
    assert payload["latest"] == {"timestamp": "2026-04-25T21:53:00+00:00", "value": 68.0, "unit": "f"}
    assert payload["latency"]["tier"] == "direct_latest"
    assert payload["latency"]["latest_value"] == 68.0


def test_source_coverage_endpoint_returns_integrated_weather_source_inventory() -> None:
    server, thread, port = _start_server()
    try:
        status, payload = _json_request(
            f"http://127.0.0.1:{port}/weather/source-coverage",
            method="POST",
            payload={},
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert status == 200
    assert payload["provider_count"] >= 50
    assert "noaa" in payload["direct_low_latency"]
    assert "weather_com" in payload["manual_review_only"]
    assert any("not literally exhaustive" in caveat for caveat in payload["caveats"])


def test_station_source_plan_endpoint_exposes_best_direct_station_source_plan() -> None:
    from unittest.mock import patch

    expected = {
        "market_id": "denver-high-64",
        "source": "fixture",
        "station_binding": {
            "exact_station_match": True,
            "latest_candidates": [{"url": "https://api.weather.gov/stations/KDEN/observations/latest"}],
        },
        "source_selection": {
            "best_latest": {"provider": "noaa", "station_code": "KDEN", "source_lag_seconds": 300},
            "best_final": {"provider": "noaa", "polling_focus": "noaa_official_daily_summary"},
            "operator_action": "poll_best_latest_station_until_threshold_then_confirm_with_official_final",
        },
    }

    with patch("prediction_core.server.station_source_plan_for_market_id", return_value=expected) as plan_mock:
        server, thread, port = _start_server()
        try:
            status, payload = _json_request(
                f"http://127.0.0.1:{port}/weather/station-source-plan",
                method="POST",
                payload={"market_id": "denver-high-64", "source": "fixture", "start_date": "2026-04-25", "end_date": "2026-04-25"},
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    assert status == 200
    assert payload == expected
    plan_mock.assert_called_once_with("denver-high-64", source="fixture", start_date="2026-04-25", end_date="2026-04-25")


def test_station_source_plan_endpoint_rejects_missing_market_id() -> None:
    server, thread, port = _start_server()
    try:
        status, payload = _json_request(
            f"http://127.0.0.1:{port}/weather/station-source-plan",
            method="POST",
            payload={"source": "fixture", "start_date": "2026-04-25", "end_date": "2026-04-25"},
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert status == 400
    assert payload["status"] == "error"
    assert payload["message"] == "market_id is required"


def test_resolution_status_endpoint_returns_resolution_status_envelope() -> None:
    from unittest.mock import patch

    expected = {
        "market_id": "hko-high-29",
        "latest_direct": {"available": True, "value": 29.2, "timestamp": "2026-04-25T15:45:00+08:00", "latency_tier": "direct_latest"},
        "official_daily_extract": {"available": False, "value": None, "timestamp": None, "latency_tier": "direct_history"},
        "confirmed_outcome": "pending",
        "action_operator": "monitor_until_official_daily_extract",
    }

    with patch("prediction_core.server.resolution_status_for_market_id", return_value=expected) as status_mock:
        server, thread, port = _start_server()
        try:
            status, payload = _json_request(
                f"http://127.0.0.1:{port}/weather/resolution-status",
                method="POST",
                payload={"market_id": "hko-high-29", "source": "live", "date": "2026-04-25"},
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    assert status == 200
    assert payload == expected
    status_mock.assert_called_once_with("hko-high-29", source="live", date="2026-04-25")


def test_resolution_status_endpoint_rejects_missing_date() -> None:
    server, thread, port = _start_server()
    try:
        status, payload = _json_request(
            f"http://127.0.0.1:{port}/weather/resolution-status",
            method="POST",
            payload={"market_id": "hko-high-29", "source": "live"},
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert status == 400
    assert payload["status"] == "error"
    assert payload["message"] == "date is required"


def test_monitor_paper_resolution_endpoint_persists_paper_only_artifacts() -> None:
    from unittest.mock import patch

    expected = {
        "mode": "paper_only",
        "market_id": "hko-high-29",
        "source": "live",
        "settlement_date": "2026-04-25",
        "paper_trade": {"side": "yes", "notional_usd": 5.0, "shares": 17.24},
        "should_repoll": True,
        "cron_repoll": {"schedule": "every 2h", "repeat": 24, "prompt": "self-contained prompt"},
        "artifacts": {
            "raw_status_json": "/tmp/weather-monitor/weather_paper_hko-high-29_resolution_marketdate_20260425.json",
            "operator_monitor_md": "/tmp/weather-monitor/weather_paper_hko-high-29_monitor_latest.md",
        },
        "status": {"confirmed_outcome": "pending"},
    }

    with patch("prediction_core.server.write_paper_resolution_monitor", return_value=expected) as monitor_mock:
        server, thread, port = _start_server()
        try:
            status, payload = _json_request(
                f"http://127.0.0.1:{port}/weather/monitor-paper-resolution",
                method="POST",
                payload={
                    "market_id": "hko-high-29",
                    "source": "live",
                    "date": "2026-04-25",
                    "paper_side": "yes",
                    "paper_notional_usd": 5,
                    "paper_shares": 17.24,
                    "output_dir": "/tmp/weather-monitor",
                },
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    assert status == 200
    assert payload == expected
    monitor_mock.assert_called_once_with(
        market_id="hko-high-29",
        source="live",
        settlement_date="2026-04-25",
        paper_side="yes",
        paper_notional_usd=5.0,
        paper_shares=17.24,
        output_dir="/tmp/weather-monitor",
    )


def test_monitor_paper_resolution_endpoint_rejects_missing_paper_side() -> None:
    server, thread, port = _start_server()
    try:
        status, payload = _json_request(
            f"http://127.0.0.1:{port}/weather/monitor-paper-resolution",
            method="POST",
            payload={"market_id": "hko-high-29", "source": "live", "date": "2026-04-25"},
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert status == 400
    assert payload["status"] == "error"
    assert payload["message"] == "paper_side is required"


def test_live_paper_cycle_overfetches_to_fill_limit_after_pre_filtering() -> None:
    from unittest.mock import patch

    from prediction_core.server import paper_cycle_request

    markets = [
        {
            "id": "expired-1",
            "question": "Will the highest temperature in Denver be 60F or higher?",
            "yes_price": 0.50,
            "best_bid": 0.49,
            "best_ask": 0.51,
            "volume": 14000.0,
            "hours_to_resolution": -1.0,
        },
        {
            "id": "quoted-1",
            "question": "Will the highest temperature in Denver be 61F or higher?",
            "yes_price": 0.43,
            "best_bid": 0.42,
            "best_ask": 0.45,
            "volume": 14000.0,
            "hours_to_resolution": 12.0,
        },
        {
            "id": "quoted-2",
            "question": "Will the highest temperature in Denver be 62F or higher?",
            "yes_price": 0.44,
            "best_bid": 0.43,
            "best_ask": 0.46,
            "volume": 14000.0,
            "hours_to_resolution": 12.0,
        },
    ]
    score_bundles = {
        market_id: {
            "score": {"edge_theoretical": 0.57},
            "decision": {"status": "skip", "max_position_pct_bankroll": 0.0},
            "execution": {},
        }
        for market_id in {"quoted-1", "quoted-2"}
    }

    def fake_score(market_id: str, *, source: str, max_impact_bps: float | None = None) -> dict:
        assert source == "live"
        return score_bundles[market_id]

    with patch("prediction_core.server.list_weather_markets", return_value=markets) as list_mock, patch(
        "prediction_core.server._score_market_from_market_id", side_effect=fake_score
    ) as score_mock:
        payload = paper_cycle_request({"run_id": "run-live-fill", "source": "live", "limit": 2, "bankroll_usd": 1000})

    assert list_mock.call_args.kwargs["limit"] > 2
    assert [call.args[0] for call in score_mock.call_args_list] == ["quoted-1", "quoted-2"]
    assert payload["summary"]["selected"] == 2
    assert payload["summary"]["raw_candidates"] == 3
    assert payload["summary"]["fetch_limit"] == list_mock.call_args.kwargs["limit"]
    assert payload["summary"]["pre_filtered"] == 1



def test_live_paper_cycle_scores_quoted_unresolved_markets_and_only_trades_tradeable_decisions() -> None:
    from unittest.mock import patch

    from prediction_core.server import paper_cycle_request

    markets = [
        {
            "id": "live-trade",
            "question": "Will the highest temperature in Denver be 64F or higher?",
            "yes_price": 0.43,
            "best_bid": 0.42,
            "best_ask": 0.45,
            "volume": 14000.0,
            "hours_to_resolution": 12.0,
        },
        {
            "id": "live-skip",
            "question": "Will the highest temperature in Denver be 65F or higher?",
            "yes_price": 0.67,
            "best_bid": 0.66,
            "best_ask": 0.68,
            "volume": 14000.0,
            "hours_to_resolution": 12.0,
        },
        {
            "id": "live-resolved",
            "question": "Will the highest temperature in Denver be 66F or higher?",
            "yes_price": 0.50,
            "best_bid": 0.49,
            "best_ask": 0.51,
            "volume": 14000.0,
            "hours_to_resolution": -1.0,
        },
        {
            "id": "live-unquoted",
            "question": "Will the highest temperature in Denver be 67F or higher?",
            "yes_price": 0.0,
            "best_bid": 0.0,
            "best_ask": 0.0,
            "volume": 14000.0,
            "hours_to_resolution": 12.0,
        },
        {
            "id": "live-wide-spread",
            "question": "Will the highest temperature in Denver be 68F or higher?",
            "yes_price": 0.51,
            "best_bid": 0.01,
            "best_ask": 1.0,
            "spread": 1.0,
            "order_book_depth_usd": 0.25,
            "volume": 14000.0,
            "hours_to_resolution": 12.0,
        },
        {
            "id": "live-wide-bid-ask",
            "question": "Will the highest temperature in Denver be 69F or higher?",
            "yes_price": 0.003,
            "best_bid": 0.001,
            "best_ask": 0.999,
            "volume": 14000.0,
            "hours_to_resolution": 12.0,
        },
    ]
    score_bundles = {
        "live-trade": {
            "score": {"edge_theoretical": 0.57},
            "decision": {"status": "trade_small", "max_position_pct_bankroll": 0.01},
            "execution": {},
        },
        "live-skip": {
            "score": {"edge_theoretical": 0.57},
            "decision": {"status": "skip", "max_position_pct_bankroll": 0.0},
            "execution": {},
        },
    }

    def fake_score(market_id: str, *, source: str, max_impact_bps: float | None = None) -> dict:
        assert source == "live"
        return score_bundles[market_id]

    with patch("prediction_core.server.list_weather_markets", return_value=markets), patch(
        "prediction_core.server._score_market_from_market_id", side_effect=fake_score
    ) as score_mock:
        payload = paper_cycle_request({"run_id": "run-live-1", "source": "live", "limit": 4, "bankroll_usd": 1000})

    assert [call.args[0] for call in score_mock.call_args_list] == ["live-trade", "live-skip"]
    assert payload["summary"] == {
        "selected": 2,
        "raw_candidates": 6,
        "fetch_limit": 12,
        "scored": 2,
        "scoreable": 2,
        "traded": 1,
        "skipped": 1,
        "skipped_reasons": {
            "decision_not_tradeable": 1,
        },
        "pre_filtered": 4,
        "pre_filter_reasons": {
            "market_already_resolving_or_resolved": 1,
            "missing_tradeable_quote": 1,
            "insufficient_executable_depth": 2,
        },
    }
    by_id = {item["market_id"]: item for item in payload["markets"]}
    assert by_id["live-trade"]["decision_status"] == "trade_small"
    assert by_id["live-trade"]["simulation"]["status"] == "filled"
    assert by_id["live-trade"]["simulation_status"] == "filled"
    assert by_id["live-trade"]["traded"] is True
    assert by_id["live-trade"]["scoreable"] is True
    assert by_id["live-trade"]["postmortem"]["recommendation"] in {"hold", "reprice"}
    assert by_id["live-trade"]["postmortem_recommendation"] in {"hold", "reprice"}
    assert by_id["live-skip"]["decision_status"] == "skip"
    assert by_id["live-skip"]["simulation"]["status"] == "skipped"
    assert by_id["live-skip"]["simulation_status"] == "skipped"
    assert by_id["live-skip"]["traded"] is False
    assert by_id["live-skip"]["scoreable"] is True
    assert by_id["live-skip"]["skip_reason"] == "decision_not_tradeable"
    assert by_id["live-skip"]["postmortem"]["recommendation"] == "no_trade"
    assert by_id["live-skip"]["postmortem_recommendation"] == "no_trade"
    assert "live-resolved" not in by_id
    assert "live-unquoted" not in by_id
    assert "live-wide-spread" not in by_id
    assert "live-wide-bid-ask" not in by_id


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
        assert payload["score_bundle"]["score"]["grade"] == "C"
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
        assert payload["score_bundle"]["execution"]["order_book_depth_usd"] == 50.0
        assert payload["score_bundle"]["execution"]["all_in_cost_bps"] == 840.0
        assert payload["simulation"]["fee_paid"] == 3.5468
        assert payload["simulation"]["metadata"]["execution"]["trading_fee_cost"] == 0.0468
        assert payload["simulation"]["metadata"]["execution"]["deposit_fee_cost"] == 1.5
        assert payload["simulation"]["metadata"]["execution"]["withdrawal_fee_cost"] == 2.0
        assert payload["simulation"]["metadata"]["execution_costs"]["all_in_cost_bps"] == 840.0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
