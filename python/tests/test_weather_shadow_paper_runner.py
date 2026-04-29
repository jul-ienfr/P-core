from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from weather_pm.account_trades import classify_weather_trade
from weather_pm.shadow_paper_runner import (
    build_account_trade_resolution_dataset,
    build_market_metadata_resolution_dataset,
    build_shadow_profile_evaluation,
    build_shadow_profile_paper_orders,
    enrich_shadow_dataset_features,
)


def _classified_trade(title: str, *, wallet: str = "0xCold", price: float = 0.31, size: float = 100.0) -> dict[str, object]:
    return classify_weather_trade(
        {
            "transactionHash": f"0x{abs(hash((title, wallet, price))) % 999999:x}",
            "proxyWallet": wallet,
            "userName": "ColdMath",
            "title": title,
            "slug": title.lower().replace(" ", "-"),
            "side": "BUY",
            "outcome": "Yes",
            "price": price,
            "size": size,
            "timestamp": "2026-04-24T10:00:00Z",
        }
    ).to_dict()


def _dataset() -> dict[str, object]:
    return {
        "paper_only": True,
        "live_order_allowed": False,
        "examples": [
            {
                "wallet": "0xCold",
                "market_id": "m-london-20",
                "question": "Will the highest temperature in London be exactly 20°C on April 25?",
                "city": "London",
                "date": "April 25",
                "surface_key": "london|april 25",
                "weather_market_type": "exact_value",
                "label": "trade",
                "yes_price": 0.31,
                "model_probability": 0.56,
                "account_trade_price": 0.31,
                "account_trade_size": 100.0,
                "account_trade_notional_usd": 31.0,
            },
            {
                "wallet": "0xCold",
                "market_id": "m-paris-18",
                "question": "Will the highest temperature in Paris be exactly 18°C on April 25?",
                "city": "Paris",
                "date": "April 25",
                "surface_key": "paris|april 25",
                "weather_market_type": "exact_value",
                "label": "no_trade",
                "yes_price": 0.48,
                "model_probability": 0.49,
                "account_trade_price": 0.0,
                "account_trade_size": 0.0,
                "account_trade_notional_usd": 0.0,
            },
        ],
    }


def test_enrich_shadow_dataset_features_adds_orderbook_and_forecast_placeholders() -> None:
    dataset = _dataset()
    enriched = enrich_shadow_dataset_features(
        dataset,
        orderbooks={"m-london-20": {"best_bid": 0.30, "best_ask": 0.32, "depth_usd": 750}},
        forecasts={"london|april 25": {"forecast_high_c": 20.4, "source": "fixture_ecmwf", "freshness_minutes": 45}},
    )

    row = enriched["examples"][0]
    assert row["features"]["orderbook"] == {"best_bid": 0.30, "best_ask": 0.32, "spread_bps": 645.16129, "depth_usd": 750.0, "available": True}
    assert row["features"]["forecast"] == {"forecast_high_c": 20.4, "source": "fixture_ecmwf", "freshness_minutes": 45.0, "available": True}
    assert enriched["examples"][1]["features"]["orderbook"]["available"] is False
    assert enriched["summary"]["feature_rows"] == 2
    assert enriched["paper_only"] is True
    assert enriched["live_order_allowed"] is False


