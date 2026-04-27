from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_monitor_module():
    path = Path(__file__).resolve().parents[2] / "scripts" / "weather_cron_monitor_refresh.py"
    spec = importlib.util.spec_from_file_location("weather_cron_monitor_refresh", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_runtime_analytics_rows_include_paper_basket_tables() -> None:
    module = _load_monitor_module()
    report = {
        "run_id": "20260427T190852Z",
        "runtime_execution_mode": "dry_run",
        "summary": {
            "portfolio_report": {
                "counts": {"exit_paper": 0, "open": 1, "settled": 1, "total": 2},
                "pnl_usdc": {"realized_total": 3.0, "realized_plus_open_mtm": 4.5},
                "spend_usdc": {"total_displayed": 20.0},
            }
        },
        "positions": [
            {
                "question": "Will it rain?",
                "token_id": "token-1",
                "side": "NO",
                "action": "HOLD_CAPPED",
                "shares": 10.0,
                "filled_usdc": 10.0,
                "entry_avg": 1.0,
                "paper_mtm_bid_usdc": 1.5,
            }
        ],
        "closed_positions": [
            {
                "question": "Will it snow?",
                "token_id": "token-2",
                "side": "NO",
                "action": "SETTLED_WON",
                "settlement_status": "SETTLED_WON",
                "shares": 10.0,
                "filled_usdc": 10.0,
                "entry_avg": 1.0,
                "paper_realized_pnl_usdc": 3.0,
            }
        ],
        "runtime_strategies": {"weather_profiles": {"decisions": []}, "execution_events": []},
    }

    rows = module.build_runtime_analytics_rows(report, "20260427T190852Z")

    assert len(rows["paper_orders"]) == 2
    assert len(rows["paper_positions"]) == 2
    assert len(rows["paper_pnl_snapshots"]) == 1
    assert rows["paper_pnl_snapshots"][0]["net_pnl_usdc"] == 4.5
    assert rows["paper_pnl_snapshots"][0]["exposure_usdc"] == 20.0
    assert rows["paper_orders"][0]["run_id"] == "20260427T190852Z"


def test_runtime_analytics_rows_create_profile_attributed_paper_rows() -> None:
    module = _load_monitor_module()
    report = {
        "run_id": "20260427T200628Z",
        "runtime_execution_mode": "dry_run",
        "summary": {"portfolio_report": {"counts": {}, "pnl_usdc": {}, "spend_usdc": {}}},
        "positions": [],
        "closed_positions": [],
        "runtime_strategies": {
            "runtime_execution_mode": "dry_run",
            "weather_profiles": {
                "decisions": [
                    {
                        "strategy_id": "weather_profile_surface_grid_trader_v1",
                        "profile_id": "surface_grid_trader",
                        "market_id": "market-1",
                        "token_id": "token-1",
                        "decision": "enter",
                        "decision_status": "paper_trade_small",
                        "side": "yes",
                        "market_price": 0.4,
                        "capped_spend_usdc": 10.0,
                        "paper_only": True,
                        "live_order_allowed": False,
                    }
                ]
            },
            "execution_events": [],
        },
    }

    rows = module.build_runtime_analytics_rows(report, "20260427T200628Z")

    profile_orders = [row for row in rows["paper_orders"] if row["profile_id"] == "surface_grid_trader"]
    profile_positions = [row for row in rows["paper_positions"] if row["profile_id"] == "surface_grid_trader"]
    profile_pnl = [row for row in rows["paper_pnl_snapshots"] if row["profile_id"] == "surface_grid_trader"]

    assert len(profile_orders) == 1
    assert profile_orders[0]["strategy_id"] == "weather_profile_surface_grid_trader_v1"
    assert profile_orders[0]["market_id"] == "market-1"
    assert profile_orders[0]["token_id"] == "token-1"
    assert profile_orders[0]["paper_only"] is True
    assert profile_orders[0]["live_order_allowed"] is False
    assert profile_orders[0]["status"] == "profile_enter_paper_planned"
    assert profile_orders[0]["spend_usdc"] == 10.0
    assert profile_orders[0]["size"] == 25.0
    raw = json.loads(profile_orders[0]["raw"])
    assert raw["analytics_source"] == "runtime_weather_profile_decision"
    assert raw["fill_semantics"] == "planned_intent"
    assert raw["paper_only"] is True
    assert raw["live_order_allowed"] is False
    assert raw["no_real_order_placed"] is True
    assert raw["runtime_execution_mode"] == "dry_run"
    assert "20260427T200628Z" not in profile_orders[0]["paper_order_id"]
    assert len(profile_positions) == 0
    assert len(profile_pnl) == 0


def test_runtime_analytics_rows_do_not_create_profile_orders_for_skip_or_live_allowed() -> None:
    module = _load_monitor_module()
    base_decision = {
        "strategy_id": "weather_profile_surface_grid_trader_v1",
        "profile_id": "surface_grid_trader",
        "market_id": "market-1",
        "token_id": "token-1",
        "side": "yes",
        "market_price": 0.4,
        "capped_spend_usdc": 10.0,
        "paper_only": True,
        "live_order_allowed": False,
    }
    report = {
        "run_id": "20260427T200628Z",
        "runtime_execution_mode": "dry_run",
        "summary": {"portfolio_report": {"counts": {}, "pnl_usdc": {}, "spend_usdc": {}}},
        "positions": [],
        "closed_positions": [],
        "runtime_strategies": {
            "weather_profiles": {
                "decisions": [
                    {**base_decision, "decision": "skip"},
                    {**base_decision, "decision": "enter", "profile_id": "exact_bin_anomaly_hunter", "live_order_allowed": True},
                ]
            },
            "execution_events": [],
        },
    }

    rows = module.build_runtime_analytics_rows(report, "20260427T200628Z")

    profile_orders = [row for row in rows["paper_orders"] if row["strategy_id"].startswith("weather_profile_")]
    profile_positions = [row for row in rows["paper_positions"] if row["strategy_id"].startswith("weather_profile_")]
    profile_pnl = [row for row in rows["paper_pnl_snapshots"] if row["strategy_id"].startswith("weather_profile_")]
    assert profile_orders == []
    assert profile_positions == []
    assert profile_pnl == []


def test_runtime_analytics_rows_create_position_and_pnl_for_filled_profile_decision() -> None:
    module = _load_monitor_module()
    report = {
        "run_id": "20260427T200628Z",
        "runtime_execution_mode": "dry_run",
        "summary": {"portfolio_report": {"counts": {}, "pnl_usdc": {}, "spend_usdc": {}}},
        "positions": [],
        "closed_positions": [],
        "runtime_strategies": {
            "weather_profiles": {
                "decisions": [
                    {"strategy_id": "weather_profile_surface_grid_trader_v1", "profile_id": "surface_grid_trader", "market_id": "market-1", "token_id": "token-1", "decision": "enter", "side": "yes", "market_price": 0.5, "capped_spend_usdc": 5.0, "paper_only": True, "live_order_allowed": False, "fill_status": "filled"},
                ]
            },
            "execution_events": [],
        },
    }

    rows = module.build_runtime_analytics_rows(report, "20260427T200628Z")

    profile_orders = [row for row in rows["paper_orders"] if row["profile_id"] == "surface_grid_trader"]
    profile_positions = [row for row in rows["paper_positions"] if row["profile_id"] == "surface_grid_trader"]
    profile_pnl = [row for row in rows["paper_pnl_snapshots"] if row["profile_id"] == "surface_grid_trader"]
    assert json.loads(profile_orders[0]["raw"])["fill_semantics"] == "simulated_fill"
    assert len(profile_positions) == 1
    assert profile_positions[0]["exposure_usdc"] == 5.0
    assert len(profile_pnl) == 1
    assert profile_pnl[0]["exposure_usdc"] == 5.0


def test_runtime_analytics_rows_preserve_manual_rows_without_planned_profile_pnl() -> None:
    module = _load_monitor_module()
    report = {
        "run_id": "20260427T200628Z",
        "runtime_execution_mode": "dry_run",
        "summary": {
            "portfolio_report": {
                "counts": {"open": 1, "total": 1},
                "pnl_usdc": {"realized_plus_open_mtm": 1.5},
                "spend_usdc": {"total_displayed": 10.0},
            }
        },
        "positions": [
            {"question": "Manual", "token_id": "manual-token", "side": "NO", "action": "HOLD_CAPPED", "shares": 10.0, "filled_usdc": 10.0, "entry_avg": 1.0, "paper_mtm_bid_usdc": 1.5}
        ],
        "closed_positions": [],
        "runtime_strategies": {
            "weather_profiles": {
                "decisions": [
                    {"strategy_id": "weather_profile_surface_grid_trader_v1", "profile_id": "surface_grid_trader", "market_id": "market-1", "token_id": "token-1", "decision": "enter", "side": "yes", "market_price": 0.5, "capped_spend_usdc": 5.0, "paper_only": True, "live_order_allowed": False},
                    {"strategy_id": "weather_profile_exact_bin_anomaly_hunter_v1", "profile_id": "exact_bin_anomaly_hunter", "market_id": "market-2", "token_id": "token-2", "decision": "enter", "side": "yes", "market_price": 0.25, "capped_spend_usdc": 8.0, "paper_only": True, "live_order_allowed": False},
                ]
            },
            "execution_events": [],
        },
    }

    rows = module.build_runtime_analytics_rows(report, "20260427T200628Z")

    assert any(row["strategy_id"] == "weather_manual_paper_basket_v1" for row in rows["paper_orders"])
    assert any(row["profile_id"] == "surface_grid_trader" for row in rows["paper_orders"])
    assert any(row["profile_id"] == "exact_bin_anomaly_hunter" for row in rows["paper_orders"])
    profile_positions = [row for row in rows["paper_positions"] if row["strategy_id"].startswith("weather_profile_")]
    profile_pnl = [row for row in rows["paper_pnl_snapshots"] if row["strategy_id"].startswith("weather_profile_")]
    assert profile_positions == []
    assert profile_pnl == []


def test_weather_model_probability_record_uses_forecast_model(monkeypatch) -> None:
    module = _load_monitor_module()

    class Forecast:
        source_provider = "open_meteo"
        source_station_code = "STATION1"
        source_url = "https://example.test/forecast"
        source_latency_tier = "direct"

    class Model:
        probability_yes = 0.63
        confidence = 0.61
        method = "calibrated_threshold_v1"

    monkeypatch.setattr(module, "parse_market_question", lambda question: {"question": question})
    monkeypatch.setattr(module, "parse_resolution_metadata", lambda **kwargs: {"resolution": kwargs})
    monkeypatch.setattr(module, "build_forecast_bundle", lambda structure, live, resolution: Forecast())
    monkeypatch.setattr(module, "build_model_output", lambda structure, forecast: Model())

    record = module.build_weather_model_probability_record({"question": "Will it rain?", "resolution_source": "NOAA"})

    assert record == {
        "probability_yes": 0.63,
        "confidence": 0.61,
        "source": "weather_model",
        "method": "calibrated_threshold_v1",
        "synthetic": False,
        "forecast_source_provider": "open_meteo",
        "forecast_source_station_code": "STATION1",
        "forecast_source_url": "https://example.test/forecast",
        "forecast_source_latency_tier": "direct",
    }


def test_weather_model_probability_record_marks_model_failure_non_tradable(monkeypatch) -> None:
    module = _load_monitor_module()

    def fail_parse(question: str):
        raise ValueError("missing city")

    monkeypatch.setattr(module, "parse_market_question", fail_parse)

    record = module.build_weather_model_probability_record({"question": "unknown"})

    assert record["probability_yes"] is None
    assert record["confidence"] == 0.0
    assert record["source"] == "weather_model_unavailable"
    assert record["method"] == "unavailable"
    assert record["synthetic"] is True
    assert "missing city" in record["error"]
