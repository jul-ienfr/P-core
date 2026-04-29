from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _fixtures(tmp_path: Path) -> dict[str, Path]:
    ts = "2026-04-29T12:10:00Z"
    trades = []
    resolutions = []
    snapshots = []
    for idx in range(6):
        market_id = f"m{idx}"
        trades.append(
            {
                "account": "Alpha" if idx < 3 else "Beta",
                "wallet": "0xa" if idx < 3 else "0xb",
                "market_id": market_id,
                "condition_id": f"c{idx}",
                "token_id": f"t{idx}",
                "timestamp": ts,
                "city": "Paris",
                "date": "2026-05-04",
                "market_type": "high_temperature",
                "side": "BUY",
                "outcome": "Yes",
                "price": 0.40,
                "size": 10,
                "notional_usd": 4,
                "threshold": 22,
            }
        )
        resolutions.append({"market_id": market_id, "winning_side": "Yes", "resolution_value": 23})
        snapshots.append(
            {
                "market_id": market_id,
                "token_id": f"t{idx}",
                "timestamp": "2026-04-29T12:09:00Z",
                "bids": [{"price": 0.39, "size": 100}],
                "asks": [{"price": 0.41, "size": 100}],
            }
        )
    snapshots.append(
        {
            "market_id": "m-current",
            "timestamp": "2026-04-29T12:09:00Z",
            "best_bid": 0.40,
            "best_ask": 0.42,
            "spread": 0.02,
            "depth_near_touch": 100,
        }
    )
    markets = [
        {
            "market_id": "m-current",
            "question": "Will Paris high temperature exceed 22C on May 4, 2026?",
            "observable": True,
            "active_timestamp": ts,
            "city": "Paris",
            "date": "2026-05-04",
            "market_type": "high_temperature",
            "side": "BUY",
            "price": 0.42,
            "threshold": 22,
        }
    ]
    forecasts = [
        {
            "market_id": "m-current",
            "forecast_timestamp": "2026-04-29T11:55:00Z",
            "city": "Paris",
            "date": "2026-05-04",
            "market_type": "high_temperature",
            "forecast_value": 23,
            "threshold": 22,
            "official_source_available": True,
            "station_id": "PARIS-1",
        }
    ]
    paths = {
        "trades": tmp_path / "trades.json",
        "resolutions": tmp_path / "resolutions.json",
        "orderbooks": tmp_path / "orderbooks.json",
        "markets": tmp_path / "markets.json",
        "forecasts": tmp_path / "forecasts.json",
    }
    _write_json(paths["trades"], {"trades": trades})
    _write_json(paths["resolutions"], {"resolutions": resolutions})
    _write_json(paths["orderbooks"], {"snapshots": snapshots})
    _write_json(paths["markets"], {"markets": markets})
    _write_json(paths["forecasts"], {"forecasts": forecasts})
    return paths


def test_winner_pattern_watchlist_capture_payload_is_paper_only_metadata() -> None:
    from weather_pm.winner_pattern_pipeline import build_winner_pattern_watchlist_capture_payload

    payload = build_winner_pattern_watchlist_capture_payload(source="fixture_watchlist")

    assert payload["mode"] == "winner_pattern_watchlist"
    assert payload["paper_only"] is True
    assert payload["live_order_allowed"] is False
    for key in ("retention_policy", "compressed", "source", "captured_at", "paper_only", "live_order_allowed"):
        assert key in payload
    assert payload["capture_scope"] == [
        "current_orderbook_compact_snapshots_for_matched_surfaces",
        "full_book_only_on_account_trade_large_movement_or_candidate_trigger",
        "forecast_snapshots",
        "market_surface_snapshots",
        "observed_account_trades",
    ]


def test_cli_winner_pattern_pipeline_runs_fixture_only_end_to_end(tmp_path: Path) -> None:
    paths = _fixtures(tmp_path)
    output_dir = tmp_path / "run"
    env = dict(os.environ)
    env["PYTHONPATH"] = "python/src"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "weather_pm.cli",
            "winner-pattern-pipeline",
            "--trades-json",
            str(paths["trades"]),
            "--resolutions-json",
            str(paths["resolutions"]),
            "--orderbook-snapshots-json",
            str(paths["orderbooks"]),
            "--market-snapshots-json",
            str(paths["markets"]),
            "--forecast-snapshots-json",
            str(paths["forecasts"]),
            "--output-dir",
            str(output_dir),
        ],
        cwd=Path(__file__).resolve().parents[2],
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    payload = json.loads(result.stdout)

    assert payload["paper_only"] is True
    assert payload["live_order_allowed"] is False
    assert payload["allow_network"] is False
    assert payload["output_dir"] == str(output_dir)
    expected = {
        "resolution_coverage.json",
        "orderbook_context.json",
        "decision_dataset.json",
        "weather_context.json",
        "winner_patterns.json",
        "paper_candidates.json",
        "operator_report.md",
    }
    assert expected.issubset({Path(path).name for path in payload["artifact_paths"].values()})
    for filename in expected:
        assert (output_dir / filename).is_file()
    assert payload["artifact_counts"]["resolution_coverage"] == 6
    assert payload["artifact_counts"]["research_only_patterns"] >= 1
    assert payload["artifact_counts"]["winner_patterns"] == 0
    assert payload["artifact_counts"]["weather_context"] == 1
    winner_payload = json.loads((output_dir / "winner_patterns.json").read_text(encoding="utf-8"))
    research_pattern = winner_payload["research_only_patterns"][0]
    assert research_pattern["promotion_gate_version"] == "weather_winner_pattern_v2_2026_04"
    assert research_pattern["promotion_eligible"] is False
    assert "insufficient_resolved_sample" in research_pattern["promotion_blockers"]
    resolution_payload = json.loads((output_dir / "resolution_coverage.json").read_text(encoding="utf-8"))
    watchlist_mode = resolution_payload["watchlist_capture_mode"]
    assert watchlist_mode["paper_only"] is True
    assert watchlist_mode["live_order_allowed"] is False
    for key in ("retention_policy", "compressed", "source", "captured_at"):
        assert key in watchlist_mode
    candidates_payload = json.loads((output_dir / "paper_candidates.json").read_text(encoding="utf-8"))
    assert candidates_payload["summary"]["paper_candidates"] == 0
    assert candidates_payload["summary"]["research_only_matches"] == 1
    assert candidates_payload["watch_only"][0]["paper_probe_authorized"] is False


