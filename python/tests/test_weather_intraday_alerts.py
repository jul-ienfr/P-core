from __future__ import annotations

from pathlib import Path

from weather_pm.intraday_alerts import build_intraday_alert_summary
from weather_pm.runtime_operator_profiles import build_runtime_weather_profile_summary


def test_intraday_alert_summary_detects_momentum_spike() -> None:
    summary = build_intraday_alert_summary(
        observations=[
            {"observed_at": "2026-04-27T13:00:00Z", "temperature": 68.0},
            {"observed_at": "2026-04-27T14:00:00Z", "temperature": 69.0},
            {"observed_at": "2026-04-27T15:00:00Z", "temperature": 73.5},
        ],
        now="2026-04-27T15:10:00Z",
    )

    assert summary["has_observations"] is True
    assert summary["status"] == "active"
    assert summary["momentum_spike"] is True
    assert "momentum_spike" in summary["alerts"]
    assert summary["latest_value"] == 73.5
    assert summary["momentum_delta"] == 4.5


def test_intraday_alert_summary_flags_peak_passed_guard() -> None:
    summary = build_intraday_alert_summary(
        observations=[
            {"observed_at": "2026-04-27T12:00:00Z", "temperature": 80.0},
            {"observed_at": "2026-04-27T13:00:00Z", "temperature": 82.0},
            {"observed_at": "2026-04-27T14:00:00Z", "temperature": 79.5},
            {"observed_at": "2026-04-27T15:00:00Z", "temperature": 78.5},
        ],
        now="2026-04-27T15:05:00Z",
    )

    assert summary["peak_passed"] is True
    assert summary["peak_value"] == 82.0
    assert summary["latest_below_peak"] == 3.5
    assert "peak_passed_guard" in summary["alerts"]


def test_intraday_alert_summary_flags_stale_observation() -> None:
    summary = build_intraday_alert_summary(
        observations=[{"observed_at": "2026-04-27T12:00:00Z", "temperature": 70.0}],
        now="2026-04-27T14:30:00Z",
        stale_after_minutes=90,
    )

    assert summary["status"] == "stale"
    assert summary["stale_observation"] is True
    assert summary["latest_age_minutes"] == 150
    assert "stale_observation" in summary["alerts"]


def test_intraday_alert_summary_source_confirmed_threshold_margin() -> None:
    summary = build_intraday_alert_summary(
        observations=[
            {"observed_at": "2026-04-27T13:00:00Z", "temperature": 74.0, "source": "station"},
            {"observed_at": "2026-04-27T14:00:00Z", "temperature": 76.5, "source": "station"},
        ],
        threshold=75.0,
        direction="above",
        now="2026-04-27T14:10:00Z",
    )

    assert summary["source_confirmed"] is True
    assert summary["threshold_margin"] == 1.5
    assert summary["source_confirmed_threshold_margin"] is True
    assert "source_confirmed_threshold_margin" in summary["alerts"]


def test_intraday_alert_summary_no_data_is_empty_and_optional() -> None:
    assert build_intraday_alert_summary([]) == {
        "has_observations": False,
        "status": "no_data",
        "alerts": [],
    }

    runtime = build_runtime_weather_profile_summary(
        markets=[{"id": "market-1", "clob_token_id": "token-1", "question": "Will it rain?", "best_ask": 0.4, "best_bid": 0.39, "liquidity": 1000}],
        probabilities={"token-1": 0.7},
        runtime_result={"execution": {"orders_submitted": []}},
        config_path=Path("/tmp/nonexistent_strategy_config_for_intraday_no_data_test.json"),
    )

    assert "intraday_alerts" not in runtime["feature_reports"]
    assert all("intraday_alerts" not in payloads[0]["score"] for payloads in runtime["payloads_by_profile"].values())
    assert all("intraday_alerts" not in signal for signal in runtime["signals"])


def test_runtime_weather_profile_summary_embeds_intraday_alerts_when_observations_present() -> None:
    runtime = build_runtime_weather_profile_summary(
        markets=[
            {
                "id": "market-1",
                "clob_token_id": "token-1",
                "question": "Will the highest temperature in Austin be above 75F?",
                "best_ask": 0.4,
                "best_bid": 0.39,
                "liquidity": 1000,
                "threshold": 75.0,
                "direction": "above",
            }
        ],
        probabilities={"token-1": 0.7},
        runtime_result={
            "execution": {"orders_submitted": []},
            "weather_observations": [
                {"observed_at": "2026-04-27T13:00:00Z", "temperature": 73.0, "source": "station"},
                {"observed_at": "2026-04-27T14:00:00Z", "temperature": 76.0, "source": "station"},
            ],
            "generated_at": "2026-04-27T14:05:00Z",
        },
        config_path=Path("/tmp/nonexistent_strategy_config_for_intraday_alert_test.json"),
    )

    intraday = runtime["feature_reports"]["intraday_alerts"]
    assert intraday["source_confirmed_threshold_margin"] is True
    assert intraday["threshold_margin"] == 1.0
    assert all(payloads[0]["score"]["intraday_alerts"] == intraday for payloads in runtime["payloads_by_profile"].values())
    assert all(signal["intraday_alerts"] == intraday for signal in runtime["signals"])
    assert all(decision["intraday_alerts"] == intraday for decision in runtime["decisions"])
