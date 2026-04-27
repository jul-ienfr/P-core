from __future__ import annotations

import json

import pytest

from prediction_core.strategies.config_store import StrategyConfigStore


def test_strategy_config_store_loads_empty_config(tmp_path) -> None:
    store = StrategyConfigStore(tmp_path / "strategy_config.json", audit_path=tmp_path / "audit.jsonl")

    assert store.list_configs() == {"strategies": {}}
    config = store.get_config("weather_profile_surface_grid_trader_v1")
    assert config.strategy_id == "weather_profile_surface_grid_trader_v1"
    assert config.enabled is False
    assert config.mode.value == "research_only"


def test_strategy_config_store_updates_independent_strategy_settings(tmp_path) -> None:
    store = StrategyConfigStore(tmp_path / "strategy_config.json", audit_path=tmp_path / "audit.jsonl")

    first = store.update_config(
        "weather_profile_surface_grid_trader_v1",
        {"enabled": True, "mode": "paper_only", "settings": {"max_order_usdc": 15.0, "min_edge": 0.04}},
    )
    second = store.update_config(
        "weather_profile_threshold_resolution_harvester_v1",
        {"enabled": False, "mode": "research_only", "settings": {"max_order_usdc": 8.0, "min_edge": 0.03}},
    )

    assert first.enabled is True
    assert second.enabled is False
    payload = json.loads((tmp_path / "strategy_config.json").read_text())
    assert payload["strategies"]["weather_profile_surface_grid_trader_v1"]["settings"]["max_order_usdc"] == 15.0
    assert payload["strategies"]["weather_profile_threshold_resolution_harvester_v1"]["settings"]["max_order_usdc"] == 8.0
    assert len((tmp_path / "audit.jsonl").read_text().strip().splitlines()) == 2


def test_strategy_config_store_enable_disable_and_live_guardrail(tmp_path) -> None:
    store = StrategyConfigStore(tmp_path / "strategy_config.json", audit_path=tmp_path / "audit.jsonl")

    assert store.set_enabled("weather_profile_surface_grid_trader_v1", True).enabled is True
    assert store.set_enabled("weather_profile_surface_grid_trader_v1", False).enabled is False
    with pytest.raises(ValueError, match="live_allowed strategies require explicit allow_live=True"):
        store.set_mode("weather_profile_surface_grid_trader_v1", "live_allowed")
    live = store.set_mode("weather_profile_surface_grid_trader_v1", "live_allowed", allow_live=True)
    assert live.mode.value == "live_allowed"
    assert live.allow_live is True


def test_strategy_config_store_rejects_invalid_settings(tmp_path) -> None:
    store = StrategyConfigStore(tmp_path / "strategy_config.json", audit_path=tmp_path / "audit.jsonl")

    with pytest.raises(ValueError, match="max_order_usdc must be non-negative"):
        store.update_config("s1", {"settings": {"max_order_usdc": -1}})
    with pytest.raises(ValueError, match="max_position_usdc must be >= max_order_usdc"):
        store.update_config("s1", {"settings": {"max_order_usdc": 10, "max_position_usdc": 5}})
