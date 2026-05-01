from __future__ import annotations

from weather_pm.operator_summary import _daily_operator_rollup, _watchlist_row


def test_watchlist_row_exposes_live_quality_and_forces_micro_live_off() -> None:
    row = _watchlist_row(
        {
            "market_id": "m-quality",
            "matched_traders": ["weatherace"],
            "execution_snapshot": {
                "best_bid_yes": 0.40,
                "best_ask_yes": 0.42,
                "spread_yes": 0.02,
                "yes_ask_depth_usd": 120.0,
            },
            "resolution_status": {"official_daily_extract": {"available": True}},
        },
        handle_lookup={
            "weatherace": {
                "handle": "weatherace",
                "classification": "weather-heavy",
                "weather_pnl_usd": 1000,
                "weather_volume_usd": 5000,
                "pnl_over_volume_pct": 20,
            }
        },
    )

    quality = row["live_quality"]
    assert quality["live_quality_score"] > 0
    assert quality["can_micro_live"] is False
    assert quality["micro_live_allowed"] is False
    assert quality["live_order_allowed"] is False
    assert quality["paper_only"] is True

    rollup = _daily_operator_rollup([row], live_quality_summary={"rows": 1, "max_live_quality_score": quality["live_quality_score"]})
    assert rollup["can_micro_live_count"] == 0
    assert rollup["micro_live_allowed"] is False
    assert rollup["live_quality_summary"]["rows"] == 1
