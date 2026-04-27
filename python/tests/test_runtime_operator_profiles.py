from __future__ import annotations

from typing import Any

import prediction_core.strategies.weather_profile_strategies as weather_profile_strategies
from weather_pm import runtime_operator_profiles
from weather_pm.runtime_operator_profiles import build_runtime_weather_profile_summary
from weather_pm.strategy_profiles import list_strategy_profiles, strategy_id_for_profile


def test_runtime_weather_profile_summary_discovers_current_profiles() -> None:
    profiles = list_strategy_profiles()
    summary = build_runtime_weather_profile_summary(
        markets=[{"id": "market-1", "clob_token_id": "token-1", "question": "Will it rain?"}],
        probabilities={"token-1": 0.57},
        runtime_result={"execution": {"orders_submitted": []}},
        artifacts={"runtime_json": "fixture://runtime"},
    )

    assert summary["enabled"] is True
    assert summary["auto_discovery"] is True
    assert summary["paper_only"] is True
    assert summary["trading_action"] == "none"
    assert summary["live_order_allowed"] is False
    assert summary["profile_count"] == len(profiles)
    assert summary["strategy_count"] == summary["profile_count"]
    assert summary["signal_count"] == summary["profile_count"]
    assert summary["profile_ids"] == [str(profile["id"]) for profile in profiles]
    assert summary["strategy_ids"] == [strategy_id_for_profile(str(profile["id"])) for profile in profiles]
    assert summary["safety"] == {
        "paper_only": True,
        "no_real_orders": True,
        "live_order_allowed": False,
        "orders_submitted": 0,
    }


def test_runtime_weather_profile_summary_signals_are_paper_only_no_trading() -> None:
    summary = build_runtime_weather_profile_summary()

    assert summary["signals"]
    assert all(signal["mode"] == "paper_only" for signal in summary["signals"])
    assert all(signal["trading_action"] == "none" for signal in summary["signals"])
    assert all(signal["side"] == "skip" for signal in summary["signals"])
    assert all(signal["blockers"] == ["operator_review_required"] for signal in summary["signals"])


def test_runtime_weather_profile_summary_uses_dynamic_profile_discovery(monkeypatch) -> None:
    base_profiles = list_strategy_profiles()
    extra_profile: dict[str, Any] = {
        **base_profiles[0],
        "id": "future_weather_profile",
        "label": "Future weather profile",
        "entry_gates": ["future_gate"],
    }
    dynamic_profiles = [*base_profiles, extra_profile]

    def fake_list_strategy_profiles() -> list[dict[str, Any]]:
        return dynamic_profiles

    def fake_get_strategy_profile(profile_id: str) -> dict[str, Any]:
        for profile in dynamic_profiles:
            if profile["id"] == profile_id:
                return profile
        raise KeyError(profile_id)

    monkeypatch.setattr(runtime_operator_profiles, "list_strategy_profiles", fake_list_strategy_profiles)
    monkeypatch.setattr(weather_profile_strategies, "list_strategy_profiles", fake_list_strategy_profiles)
    monkeypatch.setattr(weather_profile_strategies, "get_strategy_profile", fake_get_strategy_profile)

    summary = build_runtime_weather_profile_summary(runtime_result={"execution": {"orders_submitted": []}})

    assert summary["profile_count"] == len(dynamic_profiles)
    assert summary["strategy_count"] == len(dynamic_profiles)
    assert summary["signal_count"] == len(dynamic_profiles)
    assert summary["profile_ids"][-1] == "future_weather_profile"
    assert summary["strategy_ids"][-1] == strategy_id_for_profile("future_weather_profile")
    assert summary["signals"][-1]["profile_id"] == "future_weather_profile"
    assert summary["signals"][-1]["mode"] == "paper_only"
    assert summary["signals"][-1]["trading_action"] == "none"