def test_enrich_shadow_dataset_features_adds_resolution_and_historical_forecast_context() -> None:
    enriched = enrich_shadow_dataset_features(
        _dataset(),
        orderbooks={"m-london-20": {"best_bid": 0.30, "best_ask": 0.32, "depth_usd": 750}},
        forecasts={"london|april 25": {"forecast_high_c": 20.4, "source": "fixture_ecmwf", "freshness_minutes": 45}},
        historical_forecasts={
            "m-london-20": {
                "source": "replay_archive",
                "freshness_minutes": 17,
                "model_probability_at_trade": 0.57,
            }
        },
        resolutions={
            "m-london-20": {
                "resolved_outcome": "Yes",
                "status": "resolved",
                "observed_value": 20.1,
                "source": "fixture_station_history",
                "confidence": 0.98,
            },
            "paris|april 25": {
                "resolved_outcome": "No",
                "status": "resolved",
                "observed_value": 21.0,
                "source": "fixture_official_daily",
                "confidence": 0.91,
            },
        },
    )

    london_features = enriched["examples"][0]["features"]
    assert london_features["resolution"] == {
        "available": True,
        "resolved_outcome": "Yes",
        "status": "resolved",
        "observed_value": 20.1,
        "source": "fixture_station_history",
        "confidence": 0.98,
    }
    assert london_features["forecast_context"] == {
        "available": True,
        "source": "replay_archive",
        "freshness_minutes": 17.0,
        "model_probability_at_trade": 0.57,
    }
    assert london_features["forecast"]["source"] == "fixture_ecmwf"
    assert enriched["examples"][1]["features"]["resolution"]["source"] == "fixture_official_daily"
    assert enriched["summary"]["resolved_orders"] == 2


def test_build_shadow_profile_paper_orders_only_places_independently_confirmed_shadow_orders() -> None:
    enriched = enrich_shadow_dataset_features(
        _dataset(),
        orderbooks={"m-london-20": {"best_bid": 0.30, "best_ask": 0.32, "depth_usd": 750}},
        forecasts={"london|april 25": {"forecast_high_c": 20.4, "source": "fixture_ecmwf", "freshness_minutes": 45}},
    )

    result = build_shadow_profile_paper_orders(enriched, run_id="shadow-smoke", max_order_usdc=5.0)

    assert result["summary"] == {"paper_orders": 1, "skipped": 1, "paper_only": True, "live_order_allowed": False}
    assert result["orders"][0]["market_id"] == "m-london-20"
    assert result["orders"][0]["requested_notional_usdc"] == 5.0
    assert result["orders"][0]["strict_limit_price"] == 0.32
    assert result["orders"][0]["source"] == "shadow_profile_replay"
    assert result["orders"][0]["paper_only"] is True
    assert result["orders"][0]["live_order_allowed"] is False
    assert result["skipped"][0]["reason"] == "account_no_trade_label"


def test_build_shadow_profile_paper_orders_applies_profile_specific_sizing_and_role_metadata() -> None:
    dataset = _dataset()
    dataset["examples"][0]["wallet"] = "0xMarchyel"
    enriched = enrich_shadow_dataset_features(
        dataset,
        orderbooks={"m-london-20": {"best_bid": 0.30, "best_ask": 0.32, "depth_usd": 750}},
        forecasts={"london|april 25": {"forecast_high_c": 20.4, "source": "fixture_ecmwf", "freshness_minutes": 45}},
    )

    result = build_shadow_profile_paper_orders(
        enriched,
        run_id="shadow-smoke",
        max_order_usdc=5.0,
        profile_configs={
            "0xmarchyel": {
                "profile_id": "marchyel_like_capped",
                "role": "large_sizing_grid_reference",
                "max_order_usdc": 1.25,
                "min_edge": 0.20,
            }
        },
    )

    order = result["orders"][0]
    assert order["requested_notional_usdc"] == 1.25
    assert order["profile_id"] == "marchyel_like_capped"
    assert order["profile_role"] == "large_sizing_grid_reference"
    assert order["metadata"]["profile_config"] == {
        "profile_id": "marchyel_like_capped",
        "role": "large_sizing_grid_reference",
        "max_order_usdc": 1.25,
        "min_edge": 0.20,
    }
    assert result["summary"]["profile_counts"] == {"marchyel_like_capped": 1}


