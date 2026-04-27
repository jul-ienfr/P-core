from __future__ import annotations

from pathlib import Path
from typing import Any
import json

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
        config_path=Path("/tmp/nonexistent_strategy_config_for_test.json"),
    )

    assert summary["enabled"] is True
    assert summary["auto_discovery"] is True
    assert summary["paper_only"] is True
    assert summary["trading_action"] == "none"
    assert summary["live_order_allowed"] is False
    assert summary["profile_count"] == len(profiles)
    assert summary["strategy_count"] == summary["profile_count"]
    assert summary["signal_count"] == summary["profile_count"]
    assert summary["decision_count"] == summary["profile_count"]
    assert summary["profile_ids"] == [str(profile["id"]) for profile in profiles]
    assert summary["strategy_ids"] == [strategy_id_for_profile(str(profile["id"])) for profile in profiles]
    assert set(summary["payloads_by_profile"]) == {str(profile["id"]) for profile in profiles}
    assert all(payloads[0]["score"]["feature_family"] for payloads in summary["payloads_by_profile"].values())
    assert all(decision["profile_id"] in summary["profile_ids"] for decision in summary["decisions"])
    assert all(decision["strategy_id"] in summary["strategy_ids"] for decision in summary["decisions"])
    assert summary["safety"] == {
        "paper_only": True,
        "no_real_orders": True,
        "live_order_allowed": False,
        "orders_submitted": 0,
    }


def test_runtime_weather_profile_summary_signals_are_paper_only_no_trading(tmp_path: Path) -> None:
    summary = build_runtime_weather_profile_summary(config_path=tmp_path / "missing_strategy_config.json")

    assert summary["default_enabled_all"] is True
    assert summary["signals"]
    assert all(signal["mode"] == "paper_only" for signal in summary["signals"])
    assert all(signal["trading_action"] == "none" for signal in summary["signals"])
    assert all(signal["side"] == "skip" for signal in summary["signals"])
    assert all("missing_probability" in signal["blockers"] for signal in summary["signals"])
    assert all(decision["decision"] == "skip" for decision in summary["decisions"])
    assert all(decision["paper_only"] is True for decision in summary["decisions"])
    assert all(decision["live_order_allowed"] is False for decision in summary["decisions"])


def test_runtime_weather_profile_summary_uses_strategy_config_enabled_set(tmp_path: Path) -> None:
    profiles = list_strategy_profiles()
    enabled_profile = profiles[1]
    enabled_strategy_id = strategy_id_for_profile(str(enabled_profile["id"]))
    disabled_strategy_id = strategy_id_for_profile(str(profiles[0]["id"]))
    config_path = tmp_path / "strategy_config.json"
    config_path.write_text(
        json.dumps(
            {
                "strategies": {
                    disabled_strategy_id: {"enabled": False, "mode": "paper_only", "allow_live": False, "settings": {}},
                    enabled_strategy_id: {"enabled": True, "mode": "paper_only", "allow_live": False, "settings": {}},
                }
            }
        ),
        encoding="utf-8",
    )

    summary = build_runtime_weather_profile_summary(config_path=config_path)

    assert summary["default_enabled_all"] is False
    assert summary["available_profile_count"] == len(profiles)
    assert summary["profile_count"] == 1
    assert summary["strategy_count"] == 1
    assert summary["profile_ids"] == [enabled_profile["id"]]
    assert summary["strategy_ids"] == [enabled_strategy_id]
    assert summary["signals"][0]["profile_id"] == enabled_profile["id"]
    assert summary["signals"][0]["mode"] == "paper_only"
    assert summary["decisions"][0]["profile_id"] == enabled_profile["id"]
    assert summary["decisions"][0]["strategy_id"] == enabled_strategy_id


