from __future__ import annotations

from typing import Any


def build_account_data_source_manifest() -> dict[str, Any]:
    sources = [
        {
            "source_id": "polymarket_data_api_trades",
            "role": "recent_or_limited_public_account_trade_backfill",
            "priority": "medium",
            "status": "integrated_limited",
            "read_only": True,
            "paper_only": True,
            "live_order_allowed": False,
            "expected_fields": ["wallet", "market", "price", "size", "timestamp"],
            "limitations": ["usually bounded per account", "not a full historical orderbook source"],
        },
        {
            "source_id": "sii_wangzj_polymarket_data_hf",
            "role": "massive_historical_trades_users_markets_orderfilled_backfill",
            "priority": "high",
            "status": "planned_adapter",
            "read_only": True,
            "paper_only": True,
            "live_order_allowed": False,
            "expected_fields": ["trades.parquet", "users.parquet", "markets.parquet", "orderfilled_part*.parquet"],
            "limitations": ["large dataset", "schema must be normalized locally", "does not guarantee exact book at decision time"],
        },
        {
            "source_id": "sii_wangzj_polymarket_data_github",
            "role": "schema_and_etl_reference_for_hf_dataset",
            "priority": "medium",
            "status": "reference_only",
            "read_only": True,
            "paper_only": True,
            "live_order_allowed": False,
            "expected_fields": ["processors", "fetchers", "schema documentation"],
            "limitations": ["do not vendor whole repo", "use as mapping reference"],
        },
        {
            "source_id": "pmxt_l2_archive",
            "role": "historical_l2_orderbook_replay_candidate",
            "priority": "high",
            "status": "planned_adapter",
            "read_only": True,
            "paper_only": True,
            "live_order_allowed": False,
            "expected_fields": ["timestamp", "token_id", "bids", "asks"],
            "limitations": ["coverage may start after some historical trades", "hourly/archive granularity must be measured"],
        },
        {
            "source_id": "telonex_full_depth_snapshots",
            "role": "optional_full_depth_historical_orderbook_candidate",
            "priority": "high",
            "status": "access_unknown",
            "read_only": True,
            "paper_only": True,
            "live_order_allowed": False,
            "expected_fields": ["timestamp", "token_id", "full_depth_book"],
            "limitations": ["may need external access", "must remain read-only"],
        },
        {
            "source_id": "gamma_closed_markets",
            "role": "closed_market_metadata_and_resolution_backfill",
            "priority": "high",
            "status": "partially_integrated",
            "read_only": True,
            "paper_only": True,
            "live_order_allowed": False,
            "expected_fields": ["market_id", "condition_id", "slug", "outcomes", "resolution"],
            "limitations": ["matching aliases must be explicit", "some outcomes may remain unresolved"],
        },
        {
            "source_id": "polymarket_clob_current_book",
            "role": "current_live_book_observer_for_fresh_capturability_checks",
            "priority": "medium",
            "status": "current_book_only",
            "read_only": True,
            "paper_only": True,
            "live_order_allowed": False,
            "expected_fields": ["token_id", "bids", "asks", "timestamp"],
            "limitations": ["not historical unless snapshots are stored", "requires valid token_id"],
        },
        {
            "source_id": "official_weather_sources",
            "role": "forecast_station_observation_and_resolution_source_context",
            "priority": "high",
            "status": "partially_integrated",
            "read_only": True,
            "paper_only": True,
            "live_order_allowed": False,
            "expected_fields": ["station", "forecast_timestamp", "forecast_value", "observation", "resolution_source"],
            "limitations": ["must separate decision-time forecast from later observation", "source coverage varies by city"],
        },
    ]
    return {
        "artifact": "account_data_source_manifest",
        "paper_only": True,
        "live_order_allowed": False,
        "sources": sources,
        "summary": {
            "sources": len(sources),
            "high_priority_sources": [row["source_id"] for row in sources if row["priority"] == "high"],
            "planned_adapters": [row["source_id"] for row in sources if str(row["status"]).startswith("planned")],
        },
    }


def compact_account_data_source_manifest(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    return {
        "paper_only": True,
        "live_order_allowed": False,
        "sources": int(summary.get("sources") or len(payload.get("sources", []))),
        "high_priority_sources": list(summary.get("high_priority_sources") or []),
        "planned_adapters": list(summary.get("planned_adapters") or []),
    }