def test_pipeline_uses_resolution_match_primary_key_for_orderbook_context(tmp_path: Path) -> None:
    from weather_pm.winner_pattern_pipeline import run_winner_pattern_pipeline

    trades_path = tmp_path / "slug_only_trades.json"
    resolutions_path = tmp_path / "resolutions.json"
    orderbooks_path = tmp_path / "orderbooks.json"
    markets_path = tmp_path / "markets.json"
    forecasts_path = tmp_path / "forecasts.json"
    output_dir = tmp_path / "run-resolution-bridge"

    _write_json(
        trades_path,
        {
            "paper_only": True,
            "live_order_allowed": False,
            "trades": [
                {
                    "slug": "highest-temperature-in-toronto-on-april-30-2026-16c-or-higher",
                    "title": "Will the highest temperature in Toronto be 16°C or higher on April 30?",
                    "outcome": "Yes",
                    "side": "BUY",
                    "price": 0.35,
                    "size": 20,
                    "notional_usd": 7,
                    "timestamp": "2026-04-29T10:00:00Z",
                    "city": "Toronto",
                    "date": "April 30",
                    "market_type": "threshold",
                }
            ],
        },
    )
    _write_json(
        resolutions_path,
        {
            "paper_only": True,
            "live_order_allowed": False,
            "resolutions": {
                "2112614": {
                    "primary_key": "2112614",
                    "matched_key": "2112614",
                    "aliases": [
                        "highest-temperature-in-toronto-on-april-30-2026-16c-or-higher",
                        "Will the highest temperature in Toronto be 16°C or higher on April 30?",
                    ],
                    "question": "Will the highest temperature in Toronto be 16°C or higher on April 30?",
                    "resolved_outcome": "Yes",
                }
            },
        },
    )
    _write_json(orderbooks_path, {"2112614": {"best_bid": 0.31, "best_ask": 0.37, "depth_usd": 2500}})
    _write_json(
        markets_path,
        {
            "markets": [
                {
                    "market_id": "2112614",
                    "question": "Will the highest temperature in Toronto be 16°C or higher on April 30?",
                    "observable": True,
                    "active_timestamp": "2026-04-29T10:00:00Z",
                    "city": "Toronto",
                    "date": "April 30",
                    "market_type": "threshold",
                    "side": "BUY",
                    "price": 0.35,
                }
            ]
        },
    )
    _write_json(forecasts_path, {"toronto": {"forecast_high_c": 17, "freshness_minutes": 30}})

    payload = run_winner_pattern_pipeline(
        trades_json=trades_path,
        resolutions_json=resolutions_path,
        orderbook_snapshots_json=orderbooks_path,
        market_snapshots_json=markets_path,
        forecast_snapshots_json=forecasts_path,
        output_dir=output_dir,
    )

    assert payload["paper_only"] is True
    assert payload["live_order_allowed"] is False
    assert payload["artifact_counts"]["resolution_coverage"] == 1
    assert payload["artifact_counts"]["orderbook_context"] == 1
    orderbook_payload = json.loads((output_dir / "orderbook_context.json").read_text(encoding="utf-8"))
    assert orderbook_payload["trades"][0]["orderbook_context_available"] is True
    assert orderbook_payload["trades"][0]["snapshot_timestamp"] == "latest"
    assert orderbook_payload["trades"][0]["live_order_allowed"] is False


def test_winner_pattern_pipeline_rejects_allow_network(tmp_path: Path) -> None:
    paths = _fixtures(tmp_path)
    env = dict(os.environ)
    env["PYTHONPATH"] = "python/src"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "weather_pm.cli",
            "winner-pattern-pipeline",
            "--trades-json",
            str(paths["trades"]),
            "--resolutions-json",
            str(paths["resolutions"]),
            "--orderbook-snapshots-json",
            str(paths["orderbooks"]),
            "--market-snapshots-json",
            str(paths["markets"]),
            "--forecast-snapshots-json",
            str(paths["forecasts"]),
            "--output-dir",
            str(tmp_path / "run"),
            "--allow-network",
        ],
        cwd=Path(__file__).resolve().parents[2],
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.returncode != 0
    assert "allow-network is not yet supported" in result.stderr
