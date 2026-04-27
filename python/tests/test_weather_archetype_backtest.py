from __future__ import annotations

import json
from pathlib import Path

from weather_pm.archetype_backtest import build_archetype_backtest, write_archetype_backtest_artifacts


def _fixture_rows() -> list[dict[str, object]]:
    return [
        {
            "market_id": "chi-grid-yes",
            "question": "Will the highest temperature in Chicago be exactly 72°F on April 30?",
            "archetype": "event_surface_grid_specialist",
            "side": "YES",
            "entry_price": 0.40,
            "resolved_price": 1.0,
            "stake_usdc": 20,
            "orderbook": {"yes_asks": [{"price": 0.40, "size": 100}]},
            "source_station_code": "KMDW",
            "entered_at_hours_to_resolution": 30,
        },
        {
            "market_id": "chi-bin-no",
            "question": "Will the highest temperature in Chicago be exactly 70°F on April 30?",
            "archetype": "exact_bin_anomaly_hunter",
            "side": "NO",
            "entry_price": 1.0,
            "resolved_price": 1.0,
            "stake_usdc": 10,
            "orderbook": {"no_asks": [{"price": 1.0, "size": 50}]},
            "source_station_code": "KMDW",
            "entered_at_hours_to_resolution": 4,
        },
        {
            "market_id": "ny-threshold-loss",
            "question": "Will the highest temperature in New York be 80°F or higher on April 30?",
            "archetype": "threshold_harvester",
            "side": "YES",
            "entry_price": 0.55,
            "resolved_price": 0.0,
            "stake_usdc": 10,
            "orderbook": {"yes_asks": [{"price": 0.55, "size": 100}]},
            "source_station_code": "KNYC",
            "entered_at_hours_to_resolution": 1,
        },
        {
            "market_id": "mia-generalist",
            "question": "Will the highest temperature in Miami be exactly 90°F on April 30?",
            "archetype": "weather_signal_generalist",
            "side": "YES",
            "entry_price": 0.625,
            "resolved_price": 1.0,
            "stake_usdc": 50,
            "orderbook": {"yes_asks": [{"price": 0.625, "size": 100}]},
            "source_station_code": "KMIA",
            "entered_at_hours_to_resolution": 72,
        },
    ]


def test_archetype_backtest_replays_fixture_deterministically_and_aggregates_metrics() -> None:
    report = build_archetype_backtest(_fixture_rows(), max_fillable_spend_usdc=25)

    assert report["schema_version"] == 1
    assert report["summary"] == {
        "input_trade_count": 4,
        "replayed_trade_count": 4,
        "archetype_count": 4,
        "pnl_usdc": 35.0,
        "roi": 0.538462,
        "max_drawdown_usdc": 10.0,
        "hit_rate": 0.5,
        "fillability": 0.722222,
        "capturable_volume_usdc": 65.0,
        "average_slippage": 0.0,
    }
    assert [trade["market_id"] for trade in report["trades"]] == [
        "chi-grid-yes",
        "chi-bin-no",
        "ny-threshold-loss",
        "mia-generalist",
    ]
    assert report["trades"][3]["filled_spend_usdc"] == 25.0
    assert report["trades"][3]["fillability_capped"] is True
    grid = report["archetypes"]["event_surface_grid_specialist"]
    assert grid["pnl_usdc"] == 30.0
    assert grid["roi"] == 1.5
    assert grid["hit_rate"] == 1.0
    assert report["time_to_resolution_buckets"] == {
        "lt_2h": {"trade_count": 1, "pnl_usdc": -10.0, "capturable_volume_usdc": 10.0},
        "2h_to_12h": {"trade_count": 1, "pnl_usdc": 0.0, "capturable_volume_usdc": 10.0},
        "12h_to_48h": {"trade_count": 1, "pnl_usdc": 30.0, "capturable_volume_usdc": 20.0},
        "gt_48h": {"trade_count": 1, "pnl_usdc": 15.0, "capturable_volume_usdc": 25.0},
        "unknown": {"trade_count": 0, "pnl_usdc": 0.0, "capturable_volume_usdc": 0.0},
    }


def test_archetype_backtest_missing_orderbook_marks_unfillable_without_pnl() -> None:
    report = build_archetype_backtest(
        [
            {
                "market_id": "missing-book",
                "question": "Will the highest temperature in Chicago be exactly 72°F on April 30?",
                "archetype": "event_surface_grid_specialist",
                "side": "YES",
                "entry_price": 0.40,
                "resolved_price": 1.0,
                "stake_usdc": 20,
                "source_station_code": "KMDW",
            }
        ]
    )

    trade = report["trades"][0]
    assert trade["fill_status"] == "empty_book"
    assert trade["execution_blocker"] == "missing_tradeable_quote"
    assert trade["filled_spend_usdc"] == 0.0
    assert trade["pnl_usdc"] == 0.0
    assert report["summary"]["fillability"] == 0.0


def test_archetype_backtest_drawdown_uses_equity_peak_to_trough() -> None:
    report = build_archetype_backtest(
        [
            {"market_id": "win", "question": "Will the highest temperature in Chicago be exactly 72°F on April 30?", "archetype": "weather_signal_generalist", "side": "YES", "resolved_price": 1.0, "stake_usdc": 10, "orderbook": {"yes_asks": [{"price": 0.5, "size": 100}]}},
            {"market_id": "loss-one", "question": "Will the highest temperature in Chicago be exactly 73°F on April 30?", "archetype": "weather_signal_generalist", "side": "YES", "resolved_price": 0.0, "stake_usdc": 20, "orderbook": {"yes_asks": [{"price": 0.5, "size": 100}]}},
            {"market_id": "loss-two", "question": "Will the highest temperature in Chicago be exactly 74°F on April 30?", "archetype": "weather_signal_generalist", "side": "YES", "resolved_price": 0.0, "stake_usdc": 10, "orderbook": {"yes_asks": [{"price": 0.5, "size": 100}]}},
        ]
    )

    assert report["summary"]["max_drawdown_usdc"] == 30.0
    assert report["equity_curve"] == [10.0, -10.0, -20.0]


def test_archetype_backtest_writes_json_and_markdown_artifacts(tmp_path: Path) -> None:
    input_path = tmp_path / "backtest_input.json"
    input_path.write_text(json.dumps({"trades": _fixture_rows()}), encoding="utf-8")

    artifact = write_archetype_backtest_artifacts(input_path, output_dir=tmp_path, max_fillable_spend_usdc=25)

    assert Path(artifact["json_path"]).name == "weather_archetype_backtest_latest.json"
    assert Path(artifact["md_path"]).name == "weather_archetype_backtest_latest.md"
    payload = json.loads(Path(artifact["json_path"]).read_text(encoding="utf-8"))
    assert list(payload) == [
        "schema_version",
        "summary",
        "archetypes",
        "exposure",
        "time_to_resolution_buckets",
        "equity_curve",
        "trades",
        "artifacts",
    ]
    markdown = Path(artifact["md_path"]).read_text(encoding="utf-8")
    assert "# Weather Archetype Backtest" in markdown
    assert "event_surface_grid_specialist" in markdown
