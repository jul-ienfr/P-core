from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

PYTHON_SRC = Path(__file__).resolve().parents[1] / "src"


def _run_weather_pm(*args: str) -> dict[str, object]:
    result = subprocess.run(
        [sys.executable, "-m", "weather_pm.cli", *args],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONPATH": str(PYTHON_SRC)},
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_match_trade_resolution_uses_strongest_available_key_and_scores_pnl() -> None:
    from weather_pm.account_resolution_coverage import match_trade_resolution

    trade = {
        "market_id": "market-123",
        "condition_id": "cond-weather-nyc-2026-05-04",
        "token_id": "token-not-in-resolution",
        "slug": "nyc-high-temp-above-80f-may-4",
        "title": "Will NYC high temperature be above 80F on May 4?",
        "outcome": "Yes",
        "side": "BUY",
        "price": 0.25,
        "notional_usd": 10.0,
    }
    resolutions_payload = {
        "resolutions": [
            {
                "condition_id": "cond-weather-nyc-2026-05-04",
                "slug": "nyc-high-temp-above-80f-may-4",
                "question": "NYC high temperature above 80F on May 4",
                "winning_side": "Yes",
            }
        ]
    }

    result = match_trade_resolution(trade, resolutions_payload)

    assert result["resolved"] is True
    assert result["match_key"] == "condition_id"
    assert result["winning_side"] == "Yes"
    assert result["outcome"] == "win"
    assert result["pnl"] == 30.0
    assert result["unresolved_reason"] is None
    assert result["paper_only"] is True
    assert result["live_order_allowed"] is False


def test_build_resolution_coverage_report_counts_matches_and_unresolved_reasons() -> None:
    from weather_pm.account_resolution_coverage import build_resolution_coverage_report

    trades_payload = {
        "trades": [
            {"market_id": "m1", "condition_id": "c1", "outcome": "Yes", "side": "BUY", "price": 0.5, "notional_usd": 5},
            {"market_id": "m2", "slug": "missing-resolution", "outcome": "No", "side": "BUY", "price": 0.4, "notional_usd": 4},
        ]
    }
    resolutions_payload = {"resolutions": [{"condition_id": "c1", "winning_side": "No"}]}

    report = build_resolution_coverage_report(trades_payload, resolutions_payload)

    assert report["paper_only"] is True
    assert report["live_order_allowed"] is False
    assert report["summary"]["trades"] == 2
    assert report["summary"]["resolved"] == 1
    assert report["summary"]["unresolved"] == 1
    assert report["summary"]["resolved_pct"] == 50.0
    assert report["summary"]["match_key_counts"] == {"condition_id": 1}
    assert report["summary"]["unresolved_reason_counts"] == {"no_resolution_match": 1}
    assert report["trades"][0]["resolution_match"]["outcome"] == "loss"


def test_event_slug_and_outcome_side_match_only_when_unique() -> None:
    from weather_pm.account_resolution_coverage import match_trade_resolution

    trade = {"event_slug": "boston-weather-may-4", "outcome": "No", "side": "BUY", "price": 0.2, "notional_usd": 5}
    resolutions_payload = {
        "resolutions": [
            {"event_slug": "boston-weather-may-4", "outcome_side": "No", "winning_side": "No"},
            {"event_slug": "boston-weather-may-4", "outcome_side": "Yes", "winning_side": "No"},
        ]
    }

    result = match_trade_resolution(trade, resolutions_payload)

    assert result["resolved"] is True
    assert result["match_key"] == "event_slug_outcome_side"
    assert result["outcome"] == "win"


def test_embedded_trade_resolution_beats_ambiguous_slug_backfill_rows() -> None:
    from weather_pm.account_resolution_coverage import match_trade_resolution

    trade = {
        "slug": "highest-temperature-in-paris-on-april-15-2026-18c",
        "outcome": "No",
        "side": "SELL",
        "price": 0.999,
        "size": 510,
        "notional_usd": 509.49,
        "resolution": {
            "available": True,
            "primary_key": "1965242",
            "matched_key": "highest-temperature-in-paris-on-april-15-2026-18c",
            "resolved_outcome": "No",
            "source": "gamma_closed_outcomePrices_proxy",
            "status": "closed_price_resolved_proxy",
        },
    }
    resolutions_payload = {
        "resolutions": {
            "a": {"slug": "highest-temperature-in-paris-on-april-15-2026-18c", "primary_key": "1965242", "resolved_outcome": "No"},
            "b": {"slug": "highest-temperature-in-paris-on-april-15-2026-18c", "primary_key": "1965243", "resolved_outcome": "Yes"},
        }
    }

    result = match_trade_resolution(trade, resolutions_payload)

    assert result["resolved"] is True
    assert result["match_key"] == "embedded_trade_resolution"
    assert result["winning_side"] == "No"
    assert result["outcome"] == "loss"
    assert result["resolution"]["primary_key"] == "1965242"


def test_cli_account_resolution_coverage_writes_artifact_and_prints_compact_summary(tmp_path: Path) -> None:
    trades_path = tmp_path / "trades.json"
    resolutions_path = tmp_path / "resolutions.json"
    output_path = tmp_path / "coverage.json"
    trades_path.write_text(
        json.dumps(
            {
                "trades": [
                    {
                        "market_id": "m1",
                        "condition_id": "c1",
                        "slug": "nyc-rain-may-4",
                        "title": "Will NYC get rain on May 4?",
                        "outcome": "Yes",
                        "side": "BUY",
                        "price": 0.5,
                        "notional_usd": 5,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    resolutions_path.write_text(json.dumps({"resolutions": [{"condition_id": "c1", "slug": "nyc-rain-may-4", "winning_side": "Yes"}]}), encoding="utf-8")

    result = _run_weather_pm(
        "account-resolution-coverage",
        "--trades-json",
        str(trades_path),
        "--resolutions-json",
        str(resolutions_path),
        "--output-json",
        str(output_path),
    )

    assert result["paper_only"] is True
    assert result["live_order_allowed"] is False
    assert result["resolved_pct"] == 100.0
    assert result["resolved"] == 1
    assert result["unresolved"] == 0
    assert result["output_json"] == str(output_path)
    artifact = json.loads(output_path.read_text(encoding="utf-8"))
    assert artifact["summary"]["match_key_counts"] == {"condition_id": 1}