def test_runtime_weather_profile_summary_builds_attributed_paper_decisions() -> None:
    profiles = list_strategy_profiles()
    summary = build_runtime_weather_profile_summary(
        markets=[{"id": "market-1", "clob_token_id": "token-1", "question": "Will it rain?", "best_ask": 0.4, "best_bid": 0.39, "liquidity": 1000}],
        probabilities={"token-1": 0.7},
        runtime_result={"execution": {"orders_submitted": []}},
        artifacts={"runtime_json": "fixture://runtime"},
        config_path=Path("/tmp/nonexistent_strategy_config_for_decisions_test.json"),
    )

    assert summary["decision_count"] == len(profiles)
    assert summary["enter_count"] >= 1
    assert any(decision["decision"] == "enter" for decision in summary["decisions"])
    matched_decisions = [decision for decision in summary["decisions"] if decision["market_id"] == "market-1"]
    assert matched_decisions
    assert all(decision["token_id"] == "token-1" for decision in matched_decisions)
    assert any(decision["requested_spend_usdc"] == 10.0 for decision in matched_decisions)
    matched_signals = [signal for signal in summary["signals"] if signal["market_id"] == "market-1"]
    assert all(signal["probability"] == 0.7 for signal in matched_signals)
    assert all(signal["market_price"] == 0.4 for signal in matched_signals)


def test_runtime_weather_profile_summary_skips_synthetic_market_derived_probability() -> None:
    summary = build_runtime_weather_profile_summary(
        markets=[{"id": "market-1", "clob_token_id": "token-1", "question": "Will it rain?", "best_ask": 0.4, "best_bid": 0.39, "liquidity": 1000}],
        probabilities={"token-1": {"probability_yes": 0.7, "confidence": 0.0, "source": "market_book_reference", "method": "book_price_reference", "synthetic": True}},
        runtime_result={"execution": {"orders_submitted": []}},
        artifacts={"runtime_json": "fixture://runtime"},
        config_path=Path("/tmp/nonexistent_strategy_config_for_synthetic_probability_test.json"),
    )

    matched_decisions = [decision for decision in summary["decisions"] if decision["market_id"] == "market-1"]
    assert matched_decisions
    assert all(decision["decision"] == "skip" for decision in matched_decisions)
    assert all("synthetic_probability" in decision["blockers"] for decision in matched_decisions)
    assert all("market_derived_probability_not_allowed" in decision["blockers"] for decision in matched_decisions)
    assert all(decision["probability_source"] == "market_book_reference" for decision in matched_decisions)


def test_runtime_weather_profile_summary_blocks_on_portfolio_risk_guard() -> None:
    summary = build_runtime_weather_profile_summary(
        markets=[{"id": "market-1", "clob_token_id": "token-1", "question": "Will it rain?", "best_ask": 0.4, "best_bid": 0.39, "liquidity": 1000}],
        probabilities={"token-1": 0.7},
        runtime_result={
            "execution": {"orders_submitted": []},
            "portfolio_risk": {
                "open_position_count": 10,
                "deployed_capital_usdc": 20.0,
                "daily_realized_pnl_usdc": -1.0,
                "circuit_breaker": {"tripped": True, "reason": "operator_pause", "tripped_at": "2026-04-27T00:00:00Z"},
            },
        },
        artifacts={"runtime_json": "fixture://runtime"},
        config_path=Path("/tmp/nonexistent_strategy_config_for_risk_guard_test.json"),
    )

    matched_decisions = [decision for decision in summary["decisions"] if decision["market_id"] == "market-1"]
    assert matched_decisions
    assert all(decision["decision"] == "skip" for decision in matched_decisions)
    assert all("circuit_breaker_tripped" in decision["blockers"] for decision in matched_decisions)
    assert all("max_open_positions_reached" in decision["blockers"] for decision in matched_decisions)
    assert all(decision["risk_ok"] is False for decision in matched_decisions)
    assert all(decision["portfolio_risk"]["diagnostics"]["paper_only"] is True for decision in matched_decisions)
    assert all(decision["portfolio_risk"]["diagnostics"]["live_order_allowed"] is False for decision in matched_decisions)
    assert all("circuit_breaker_tripped" in signal["blockers"] for signal in summary["signals"] if signal["market_id"] == "market-1")