def test_build_shadow_profile_paper_orders_skips_when_profile_min_edge_not_met() -> None:
    dataset = _dataset()
    dataset["examples"][0]["wallet"] = "0xJey"
    enriched = enrich_shadow_dataset_features(
        dataset,
        orderbooks={"m-london-20": {"best_bid": 0.30, "best_ask": 0.32, "depth_usd": 750}},
        forecasts={"london|april 25": {"forecast_high_c": 20.4, "source": "fixture_ecmwf", "freshness_minutes": 45}},
    )

    result = build_shadow_profile_paper_orders(
        enriched,
        run_id="shadow-smoke",
        max_order_usdc=5.0,
        profile_configs={"0xjey": {"profile_id": "jey_threshold", "max_order_usdc": 3.0, "min_edge": 0.30}},
    )

    assert result["orders"] == []
    assert result["skipped"] == [
        {"market_id": "m-london-20", "wallet": "0xJey", "reason": "profile_min_edge_not_met"},
        {"market_id": "m-paris-18", "wallet": "0xCold", "reason": "account_no_trade_label"},
    ]
    assert result["summary"] == {"paper_orders": 0, "skipped": 2, "paper_only": True, "live_order_allowed": False}


def test_build_shadow_profile_paper_orders_preserves_resolution_and_forecast_context_metadata() -> None:
    enriched = enrich_shadow_dataset_features(
        _dataset(),
        orderbooks={"m-london-20": {"best_bid": 0.30, "best_ask": 0.32, "depth_usd": 750}},
        forecasts={"london|april 25": {"forecast_high_c": 20.4, "source": "fixture_ecmwf", "freshness_minutes": 45}},
        historical_forecasts={"london|april 25": {"source": "replay_archive", "freshness_minutes": 19, "model_probability_at_trade": 0.56}},
        resolutions={"london|april 25": {"resolved_outcome": "Yes", "status": "resolved", "observed_value": 20.1, "source": "fixture_station_history", "confidence": 0.98}},
    )

    result = build_shadow_profile_paper_orders(enriched, run_id="shadow-smoke", max_order_usdc=5.0)

    assert result["summary"] == {"paper_orders": 1, "skipped": 1, "resolved_orders": 1, "paper_only": True, "live_order_allowed": False}
    order = result["orders"][0]
    assert order["metadata"]["resolution"] == order["features"]["resolution"]
    assert order["metadata"]["forecast_context"] == order["features"]["forecast_context"]
    assert order["paper_only"] is True
    assert order["live_order_allowed"] is False


