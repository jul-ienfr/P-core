from __future__ import annotations

import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from prediction_core.server import build_server


def _start_server(monkeypatch: pytest.MonkeyPatch, tmp_path) -> tuple[object, threading.Thread, str]:
    monkeypatch.setenv("PREDICTION_CORE_STRATEGY_CONFIG_PATH", str(tmp_path / "strategy_config.json"))
    monkeypatch.setenv("PREDICTION_CORE_STRATEGY_AUDIT_PATH", str(tmp_path / "strategy_config_audit.jsonl"))
    server = build_server(host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, f"http://127.0.0.1:{server.server_address[1]}"


def _json_request(url: str, payload: dict | None = None) -> dict:
    if payload is None:
        with urlopen(url, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))
    body = json.dumps(payload).encode("utf-8")
    request = Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def test_strategy_admin_api_updates_and_lists_config(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    server, thread, base_url = _start_server(monkeypatch, tmp_path)
    try:
        updated = _json_request(
            f"{base_url}/strategies/config/weather_profile_surface_grid_trader_v1",
            {"enabled": True, "mode": "paper_only", "settings": {"max_order_usdc": 15.0}},
        )
        assert updated["strategy"]["enabled"] is True
        assert updated["strategy"]["mode"] == "paper_only"

        listed = _json_request(f"{base_url}/strategies/config")
        assert listed["strategies"]["weather_profile_surface_grid_trader_v1"]["settings"]["max_order_usdc"] == 15.0

        detail = _json_request(f"{base_url}/strategies/config/weather_profile_surface_grid_trader_v1")
        assert detail["strategy"]["strategy_id"] == "weather_profile_surface_grid_trader_v1"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_strategy_admin_api_enable_disable_and_rejects_unsafe_live(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    server, thread, base_url = _start_server(monkeypatch, tmp_path)
    try:
        enabled = _json_request(f"{base_url}/strategies/config/weather_profile_surface_grid_trader_v1/enable", {})
        assert enabled["strategy"]["enabled"] is True
        disabled = _json_request(f"{base_url}/strategies/config/weather_profile_surface_grid_trader_v1/disable", {})
        assert disabled["strategy"]["enabled"] is False

        with pytest.raises(HTTPError) as exc_info:
            _json_request(f"{base_url}/strategies/config/weather_profile_surface_grid_trader_v1/mode", {"mode": "live_allowed"})
        assert exc_info.value.code == 400

        live = _json_request(f"{base_url}/strategies/config/weather_profile_surface_grid_trader_v1/mode", {"mode": "live_allowed", "allow_live": True})
        assert live["strategy"]["mode"] == "live_allowed"
        assert live["strategy"]["allow_live"] is True
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