def test_runtime_weather_profile_summary_enters_trusted_weather_model_probability() -> None:
    summary = build_runtime_weather_profile_summary(
        markets=[{"id": "market-1", "clob_token_id": "token-1", "question": "Will it rain?", "best_ask": 0.4, "best_bid": 0.39, "liquidity": 1000}],
        probabilities={
            "token-1": {
                "probability_yes": 0.7,
                "confidence": 0.8,
                "source": "weather_model",
                "method": "forecast_model",
                "synthetic": False,
                "forecast_source_provider": "open_meteo",
                "forecast_source_station_code": None,
                "forecast_source_url": "https://example.test/forecast",
                "forecast_source_latency_tier": "direct",
            }
        },
        runtime_result={"execution": {"orders_submitted": []}},
        artifacts={"runtime_json": "fixture://runtime"},
        config_path=Path("/tmp/nonexistent_strategy_config_for_trusted_probability_test.json"),
    )

    assert summary["enter_count"] >= 1
    enter_decision = next(decision for decision in summary["decisions"] if decision["decision"] == "enter" and decision["probability_source"] == "weather_model")
    assert enter_decision["forecast_source_provider"] == "open_meteo"
    assert enter_decision["forecast_source_url"] == "https://example.test/forecast"
    assert enter_decision["forecast_source_latency_tier"] == "direct"


def test_runtime_weather_profile_summary_skips_unavailable_weather_model_probability() -> None:
    summary = build_runtime_weather_profile_summary(
        markets=[{"id": "market-1", "clob_token_id": "token-1", "question": "Will it rain?", "best_ask": 0.4, "best_bid": 0.39, "liquidity": 1000}],
        probabilities={"token-1": {"probability_yes": None, "confidence": 0.0, "source": "weather_model_unavailable", "method": "unavailable", "synthetic": True, "error": "ValueError('missing city')"}},
        runtime_result={"execution": {"orders_submitted": []}},
        artifacts={"runtime_json": "fixture://runtime"},
        config_path=Path("/tmp/nonexistent_strategy_config_for_unavailable_probability_test.json"),
    )

    matched_decisions = [decision for decision in summary["decisions"] if decision["market_id"] == "market-1"]
    assert matched_decisions
    assert all(decision["decision"] == "skip" for decision in matched_decisions)
    assert all("missing_probability" in decision["blockers"] for decision in matched_decisions)
    assert all("synthetic_probability" in decision["blockers"] for decision in matched_decisions)
    assert all(decision["probability_source"] == "weather_model_unavailable" for decision in matched_decisions)
    assert all(decision["probability_error"] == "ValueError('missing city')" for decision in matched_decisions)


def test_runtime_weather_profile_summary_does_not_force_macro_profile_onto_generic_market() -> None:
    summary = build_runtime_weather_profile_summary(
        markets=[{"id": "market-1", "clob_token_id": "token-1", "question": "Will the highest temperature in Paris be 20C?", "best_ask": 0.4, "best_bid": 0.39, "liquidity": 1000}],
        probabilities={"token-1": 0.7},
        runtime_result={"execution": {"orders_submitted": []}},
        artifacts={"runtime_json": "fixture://runtime"},
        config_path=Path("/tmp/nonexistent_strategy_config_for_macro_test.json"),
    )

    macro_decision = next(decision for decision in summary["decisions"] if decision["profile_id"] == "macro_weather_event_trader")
    macro_signal = next(signal for signal in summary["signals"] if signal["profile_id"] == "macro_weather_event_trader")

    assert macro_decision["decision"] == "skip"
    assert "no_profile_candidate_market" in macro_decision["blockers"]
    assert "no_profile_candidate_market" in macro_signal["blockers"]


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

    summary = build_runtime_weather_profile_summary(runtime_result={"execution": {"orders_submitted": []}}, config_path=Path("/tmp/nonexistent_strategy_config_for_dynamic_test.json"))

    assert summary["profile_count"] == len(dynamic_profiles)
    assert summary["strategy_count"] == len(dynamic_profiles)
    assert summary["signal_count"] == len(dynamic_profiles)
    assert summary["profile_ids"][-1] == "future_weather_profile"
    assert summary["strategy_ids"][-1] == strategy_id_for_profile("future_weather_profile")
    assert summary["signals"][-1]["profile_id"] == "future_weather_profile"
    assert summary["signals"][-1]["mode"] == "paper_only"
    assert summary["signals"][-1]["trading_action"] == "none"
    assert summary["decisions"][-1]["profile_id"] == "future_weather_profile"
    assert summary["payloads_by_profile"]["future_weather_profile"][0]["score"]["feature_family"]