def test_cli_shadow_paper_runner_writes_artifact(tmp_path: Path) -> None:
    dataset_in = tmp_path / "dataset.json"
    orderbooks_in = tmp_path / "orderbooks.json"
    forecasts_in = tmp_path / "forecasts.json"
    output = tmp_path / "paper_orders.json"
    dataset_in.write_text(json.dumps(_dataset()), encoding="utf-8")
    orderbooks_in.write_text(json.dumps({"m-london-20": {"best_bid": 0.30, "best_ask": 0.32, "depth_usd": 750}}), encoding="utf-8")
    forecasts_in.write_text(json.dumps({"london|april 25": {"forecast_high_c": 20.4, "source": "fixture_ecmwf", "freshness_minutes": 45}}), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "weather_pm.cli",
            "shadow-paper-runner",
            "--dataset-json",
            str(dataset_in),
            "--orderbooks-json",
            str(orderbooks_in),
            "--forecasts-json",
            str(forecasts_in),
            "--run-id",
            "shadow-smoke",
            "--output-json",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
        env={"PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
    )

    assert result.returncode == 0, result.stderr
    compact = json.loads(result.stdout)
    assert compact["summary"]["paper_orders"] == 1
    assert compact["artifacts"] == {"output_json": str(output)}
    assert json.loads(output.read_text(encoding="utf-8"))["live_order_allowed"] is False


def test_cli_shadow_paper_runner_accepts_resolutions_json(tmp_path: Path) -> None:
    dataset_in = tmp_path / "dataset.json"
    orderbooks_in = tmp_path / "orderbooks.json"
    forecasts_in = tmp_path / "forecasts.json"
    resolutions_in = tmp_path / "resolutions.json"
    output = tmp_path / "paper_orders.json"
    dataset_in.write_text(json.dumps(_dataset()), encoding="utf-8")
    orderbooks_in.write_text(json.dumps({"m-london-20": {"best_bid": 0.30, "best_ask": 0.32, "depth_usd": 750}}), encoding="utf-8")
    forecasts_in.write_text(json.dumps({"london|april 25": {"forecast_high_c": 20.4, "source": "fixture_ecmwf", "freshness_minutes": 45}}), encoding="utf-8")
    resolutions_in.write_text(json.dumps({"m-london-20": {"resolved_outcome": "Yes", "status": "resolved", "observed_value": 20.1, "source": "fixture_station_history", "confidence": 0.98}}), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "weather_pm.cli",
            "shadow-paper-runner",
            "--dataset-json",
            str(dataset_in),
            "--orderbooks-json",
            str(orderbooks_in),
            "--forecasts-json",
            str(forecasts_in),
            "--resolutions-json",
            str(resolutions_in),
            "--run-id",
            "shadow-smoke",
            "--output-json",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
        env={"PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
    )

    assert result.returncode == 0, result.stderr
    compact = json.loads(result.stdout)
    assert compact["summary"]["resolved_orders"] == 1
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["orders"][0]["features"]["resolution"]["available"] is True
    assert payload["orders"][0]["features"]["resolution"]["resolved_outcome"] == "Yes"


def test_cli_shadow_paper_runner_accepts_profile_configs_json(tmp_path: Path) -> None:
    dataset = _dataset()
    dataset["examples"][0]["wallet"] = "0xMarchyel"
    dataset_in = tmp_path / "dataset.json"
    orderbooks_in = tmp_path / "orderbooks.json"
    forecasts_in = tmp_path / "forecasts.json"
    profile_configs_in = tmp_path / "profile_configs.json"
    output = tmp_path / "paper_orders.json"
    dataset_in.write_text(json.dumps(dataset), encoding="utf-8")
    orderbooks_in.write_text(json.dumps({"m-london-20": {"best_bid": 0.30, "best_ask": 0.32, "depth_usd": 750}}), encoding="utf-8")
    forecasts_in.write_text(json.dumps({"london|april 25": {"forecast_high_c": 20.4, "source": "fixture_ecmwf", "freshness_minutes": 45}}), encoding="utf-8")
    profile_configs_in.write_text(
        json.dumps({"profiles": {"0xmarchyel": {"profile_id": "marchyel_like_capped", "role": "large_sizing_grid_reference", "max_order_usdc": 1.25}}}),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "weather_pm.cli",
            "shadow-paper-runner",
            "--dataset-json",
            str(dataset_in),
            "--orderbooks-json",
            str(orderbooks_in),
            "--forecasts-json",
            str(forecasts_in),
            "--profile-configs-json",
            str(profile_configs_in),
            "--run-id",
            "shadow-smoke",
            "--output-json",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
        env={"PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
    )

    assert result.returncode == 0, result.stderr
    compact = json.loads(result.stdout)
    assert compact["summary"]["profile_counts"] == {"marchyel_like_capped": 1}
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["orders"][0]["requested_notional_usdc"] == 1.25
    assert payload["orders"][0]["metadata"]["profile_config"]["profile_id"] == "marchyel_like_capped"


def test_build_market_metadata_resolution_dataset_uses_closed_resolved_outcome_prices() -> None:
    result = build_market_metadata_resolution_dataset(
        {
            "markets": [
                {
                    "id": "m-toronto-19",
                    "question": "Will the highest temperature in Toronto be 19°C or higher on April 28?",
                    "slug": "highest-temperature-in-toronto-on-april-28-2026-19c-or-higher",
                    "closed": True,
                    "active": False,
                    "outcomes": '["Yes", "No"]',
                    "outcomePrices": '["0", "1"]',
                    "resolvedOutcome": "No",
                },
                {
                    "id": "m-open",
                    "question": "Will the highest temperature in Paris be 18°C on April 29?",
                    "closed": False,
                    "active": True,
                    "outcomes": '["Yes", "No"]',
                    "outcomePrices": '["0.49", "0.51"]',
                },
            ]
        }
    )

    assert result["paper_only"] is True
    assert result["live_order_allowed"] is False
    assert result["summary"] == {"markets": 2, "resolved_markets": 1, "unresolved_markets": 1, "paper_only": True, "live_order_allowed": False}
    resolved = result["resolutions"]["m-toronto-19"]
    assert resolved["resolved_outcome"] == "No"
    assert resolved["status"] == "resolved"
    assert resolved["source"] == "gamma_closed_market_metadata"
    assert resolved["confidence"] == 1.0
    assert resolved["question"] == "Will the highest temperature in Toronto be 19°C or higher on April 28?"
    assert "m-open" not in result["resolutions"]


def test_build_market_metadata_resolution_dataset_infers_from_final_outcome_prices() -> None:
    result = build_market_metadata_resolution_dataset(
        [
            {
                "id": "m-london-20",
                "title": "Will the highest temperature in London be exactly 20°C on April 25?",
                "slug": "highest-temperature-in-london-on-april-25-2026-20c",
                "closed": True,
                "active": False,
                "outcomes": ["Yes", "No"],
                "outcomePrices": ["0.998", "0.002"],
            }
        ]
    )

    assert result["summary"]["resolved_markets"] == 1
    resolved = result["resolutions"]["m-london-20"]
    assert resolved["resolved_outcome"] == "Yes"
    assert resolved["status"] == "closed_price_resolved_proxy"
    assert resolved["source"] == "gamma_closed_outcomePrices_proxy"
    assert resolved["confidence"] == 0.998
    assert resolved["outcome_prices"] == [0.998, 0.002]


def test_build_account_trade_resolution_dataset_matches_resolution_by_question_when_trade_has_no_market_id() -> None:
    trades = {
        "trades": [
            {
                "wallet": "0xJey",
                "handle": "jey",
                "title": "Will the highest temperature in Toronto be 19°C or higher on April 28?",
                "slug": "highest-temperature-in-toronto-on-april-28-2026-19c-or-higher",
                "side": "BUY",
                "outcome": "No",
                "price": 0.90,
                "size": 10,
                "notional_usd": 9.0,
                "timestamp": "2026-04-28T23:25:14Z",
                "weather_market_type": "threshold",
                "city": "Toronto",
            }
        ]
    }
    resolutions = {
        "2082355": {
            "question": "Will the highest temperature in Toronto be 19°C or higher on April 28?",
            "resolved_outcome": "No",
            "status": "market_price_proxy_unfinalized",
            "source": "gamma_outcomePrices_current_proxy",
        }
    }

    result = build_account_trade_resolution_dataset(trades, resolutions=resolutions)

    assert result["summary"]["resolved_trades"] == 1
    assert result["summary"]["wins"] == 1
    assert result["trades"][0]["resolution"]["source"] == "gamma_outcomePrices_current_proxy"
    assert result["trades"][0]["trade_result"] == "win"
    assert result["trades"][0]["estimated_pnl_usdc"] == 1.0


def test_build_account_trade_resolution_dataset_matches_resolution_from_enriched_metadata_aliases() -> None:
    metadata = build_market_metadata_resolution_dataset(
        {
            "markets": [
                {
                    "id": "gamma-123",
                    "conditionId": "0xcondition",
                    "question": "Will the highest temperature in Toronto be 19°C or higher on April 28?",
                    "slug": "highest-temperature-in-toronto-on-april-28-2026-19c-or-higher",
                    "closed": True,
                    "active": False,
                    "outcomes": ["Yes", "No"],
                    "outcomePrices": ["0", "1"],
                }
            ]
        }
    )
    trades = {
        "trades": [
            {
                "wallet": "0xJey",
                "market_id": "0xcondition",
                "title": "Toronto high temp trade",
                "side": "BUY",
                "outcome": "No",
                "price": 0.90,
                "size": 10,
                "notional_usd": 9.0,
            },
            {
                "wallet": "0xSlug",
                "slug": "highest-temperature-in-toronto-on-april-28-2026-19c-or-higher",
                "side": "BUY",
                "outcome": "Yes",
                "price": 0.10,
                "size": 10,
                "notional_usd": 1.0,
            },
        ]
    }

    result = build_account_trade_resolution_dataset(trades, resolutions=metadata)

    assert result["summary"]["resolved_trades"] == 2
    assert result["summary"]["wins"] == 1
    assert result["summary"]["losses"] == 1
    assert result["trades"][0]["trade_result"] == "win"
    assert result["trades"][0]["resolution"]["matched_key"] == "0xcondition"
    assert result["trades"][1]["trade_result"] == "loss"
    assert result["trades"][1]["resolution"]["matched_key"] == "highest-temperature-in-toronto-on-april-28-2026-19c-or-higher"


def test_build_account_trade_resolution_dataset_scores_buy_sell_yes_no_trades() -> None:
    trades = {
        "trades": [
            {
                "wallet": "0xJey",
                "handle": "jey",
                "title": "Will the highest temperature in Toronto be 19°C or higher on April 28?",
                "slug": "highest-temperature-in-toronto-on-april-28-2026-19c-or-higher",
                "side": "BUY",
                "outcome": "No",
                "price": 0.90,
                "size": 10,
                "notional_usd": 9.0,
                "timestamp": "2026-04-28T23:25:14Z",
                "weather_market_type": "threshold",
                "city": "Toronto",
            },
            {
                "wallet": "0xUnplugged",
                "handle": "Unpluggedstoic",
                "title": "Will the highest temperature in Toronto be 15°C on April 28?",
                "slug": "highest-temperature-in-toronto-on-april-28-2026-15c",
                "side": "SELL",
                "outcome": "Yes",
                "price": 0.20,
                "size": 10,
                "notional_usd": 2.0,
                "timestamp": "2026-04-28T18:05:58Z",
                "weather_market_type": "exact_value",
                "city": "Toronto",
            },
            {
                "wallet": "0xCold",
                "handle": "ColdMath",
                "title": "Will the highest temperature in Dallas be 90°F or higher on April 28?",
                "slug": "highest-temperature-in-dallas-on-april-28-2026-90f-or-higher",
                "side": "BUY",
                "outcome": "Yes",
                "price": 0.55,
                "size": 10,
                "notional_usd": 5.5,
                "timestamp": "2026-04-28T12:00:00Z",
                "weather_market_type": "threshold",
                "city": "Dallas",
            },
        ]
    }
    resolutions = {
        "highest-temperature-in-toronto-on-april-28-2026-19c-or-higher": {"resolved_outcome": "No", "status": "resolved", "source": "official_fixture"},
        "highest-temperature-in-toronto-on-april-28-2026-15c": {"resolved_outcome": "No", "status": "resolved", "source": "official_fixture"},
    }

    result = build_account_trade_resolution_dataset(trades, resolutions=resolutions)

    assert result["paper_only"] is True
    assert result["live_order_allowed"] is False
    assert result["summary"] == {
        "trades": 3,
        "resolved_trades": 2,
        "wins": 2,
        "losses": 0,
        "unresolved_trades": 1,
        "paper_only": True,
        "live_order_allowed": False,
    }
    assert result["trades"][0]["trade_result"] == "win"
    assert result["trades"][0]["effective_position"] == "No"
    assert result["trades"][0]["estimated_pnl_usdc"] == 1.0
    assert result["trades"][1]["trade_result"] == "win"
    assert result["trades"][1]["effective_position"] == "No"
    assert result["trades"][1]["estimated_pnl_usdc"] == 2.0
    assert result["trades"][2]["trade_result"] == "unresolved"


def test_build_shadow_profile_evaluation_scores_profiles_from_resolved_trade_dataset() -> None:
    trade_resolution_dataset = {
        "paper_only": True,
        "live_order_allowed": False,
        "trades": [
            {"wallet": "0xJey", "handle": "jey", "profile_id": "jey_threshold", "profile_role": "clean_threshold_reference", "trade_result": "win", "estimated_pnl_usdc": 1.0, "notional_usd": 9.0, "weather_market_type": "threshold", "city": "Toronto"},
            {"wallet": "0xJey", "handle": "jey", "profile_id": "jey_threshold", "profile_role": "clean_threshold_reference", "trade_result": "loss", "estimated_pnl_usdc": -3.0, "notional_usd": 3.0, "weather_market_type": "threshold", "city": "Toronto"},
            {"wallet": "0xUnplugged", "handle": "Unpluggedstoic", "profile_id": "tail_longshot", "profile_role": "low_price_tail_reference", "trade_result": "unresolved", "estimated_pnl_usdc": 0.0, "notional_usd": 2.0, "weather_market_type": "exact_value", "city": "Paris"},
        ],
    }

    result = build_shadow_profile_evaluation({"orders": [], "skipped": []}, trade_resolution_dataset=trade_resolution_dataset)

    assert result["summary"]["resolved_trades"] == 2
    assert result["summary"]["trade_wins"] == 1
    jey = next(profile for profile in result["profiles"] if profile["profile_id"] == "jey_threshold")
    assert jey["historical_trades"] == 2
    assert jey["resolved_trades"] == 2
    assert jey["trade_winrate"] == 0.5
    assert jey["historical_estimated_pnl_usdc"] == -2.0
    assert jey["top_cities"] == {"Toronto": 2}


def test_build_shadow_profile_evaluation_maps_historical_trades_to_existing_wallet_profiles() -> None:
    paper_orders = {
        "orders": [
            {
                "profile_id": "jey_threshold",
                "profile_role": "clean_threshold_reference",
                "wallet_signal": "0xJey",
                "requested_notional_usdc": 3.0,
                "strict_limit_price": 0.40,
                "features": {"resolution": {"available": False}},
            }
        ],
        "skipped": [],
    }
    trade_resolution_dataset = {
        "trades": [
            {
                "wallet": "0xJey",
                "handle": "jey",
                "trade_result": "win",
                "estimated_pnl_usdc": 1.0,
                "notional_usd": 9.0,
                "weather_market_type": "threshold",
                "city": "Toronto",
            }
        ]
    }

    result = build_shadow_profile_evaluation(paper_orders, trade_resolution_dataset=trade_resolution_dataset)

    profile_ids = {profile["profile_id"] for profile in result["profiles"]}
    assert "jey_threshold" in profile_ids
    assert "0xJey" not in profile_ids
    jey = next(profile for profile in result["profiles"] if profile["profile_id"] == "jey_threshold")
    assert jey["historical_trades"] == 1
    assert jey["trade_wins"] == 1


def test_build_shadow_profile_evaluation_scores_profiles_from_resolved_paper_orders() -> None:
    paper_orders = {
        "paper_only": True,
        "live_order_allowed": False,
        "summary": {"paper_orders": 3, "skipped": 2},
        "orders": [
            {
                "profile_id": "jey_threshold",
                "profile_role": "clean_threshold_reference",
                "wallet_signal": "0xJey",
                "requested_notional_usdc": 3.0,
                "strict_limit_price": 0.40,
                "features": {"resolution": {"available": True, "resolved_outcome": "Yes"}},
            },
            {
                "profile_id": "jey_threshold",
                "profile_role": "clean_threshold_reference",
                "wallet_signal": "0xJey",
                "requested_notional_usdc": 3.0,
                "strict_limit_price": 0.60,
                "features": {"resolution": {"available": True, "resolved_outcome": "No"}},
            },
            {
                "profile_id": "marchyel_like_capped",
                "profile_role": "large_sizing_grid_reference_capped",
                "wallet_signal": "0xMarchyel",
                "requested_notional_usdc": 1.25,
                "strict_limit_price": 0.25,
                "features": {"resolution": {"available": False}},
            },
        ],
        "skipped": [
            {"wallet": "0xJey", "market_id": "m-a", "reason": "profile_min_edge_not_met"},
            {"wallet": "0xMarchyel", "market_id": "m-b", "reason": "missing_forecast_features"},
        ],
    }

    result = build_shadow_profile_evaluation(paper_orders)

    assert result["paper_only"] is True
    assert result["live_order_allowed"] is False
    assert result["summary"] == {"profiles": 2, "orders": 3, "resolved_orders": 2, "wins": 1, "losses": 1, "unresolved_orders": 1}
    assert result["profiles"][0] == {
        "profile_id": "jey_threshold",
        "profile_role": "clean_threshold_reference",
        "orders": 2,
        "resolved_orders": 2,
        "wins": 1,
        "losses": 1,
        "unresolved_orders": 0,
        "winrate": 0.5,
        "requested_notional_usdc": 6.0,
        "estimated_pnl_usdc": 1.5,
        "roi": 0.25,
        "skipped_counts": {"profile_min_edge_not_met": 1},
        "recommendation": "observe_more",
    }
    assert result["profiles"][1]["profile_id"] == "marchyel_like_capped"
    assert result["profiles"][1]["recommendation"] == "needs_resolution_data"


def test_cli_market_metadata_resolution_writes_paper_only_resolution_artifact(tmp_path: Path) -> None:
    markets_in = tmp_path / "markets.json"
    output_json = tmp_path / "resolutions.json"
    markets_in.write_text(
        json.dumps(
            {
                "markets": [
                    {
                        "id": "m-toronto-19",
                        "question": "Will the highest temperature in Toronto be 19°C or higher on April 28?",
                        "closed": True,
                        "active": False,
                        "outcomes": '["Yes", "No"]',
                        "outcomePrices": '["0", "1"]',
                        "resolvedOutcome": "No",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "weather_pm.cli",
            "market-metadata-resolution",
            "--markets-json",
            str(markets_in),
            "--output-json",
            str(output_json),
        ],
        capture_output=True,
        text=True,
        check=False,
        env={"PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
    )

    assert result.returncode == 0, result.stderr
    compact = json.loads(result.stdout)
    assert compact["summary"]["resolved_markets"] == 1
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["paper_only"] is True
    assert payload["live_order_allowed"] is False
    assert payload["resolutions"]["m-toronto-19"]["resolved_outcome"] == "No"


def test_cli_shadow_profile_evaluator_writes_json_and_markdown(tmp_path: Path) -> None:
    paper_orders_in = tmp_path / "paper_orders.json"
    output_json = tmp_path / "evaluation.json"
    output_md = tmp_path / "evaluation.md"
    paper_orders_in.write_text(
        json.dumps(
            {
                "paper_only": True,
                "live_order_allowed": False,
                "orders": [
                    {
                        "profile_id": "hotcold_weather_native",
                        "profile_role": "weather_native_reference",
                        "wallet_signal": "0xHotCold",
                        "requested_notional_usdc": 2.5,
                        "strict_limit_price": 0.20,
                        "features": {"resolution": {"available": True, "resolved_outcome": "Yes"}},
                    }
                ],
                "skipped": [],
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "weather_pm.cli",
            "shadow-profile-evaluator",
            "--paper-orders-json",
            str(paper_orders_in),
            "--output-json",
            str(output_json),
            "--output-md",
            str(output_md),
        ],
        capture_output=True,
        text=True,
        check=False,
        env={"PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
    )

    assert result.returncode == 0, result.stderr
    compact = json.loads(result.stdout)
    assert compact["summary"]["profiles"] == 1
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["profiles"][0]["profile_id"] == "hotcold_weather_native"
    assert "hotcold_weather_native" in output_md.read_text(encoding="utf-8")
